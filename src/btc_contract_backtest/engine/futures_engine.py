from __future__ import annotations

import ccxt
import numpy as np
import pandas as pd

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, ExecutionConfig, LiveRiskConfig, RiskConfig
from btc_contract_backtest.engine.execution_models import OrderSide, OrderType
from btc_contract_backtest.engine.simulator_core import SimulatorCore


class FuturesBacktestEngine:
    def __init__(
        self,
        contract: ContractSpec,
        account: AccountConfig,
        risk: RiskConfig,
        timeframe: str = "1h",
        execution: ExecutionConfig | None = None,
        live_risk: LiveRiskConfig | None = None,
    ):
        self.contract = contract
        self.account = account
        self.risk = risk
        self.timeframe = timeframe
        self.execution = execution or ExecutionConfig()
        self.live_risk = live_risk or LiveRiskConfig()
        self.exchange = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})

    def fetch_historical_data(self, start_date: str, end_date: str) -> pd.DataFrame:
        since = int(pd.Timestamp(start_date).timestamp() * 1000)
        rows = self.exchange.fetch_ohlcv(self.contract.symbol, timeframe=self.timeframe, since=since, limit=1000)
        tf_ms = self._parse_timeframe()
        while rows and pd.to_datetime(rows[-1][0], unit="ms") < pd.Timestamp(end_date) and len(rows) < 20000:
            nxt = self.exchange.fetch_ohlcv(self.contract.symbol, timeframe=self.timeframe, since=rows[-1][0] + tf_ms, limit=1000)
            if not nxt:
                break
            rows.extend(nxt)
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df[df["timestamp"] <= pd.Timestamp(end_date)]
        df.set_index("timestamp", inplace=True)
        return df

    def _parse_timeframe(self):
        mapping = {"1m": 60000, "5m": 300000, "15m": 900000, "30m": 1800000, "1h": 3600000, "4h": 14400000, "1d": 86400000}
        return mapping.get(self.timeframe, 3600000)

    def _compute_atr(self, df: pd.DataFrame, window: int = 14) -> pd.Series:
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - df["close"].shift(1)).abs()
        tr3 = (df["low"] - df["close"].shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window).mean()

    def simulate(self, signal_df: pd.DataFrame) -> dict:
        signal_df = signal_df.copy()
        if "atr" not in signal_df.columns:
            signal_df["atr"] = self._compute_atr(signal_df)

        core = SimulatorCore(self.contract, self.account, self.risk, self.execution, self.live_risk)
        equity_curve = []
        liquidation_events = 0

        for ts, row in signal_df.iterrows():
            snapshot = core.snapshot_from_bar(ts, row)
            if not core.check_snapshot_safety(snapshot):
                equity_curve.append({"timestamp": ts, "equity": core.capital, "close": snapshot.close, "position": core.position.side})
                continue

            if core.position.side != 0:
                core.position.bars_held += 1
                core.position.peak_price = snapshot.close if core.position.peak_price is None else max(core.position.peak_price, snapshot.close)
                core.position.trough_price = snapshot.close if core.position.trough_price is None else min(core.position.trough_price, snapshot.close)
                core.apply_periodic_funding(snapshot)

            price = snapshot.close
            atr = None if pd.isna(row.get("atr")) else float(row.get("atr"))

            unrealized = 0.0
            if core.position.side != 0 and core.position.entry_price is not None and core.position.quantity != 0:
                unrealized = ((price - core.position.entry_price) / core.position.entry_price) * core.position.notional * self.contract.leverage * core.position.side
                maintenance = core.position.notional * self.risk.maintenance_margin_ratio
                if core.capital + unrealized <= maintenance:
                    core.emit_risk_event("liquidation", "Maintenance margin breached", severity="critical")
                    core.trades.append({
                        "entry_time": core.position.entry_time,
                        "exit_time": str(ts),
                        "entry_price": core.position.entry_price,
                        "exit_price": price,
                        "position": core.position.side,
                        "bars_held": core.position.bars_held,
                        "notional_closed": core.position.notional,
                        "remaining_notional": 0.0,
                        "reason": "liquidation",
                        "is_partial": False,
                        "pnl_after_costs": -(core.position.margin_used),
                    })
                    core.capital -= core.position.margin_used
                    liquidation_events += 1
                    core.position.quantity = 0.0
                    core.position.side = 0
                    core.position.entry_price = None
                    core.position.notional = 0.0
                    core.position.margin_used = 0.0
                    equity_curve.append({"timestamp": ts, "equity": core.capital, "close": price, "position": 0})
                    continue

                pnl_pct = ((price - core.position.entry_price) / core.position.entry_price) * core.position.side
                should_close = None
                if self.risk.partial_take_profit_pct is not None and not core.position.partial_taken and pnl_pct >= self.risk.partial_take_profit_pct:
                    close_qty = abs(core.position.quantity) * self.risk.partial_close_ratio
                    order = core.create_order(OrderSide.SELL if core.position.side == 1 else OrderSide.BUY, close_qty, OrderType.MARKET, reduce_only=True)
                    for fill in core.try_fill_order(order, snapshot):
                        core.apply_fill(fill)
                    core.position.partial_taken = True
                if self.risk.break_even_trigger_pct is not None and pnl_pct >= self.risk.break_even_trigger_pct:
                    core.position.break_even_armed = True
                if self.risk.atr_stop_mult is not None and core.position.atr_at_entry is not None:
                    if core.position.side == 1 and price <= core.position.entry_price - (core.position.atr_at_entry * self.risk.atr_stop_mult):
                        should_close = "atr_stop"
                    if core.position.side == -1 and price >= core.position.entry_price + (core.position.atr_at_entry * self.risk.atr_stop_mult):
                        should_close = "atr_stop"
                if core.position.break_even_armed and should_close is None:
                    if core.position.side == 1 and price <= core.position.entry_price:
                        should_close = "break_even_stop"
                    if core.position.side == -1 and price >= core.position.entry_price:
                        should_close = "break_even_stop"
                if self.risk.stepped_trailing_stop_pct is not None and should_close is None:
                    if core.position.side == 1:
                        anchor = core.position.peak_price if core.position.stepped_stop_anchor is None else max(core.position.stepped_stop_anchor, core.position.peak_price)
                        core.position.stepped_stop_anchor = anchor
                        if price <= anchor * (1 - self.risk.stepped_trailing_stop_pct):
                            should_close = "stepped_trailing_stop"
                    if core.position.side == -1:
                        anchor = core.position.trough_price if core.position.stepped_stop_anchor is None else min(core.position.stepped_stop_anchor, core.position.trough_price)
                        core.position.stepped_stop_anchor = anchor
                        if price >= anchor * (1 + self.risk.stepped_trailing_stop_pct):
                            should_close = "stepped_trailing_stop"
                if self.risk.stop_loss_pct is not None and should_close is None and pnl_pct <= -self.risk.stop_loss_pct:
                    should_close = "stop_loss"
                if self.risk.take_profit_pct is not None and should_close is None and pnl_pct >= self.risk.take_profit_pct:
                    should_close = "take_profit"
                if self.risk.trailing_stop_pct is not None and should_close is None:
                    if core.position.side == 1 and core.position.peak_price is not None and price <= core.position.peak_price * (1 - self.risk.trailing_stop_pct):
                        should_close = "trailing_stop"
                    if core.position.side == -1 and core.position.trough_price is not None and price >= core.position.trough_price * (1 + self.risk.trailing_stop_pct):
                        should_close = "trailing_stop"
                if self.risk.max_holding_bars is not None and should_close is None and core.position.bars_held >= self.risk.max_holding_bars:
                    should_close = "time_exit"

                if should_close is not None:
                    order = core.create_order(OrderSide.SELL if core.position.side == 1 else OrderSide.BUY, abs(core.position.quantity), OrderType.MARKET, reduce_only=True)
                    for fill in core.try_fill_order(order, snapshot):
                        core.apply_fill(fill)
                    if core.trades:
                        core.trades[-1]["reason"] = should_close

            equity_curve.append({"timestamp": ts, "equity": core.capital + unrealized, "close": price, "position": core.position.side})

            signal = int(row.get("signal", 0))
            if core.check_daily_loss_kill(core.capital + unrealized):
                continue
            if signal == 0:
                continue
            if core.position.side == 0:
                notional = core.determine_notional(price, atr)
                qty = 0.0 if price <= 0 else notional / price
                order = core.create_order(OrderSide.BUY if signal == 1 else OrderSide.SELL, qty, OrderType.MARKET)
                for fill in core.try_fill_order(order, snapshot):
                    core.apply_fill(fill)
                    core.position.atr_at_entry = atr
                continue
            if signal != core.position.side:
                close_order = core.create_order(OrderSide.SELL if core.position.side == 1 else OrderSide.BUY, abs(core.position.quantity), OrderType.MARKET, reduce_only=True)
                for fill in core.try_fill_order(close_order, snapshot):
                    core.apply_fill(fill)
                notional = core.determine_notional(price, atr)
                qty = 0.0 if price <= 0 else notional / price
                open_order = core.create_order(OrderSide.BUY if signal == 1 else OrderSide.SELL, qty, OrderType.MARKET)
                for fill in core.try_fill_order(open_order, snapshot):
                    core.apply_fill(fill)
                    core.position.atr_at_entry = atr
                if core.trades:
                    core.trades[-1]["reason"] = "reverse_signal"

        trades_df = pd.DataFrame(core.trades)
        equity_df = pd.DataFrame(equity_curve)
        final_capital = float(equity_df.iloc[-1]["equity"]) if not equity_df.empty else core.capital
        return {
            "equity_curve": equity_df,
            "trades": trades_df,
            "initial_capital": self.account.initial_capital,
            "final_capital": final_capital,
            "liquidation_events": liquidation_events,
            "risk_events": pd.DataFrame(core.risk_events),
        }

    def calculate_metrics(self, results: dict) -> dict:
        equity = results["equity_curve"]["equity"]
        returns = equity.pct_change().dropna()
        total_return = ((results["final_capital"] - results["initial_capital"]) / results["initial_capital"]) * 100
        sharpe = 0.0 if len(returns) < 2 or returns.std() == 0 else (returns.mean() / returns.std()) * np.sqrt(252)
        dd = 0.0 if equity.empty else ((equity - equity.cummax()) / equity.cummax()).min() * 100
        trades = results["trades"]
        closed = trades[~trades.get("is_partial", False)] if not trades.empty and "is_partial" in trades.columns else trades
        win_rate = 0.0 if closed.empty else (len(closed[closed["pnl_after_costs"] > 0]) / len(closed)) * 100
        return {
            "total_return": total_return,
            "sharpe_ratio": float(sharpe),
            "max_drawdown": float(dd),
            "win_rate": float(win_rate),
            "total_trades": int(len(trades)),
            "final_capital": float(results["final_capital"]),
            "liquidation_events": int(results["liquidation_events"]),
            "risk_events": 0 if "risk_events" not in results or results["risk_events"].empty else int(len(results["risk_events"])),
        }
