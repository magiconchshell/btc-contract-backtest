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

    def _compute_atr(self, df: pd.DataFrame, window: int = 14) -> pd.Series:
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - df["close"].shift(1)).abs()
        tr3 = (df["low"] - df["close"].shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window).mean()

    def simulate(self, signal_df: pd.DataFrame) -> dict:
        capital = self.account.initial_capital
        peak_equity = capital
        side = 0
        entry_price = None
        entry_time = None
        initial_notional = 0.0
        open_notional = 0.0
        bars_held = 0
        peak_price = None
        trough_price = None
        break_even_armed = False
        partial_taken = False
        stepped_stop_anchor = None
        atr_at_entry = None
        equity_curve = []
        trades = []
        liquidation_events = 0

        signal_df = signal_df.copy()
        if "atr" not in signal_df.columns:
            signal_df["atr"] = self._compute_atr(signal_df)

        def current_position_scale(current_equity: float) -> float:
            nonlocal peak_equity
            peak_equity = max(peak_equity, current_equity)
            if not self.risk.drawdown_position_scale:
                return 1.0
            drawdown_pct = 0.0 if peak_equity <= 0 else max(0.0, (peak_equity - current_equity) / peak_equity * 100)
            if drawdown_pct <= self.risk.max_drawdown_scale_start_pct:
                return 1.0
            excess = min(drawdown_pct - self.risk.max_drawdown_scale_start_pct, 100.0)
            scale = 1.0 - (excess / 100.0)
            return max(self.risk.max_drawdown_scale_floor, scale)

        def determine_notional(current_capital: float, atr_value: float | None, price: float) -> float:
            scale = current_position_scale(current_capital)
            base_cap = current_capital * self.risk.max_position_notional_pct * scale
            candidates = [base_cap]
            if self.risk.risk_per_trade_pct is not None and self.risk.stop_loss_pct is not None and self.risk.stop_loss_pct > 0:
                risk_budget = current_capital * self.risk.risk_per_trade_pct * scale
                stop_based_notional = risk_budget / (self.risk.stop_loss_pct * self.contract.leverage)
                candidates.append(stop_based_notional)
            if self.risk.atr_position_sizing_mult is not None and atr_value is not None and atr_value > 0 and price > 0:
                atr_pct = atr_value / price
                if atr_pct > 0:
                    atr_based_notional = (current_capital * scale * self.risk.atr_position_sizing_mult) / (atr_pct * self.contract.leverage)
                    candidates.append(atr_based_notional)
            return max(0.0, min(candidates))

        def reset_position_state():
            nonlocal side, entry_price, entry_time, initial_notional, open_notional, bars_held
            nonlocal peak_price, trough_price, break_even_armed, partial_taken, stepped_stop_anchor, atr_at_entry
            side = 0
            entry_price = None
            entry_time = None
            initial_notional = 0.0
            open_notional = 0.0
            bars_held = 0
            peak_price = None
            trough_price = None
            break_even_armed = False
            partial_taken = False
            stepped_stop_anchor = None
            atr_at_entry = None

        def realized_pnl(px: float, notional_amount: float) -> tuple[float, float, float, float]:
            gross = ((px - entry_price) / entry_price) * notional_amount * self.contract.leverage * side
            fees = (notional_amount * self.account.taker_fee_rate) * 2
            funding = notional_amount * (self.account.funding_rate_annual / 365) * max(bars_held, 1)
            pnl = gross - fees - funding
            return gross, fees, funding, pnl

        def close_trade(ts, px, reason, notional_to_close: float | None = None, is_partial: bool = False):
            nonlocal capital, open_notional, partial_taken
            closing_notional = open_notional if notional_to_close is None else min(notional_to_close, open_notional)
            gross, fees, funding, pnl = realized_pnl(px, closing_notional)
            capital += pnl
            trades.append({
                "entry_time": entry_time,
                "exit_time": ts,
                "entry_price": entry_price,
                "exit_price": px,
                "position": side,
                "bars_held": bars_held,
                "notional_closed": closing_notional,
                "remaining_notional": max(open_notional - closing_notional, 0.0),
                "reason": reason,
                "is_partial": is_partial,
                "gross_pnl": gross,
                "fees": fees,
                "funding": funding,
                "pnl_after_costs": pnl,
            })
            open_notional -= closing_notional
            if is_partial and open_notional > 0:
                partial_taken = True
                return
            reset_position_state()

        for ts, row in signal_df.iterrows():
            px = float(row["close"])
            atr = None if pd.isna(row.get("atr")) else float(row.get("atr"))
            unrealized = 0.0

            if side != 0 and entry_price is not None:
                bars_held += 1
                peak_price = px if peak_price is None else max(peak_price, px)
                trough_price = px if trough_price is None else min(trough_price, px)
                unrealized = ((px - entry_price) / entry_price) * open_notional * self.contract.leverage * side
                margin_used = open_notional / self.contract.leverage
                maintenance = open_notional * self.risk.maintenance_margin_ratio

                if capital + unrealized <= maintenance:
                    trades.append({
                        "entry_time": entry_time,
                        "exit_time": ts,
                        "entry_price": entry_price,
                        "exit_price": px,
                        "position": side,
                        "bars_held": bars_held,
                        "notional_closed": open_notional,
                        "remaining_notional": 0.0,
                        "reason": "liquidation",
                        "is_partial": False,
                        "pnl_after_costs": -(margin_used),
                    })
                    capital -= margin_used
                    liquidation_events += 1
                    reset_position_state()
                    equity_curve.append({"timestamp": ts, "equity": capital, "close": px, "position": 0})
                    continue

                pnl_pct = ((px - entry_price) / entry_price) * side

                if self.risk.partial_take_profit_pct is not None and not partial_taken and pnl_pct >= self.risk.partial_take_profit_pct:
                    close_trade(ts, px, "partial_take_profit", open_notional * self.risk.partial_close_ratio, is_partial=True)
                    if side != 0:
                        equity_curve.append({"timestamp": ts, "equity": capital + ((px - entry_price) / entry_price) * open_notional * self.contract.leverage * side, "close": px, "position": side})
                        continue

                if self.risk.break_even_trigger_pct is not None and pnl_pct >= self.risk.break_even_trigger_pct:
                    break_even_armed = True

                if self.risk.atr_stop_mult is not None and atr_at_entry is not None:
                    if side == 1 and px <= entry_price - (atr_at_entry * self.risk.atr_stop_mult):
                        close_trade(ts, px, "atr_stop")
                        equity_curve.append({"timestamp": ts, "equity": capital, "close": px, "position": 0})
                        continue
                    if side == -1 and px >= entry_price + (atr_at_entry * self.risk.atr_stop_mult):
                        close_trade(ts, px, "atr_stop")
                        equity_curve.append({"timestamp": ts, "equity": capital, "close": px, "position": 0})
                        continue

                if break_even_armed:
                    if side == 1 and px <= entry_price:
                        close_trade(ts, px, "break_even_stop")
                        equity_curve.append({"timestamp": ts, "equity": capital, "close": px, "position": 0})
                        continue
                    if side == -1 and px >= entry_price:
                        close_trade(ts, px, "break_even_stop")
                        equity_curve.append({"timestamp": ts, "equity": capital, "close": px, "position": 0})
                        continue

                if self.risk.stepped_trailing_stop_pct is not None:
                    if side == 1:
                        anchor = peak_price if stepped_stop_anchor is None else max(stepped_stop_anchor, peak_price)
                        stepped_stop_anchor = anchor
                        if px <= anchor * (1 - self.risk.stepped_trailing_stop_pct):
                            close_trade(ts, px, "stepped_trailing_stop")
                            equity_curve.append({"timestamp": ts, "equity": capital, "close": px, "position": 0})
                            continue
                    if side == -1:
                        anchor = trough_price if stepped_stop_anchor is None else min(stepped_stop_anchor, trough_price)
                        stepped_stop_anchor = anchor
                        if px >= anchor * (1 + self.risk.stepped_trailing_stop_pct):
                            close_trade(ts, px, "stepped_trailing_stop")
                            equity_curve.append({"timestamp": ts, "equity": capital, "close": px, "position": 0})
                            continue

                if self.risk.stop_loss_pct is not None and pnl_pct <= -self.risk.stop_loss_pct:
                    close_trade(ts, px, "stop_loss")
                    equity_curve.append({"timestamp": ts, "equity": capital, "close": px, "position": 0})
                    continue
                if self.risk.take_profit_pct is not None and pnl_pct >= self.risk.take_profit_pct:
                    close_trade(ts, px, "take_profit")
                    equity_curve.append({"timestamp": ts, "equity": capital, "close": px, "position": 0})
                    continue
                if self.risk.trailing_stop_pct is not None:
                    if side == 1 and peak_price is not None and px <= peak_price * (1 - self.risk.trailing_stop_pct):
                        close_trade(ts, px, "trailing_stop")
                        equity_curve.append({"timestamp": ts, "equity": capital, "close": px, "position": 0})
                        continue
                    if side == -1 and trough_price is not None and px >= trough_price * (1 + self.risk.trailing_stop_pct):
                        close_trade(ts, px, "trailing_stop")
                        equity_curve.append({"timestamp": ts, "equity": capital, "close": px, "position": 0})
                        continue
                if self.risk.max_holding_bars is not None and bars_held >= self.risk.max_holding_bars:
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
                initial_notional = determine_notional(capital, atr, px)
                open_notional = initial_notional
                bars_held = 0
                peak_price = px
                trough_price = px
                stepped_stop_anchor = px
                atr_at_entry = atr
                break_even_armed = False
                partial_taken = False
                continue
            if signal != side:
                close_trade(ts, px, "reverse_signal")
                side = signal
                entry_price = px
                entry_time = ts
                initial_notional = determine_notional(capital, atr, px)
                open_notional = initial_notional
                bars_held = 0
                peak_price = px
                trough_price = px
                stepped_stop_anchor = px
                atr_at_entry = atr
                break_even_armed = False
                partial_taken = False

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
        }
