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
        equity_curve = []
        trades = []
        liquidation_events = 0

        for ts, row in signal_df.iterrows():
            px = float(row["close"])
            unrealized = 0.0
            if side != 0 and entry_price is not None:
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
                        "reason": "liquidation",
                        "pnl_after_costs": -(margin_used),
                    })
                    capital -= margin_used
                    side = 0
                    entry_price = None
                    entry_time = None
                    notional = 0.0
                    liquidation_events += 1
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
                continue
            if signal != side:
                gross = ((px - entry_price) / entry_price) * notional * self.contract.leverage * side
                fees = (notional * self.account.taker_fee_rate) * 2
                funding = notional * (self.account.funding_rate_annual / 365)
                pnl = gross - fees - funding
                capital += pnl
                trades.append({
                    "entry_time": entry_time,
                    "exit_time": ts,
                    "entry_price": entry_price,
                    "exit_price": px,
                    "position": side,
                    "reason": "reverse_signal",
                    "gross_pnl": gross,
                    "fees": fees,
                    "funding": funding,
                    "pnl_after_costs": pnl,
                })
                side = signal
                entry_price = px
                entry_time = ts
                notional = capital * self.risk.max_position_notional_pct

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
