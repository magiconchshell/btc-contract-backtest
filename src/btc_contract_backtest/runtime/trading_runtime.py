from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, ExecutionConfig, LiveRiskConfig, RiskConfig
from btc_contract_backtest.engine.simulator_core import SimulatorCore
from btc_contract_backtest.live.watchdog import HeartbeatWatchdog
from btc_contract_backtest.strategies.base import BaseStrategy


@dataclass
class RuntimeContext:
    contract: ContractSpec
    account: AccountConfig
    risk: RiskConfig
    execution: ExecutionConfig
    live_risk: LiveRiskConfig
    timeframe: str


class TradingRuntime:
    def __init__(
        self,
        contract: ContractSpec,
        account: AccountConfig,
        risk: RiskConfig,
        strategy: BaseStrategy,
        timeframe: str = "1h",
        execution: ExecutionConfig | None = None,
        live_risk: LiveRiskConfig | None = None,
    ):
        self.context = RuntimeContext(
            contract=contract,
            account=account,
            risk=risk,
            execution=execution or ExecutionConfig(),
            live_risk=live_risk or LiveRiskConfig(),
            timeframe=timeframe,
        )
        self.strategy = strategy
        self.core = SimulatorCore(contract, account, risk, self.context.execution, self.context.live_risk)
        self.watchdog = HeartbeatWatchdog(self.context.live_risk.heartbeat_timeout_seconds, self.context.live_risk.max_consecutive_failures)

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def fetch_recent_data(self, limit: int = 300) -> pd.DataFrame:
        raise NotImplementedError

    def enrich_snapshot(self, signal_df: pd.DataFrame, latest) -> object:
        snapshot = self.core.snapshot_from_bar(signal_df.index[-1], latest)
        return snapshot

    def on_blocked_snapshot(self, payload: dict):
        return payload

    def on_hold(self, payload: dict):
        return payload

    def on_decision(self, payload: dict):
        return payload

    def build_intended_order(self, signal: int, snapshot, atr: Optional[float]):
        if signal == 0:
            return None
        notional = self.core.determine_notional(snapshot.close, atr)
        qty = 0.0 if snapshot.close <= 0 else notional / snapshot.close
        return {
            "symbol": self.context.contract.symbol,
            "signal": signal,
            "quantity": qty,
            "notional": notional,
            "price_reference": snapshot.close,
        }

    def step(self):
        if self.watchdog.state.halted:
            return {"event": "halted", "reason": self.watchdog.state.halt_reason, "timestamp": self.now_iso()}

        self.watchdog.beat()
        df = self.fetch_recent_data()
        signal_df = self.strategy.generate_signals(df)
        latest = signal_df.iloc[-1]
        snapshot = self.enrich_snapshot(signal_df, latest)

        if not self.core.check_snapshot_safety(snapshot):
            return self.on_blocked_snapshot({"event": "blocked", "reason": "snapshot_safety_failed", "timestamp": self.now_iso()})

        signal = int(latest.get("signal", 0))
        if signal == 0:
            return self.on_hold({"event": "hold", "reason": "no_signal", "timestamp": self.now_iso()})

        atr = None if pd.isna(latest.get("atr")) else float(latest.get("atr"))
        intended = self.build_intended_order(signal, snapshot, atr)
        return self.on_decision({
            "event": "decision",
            "timestamp": self.now_iso(),
            "signal": signal,
            "snapshot": {
                "close": snapshot.close,
                "bid": snapshot.bid,
                "ask": snapshot.ask,
                "mark_price": snapshot.mark_price,
                "stale": snapshot.stale,
            },
            "intended_order": intended,
        })
