from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, ExecutionConfig, LiveRiskConfig, RiskConfig
from btc_contract_backtest.engine.simulator_core import SimulatorCore
from btc_contract_backtest.live.watchdog import HeartbeatWatchdog
from btc_contract_backtest.runtime.runtime_persistence import InMemoryRuntimePersistence, RuntimePersistence, RuntimeStepRecord
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
        persistence: RuntimePersistence | None = None,
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
        self.persistence = persistence or InMemoryRuntimePersistence()
        self._last_risk_event_count = 0

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def fetch_recent_data(self, limit: int = 300) -> pd.DataFrame:
        raise NotImplementedError

    def enrich_snapshot(self, signal_df: pd.DataFrame, latest) -> object:
        snapshot = self.core.snapshot_from_bar(signal_df.index[-1], latest)
        return snapshot

    def ingest_snapshot(self, limit: int = 300):
        df = self.fetch_recent_data(limit=limit)
        signal_df = self.strategy.generate_signals(df)
        latest = signal_df.iloc[-1]
        snapshot = self.enrich_snapshot(signal_df, latest)
        return signal_df, latest, snapshot

    def evaluate_signal(self, latest) -> int:
        return int(latest.get("signal", 0))

    def evaluate_risk(self, snapshot) -> tuple[bool, str | None]:
        if not self.core.check_snapshot_safety(snapshot):
            return False, "snapshot_safety_failed"
        return True, None

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

    def build_decision_payload(self, signal: int, snapshot, latest) -> dict:
        atr = None if pd.isna(latest.get("atr")) else float(latest.get("atr"))
        intended = self.build_intended_order(signal, snapshot, atr)
        return {
            "event": "decision",
            "timestamp": self.now_iso(),
            "signal": signal,
            "snapshot": {
                "close": snapshot.close,
                "bid": snapshot.bid,
                "ask": snapshot.ask,
                "mark_price": snapshot.mark_price,
                "stale": snapshot.stale,
                "timestamp": snapshot.timestamp,
            },
            "intended_order": intended,
        }

    def persist_payload(self, payload: dict, metadata: dict | None = None):
        record = RuntimeStepRecord(
            timestamp=payload.get("timestamp", self.now_iso()),
            event=payload.get("event", "unknown"),
            signal=payload.get("signal"),
            snapshot=payload.get("snapshot") or {},
            intended_order=payload.get("intended_order"),
            metadata=metadata or {},
        )
        self.persistence.record_runtime_step(record)
        new_events = self.core.risk_events[self._last_risk_event_count :]
        for event in new_events:
            self.persistence.record_risk_event(event)
        self._last_risk_event_count = len(self.core.risk_events)

    def on_blocked_snapshot(self, payload: dict):
        return payload

    def on_hold(self, payload: dict):
        return payload

    def on_decision(self, payload: dict):
        return payload

    def step(self):
        if self.watchdog.state.halted:
            payload = {"event": "halted", "reason": self.watchdog.state.halt_reason, "timestamp": self.now_iso()}
            self.persist_payload(payload, {"stage": "watchdog"})
            return payload

        self.watchdog.beat()
        signal_df, latest, snapshot = self.ingest_snapshot()
        safe, reason = self.evaluate_risk(snapshot)

        if not safe:
            payload = {"event": "blocked", "reason": reason or "risk_check_failed", "timestamp": self.now_iso()}
            self.persist_payload(payload, {"stage": "risk"})
            return self.on_blocked_snapshot(payload)

        signal = self.evaluate_signal(latest)
        if signal == 0:
            payload = {"event": "hold", "reason": "no_signal", "timestamp": self.now_iso(), "snapshot": {"close": snapshot.close, "timestamp": snapshot.timestamp}}
            self.persist_payload(payload, {"stage": "signal"})
            return self.on_hold(payload)

        payload = self.build_decision_payload(signal, snapshot, latest)
        self.persist_payload(payload, {"stage": "decision", "rows": len(signal_df)})
        return self.on_decision(payload)
