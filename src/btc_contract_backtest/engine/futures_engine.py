from __future__ import annotations

import ccxt
import numpy as np
import pandas as pd

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, RiskConfig


class FuturesBacktestEngine:
    def __init__(
        self,
        contract: ContractSpec,
        account: AccountConfig,
        risk: RiskConfig,
        timeframe: str = "1h",
    ):
        self.contract = contract
        self.account = account
        self.risk = risk
        self.timeframe = timeframe
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

    def simulate(self, signal_df: pd.DataFrame) -> dict:
        capital = self.account.initial_capital
        side = 0
        entry_price = None
        entry_time = None
        notional = 0.0
        bars_held = 0
        peak_price = None
        trough_price = None
        equity_curve = []
        trades = []
        liquidation_events = 0

        def close_trade(ts, px, reason):
            nonlocal capital, side, entry_price, entry_time, notional, bars_held, peak_price, trough_price
            gross = ((px - entry_price) / entry_price) * notional * self.contract.leverage * side
            fees = (notional * self.account.taker_fee_rate) * 2
            funding = notional * (self.account.funding_rate_annual / 365) * max(bars_held, 1)
            pnl = gross - fees - funding
            capital += pnl
            trades.append({
                "entry_time": entry_time,
                "exit_time": ts,
                "entry_price": entry_price,
                "exit_price": px,
                "position": side,
                "bars_held": bars_held,
                "reason": reason,
                "gross_pnl": gross,
                "fees": fees,
                "funding": funding,
                "pnl_after_costs": pnl,
            })
            side = 0
            entry_price = None
            entry_time = None
            notional = 0.0
            bars_held = 0
            peak_price = None
            trough_price = None

        for ts, row in signal_df.iterrows():
            px = float(row["close"])
            unrealized = 0.0
            if side != 0 and entry_price is not None:
                bars_held += 1
                peak_price = px if peak_price is None else max(peak_price, px)
                trough_price = px if trough_price is None else min(trough_price, px)
                unrealized = ((px - entry_price) / entry_price) * notional * self.contract.leverage * side
                margin_used = notional / self.contract.leverage
                maintenance = notional * self.risk.maintenance_margin_ratio
                if capital + unrealized <= maintenance:
                    trades.append({
                        "entry_time": entry_time,
                        "exit_time": ts,
                        "entry_price": entry_price,
                        "exit_price": px,
                        "position": side,
                        "bars_held": bars_held,
                        "reason": "liquidation",
                        "pnl_after_costs": -(margin_used),
                    })
                    capital -= margin_used
                    side = 0
                    entry_price = None
                    entry_time = None
                    notional = 0.0
                    bars_held = 0
                    peak_price = None
                    trough_price = None
                    liquidation_events += 1
                    equity_curve.append({"timestamp": ts, "equity": capital, "close": px, "position": 0})
                    continue

                stop_loss_pct = self.risk.stop_loss_pct
                take_profit_pct = self.risk.take_profit_pct
                trailing_stop_pct = self.risk.trailing_stop_pct
                max_holding_bars = self.risk.max_holding_bars

                pnl_pct = ((px - entry_price) / entry_price) * side
                if stop_loss_pct is not None and pnl_pct <= -stop_loss_pct:
                    close_trade(ts, px, "stop_loss")
                    equity_curve.append({"timestamp": ts, "equity": capital, "close": px, "position": 0})
                    continue
                if take_profit_pct is not None and pnl_pct >= take_profit_pct:
                    close_trade(ts, px, "take_profit")
                    equity_curve.append({"timestamp": ts, "equity": capital, "close": px, "position": 0})
                    continue
                if trailing_stop_pct is not None:
                    if side == 1 and peak_price is not None and px <= peak_price * (1 - trailing_stop_pct):
                        close_trade(ts, px, "trailing_stop")
                        equity_curve.append({"timestamp": ts, "equity": capital, "close": px, "position": 0})
                        continue
                    if side == -1 and trough_price is not None and px >= trough_price * (1 + trailing_stop_pct):
                        close_trade(ts, px, "trailing_stop")
                        equity_curve.append({"timestamp": ts, "equity": capital, "close": px, "position": 0})
                        continue
                if max_holding_bars is not None and bars_held >= max_holding_bars:
                    close_trade(ts, px, "time_exit")
                    equity_curve.append({"timestamp": ts, "equity": capital, "close": px, "position": 0})
                    continue

            equity_curve.append({"timestamp": ts, "equity": capital + unrealized, "close": px, "position": side})
            signal = int(row.get("signal", 0))
            if signal == 0:
                continue
            if side == 0:
                side = signal
                entry_price = px
                entry_time = ts
                notional = capital * self.risk.max_position_notional_pct
                bars_held = 0
                peak_price = px
                trough_price = px
                continue
            if signal != side:
                close_trade(ts, px, "reverse_signal")
                side = signal
                entry_price = px
                entry_time = ts
                notional = capital * self.risk.max_position_notional_pct
                bars_held = 0
                peak_price = px
                trough_price = px

        trades_df = pd.DataFrame(trades)
        equity_df = pd.DataFrame(equity_curve)
        final_capital = float(equity_df.iloc[-1]["equity"]) if not equity_df.empty else capital
        return {
            "equity_curve": equity_df,
            "trades": trades_df,
            "initial_capital": self.account.initial_capital,
            "final_capital": final_capital,
            "liquidation_events": liquidation_events,
        }

    def calculate_metrics(self, results: dict) -> dict:
        equity = results["equity_curve"]["equity"]
        returns = equity.pct_change().dropna()
        total_return = ((results["final_capital"] - results["initial_capital"]) / results["initial_capital"]) * 100
        sharpe = 0.0 if len(returns) < 2 or returns.std() == 0 else (returns.mean() / returns.std()) * np.sqrt(252)
        dd = 0.0 if equity.empty else ((equity - equity.cummax()) / equity.cummax()).min() * 100
        trades = results["trades"]
        win_rate = 0.0 if trades.empty else (len(trades[trades["pnl_after_costs"] > 0]) / len(trades)) * 100
        return {
            "total_return": total_return,
            "sharpe_ratio": float(sharpe),
            "max_drawdown": float(dd),
            "win_rate": float(win_rate),
            "total_trades": int(len(trades)),
            "final_capital": float(results["final_capital"]),
            "liquidation_events": int(results["liquidation_events"]),
        }
