from __future__ import annotations
from typing import Optional

import ccxt
import numpy as np
import pandas as pd

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, ExecutionConfig, LiveRiskConfig, RiskConfig
from btc_contract_backtest.runtime.backtest_runtime import BacktestRuntime


class FuturesBacktestEngine:
    def __init__(
        self,
        contract: ContractSpec,
        account: AccountConfig,
        risk: RiskConfig,
        timeframe: str = "1h",
        execution: Optional[ExecutionConfig] = None,
        live_risk: Optional[LiveRiskConfig] = None,
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

        class _BacktestStrategy:
            def name(self) -> str:
                return "backtest_runtime_strategy"

            def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
                return signal_df.loc[df.index].copy()

        runtime = BacktestRuntime(
            market_data=signal_df,
            contract=self.contract,
            account=self.account,
            risk=self.risk,
            strategy=_BacktestStrategy(),
            timeframe=self.timeframe,
            execution=self.execution,
            live_risk=self.live_risk,
        )
        return runtime.run()

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
            "calibration_mode": getattr(self.execution, "calibration_mode", "calibrated"),
            "calibration_version": getattr(self.execution, "calibration_version", "t4-v1"),
        }
