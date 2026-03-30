from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Optional

import ccxt
import pandas as pd

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, ExecutionConfig, LiveRiskConfig, RiskConfig
from btc_contract_backtest.live.audit_logger import AuditLogger
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter
from btc_contract_backtest.live.governance import AlertSink, GovernancePolicy, GovernanceState, OperatorApprovalQueue, TradingMode
from btc_contract_backtest.live.guarded_live import GuardedLiveExecutor
from btc_contract_backtest.live.live_recovery import LiveSessionRecovery
from btc_contract_backtest.runtime.trading_runtime import TradingRuntime
from btc_contract_backtest.strategies.base import BaseStrategy


class GovernedLiveSession(TradingRuntime):
    def __init__(
        self,
        contract: ContractSpec,
        account: AccountConfig,
        risk: RiskConfig,
        strategy: BaseStrategy,
        timeframe: str = "1h",
        execution: ExecutionConfig | None = None,
        live_risk: LiveRiskConfig | None = None,
        mode: TradingMode = TradingMode.APPROVAL_REQUIRED,
        audit_log: str = "live_governance_audit.jsonl",
        approval_file: str = "operator_approvals.json",
        governance_state_file: str = "governance_state.json",
        alerts_file: str = "live_alerts.jsonl",
        state_file: str = "live_session_state.json",
    ):
        super().__init__(contract, account, risk, strategy, timeframe, execution, live_risk)
        self.exchange = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})
        self.adapter = ExchangeExecutionAdapter(self.exchange, contract.symbol, max_retries=self.context.live_risk.max_consecutive_failures)
        self.audit = AuditLogger(audit_log)
        self.alerts = AlertSink(alerts_file)
        self.approvals = OperatorApprovalQueue(approval_file)
        self.gov_state = GovernanceState(governance_state_file)
        self.recovery = LiveSessionRecovery(state_file)
        recovered = self.recovery.load()
        self.watchdog.state.last_heartbeat_at = recovered.get("last_heartbeat_at")
        self.watchdog.state.consecutive_failures = recovered.get("consecutive_failures", 0)
        self.watchdog.state.halted = recovered.get("halted", False)
        self.watchdog.state.halt_reason = recovered.get("halt_reason")
        state = self.gov_state.load()
        current_mode = TradingMode(state.get("mode", mode.value))
        self.policy = GovernancePolicy(risk, self.context.live_risk, current_mode)
        self.executor = GuardedLiveExecutor(self.adapter, self.policy, self.approvals, self.alerts, self.audit)

    def save_state(self, payload: dict | None = None):
        self.recovery.save({
            "last_heartbeat_at": self.watchdog.state.last_heartbeat_at,
            "consecutive_failures": self.watchdog.state.consecutive_failures,
            "halted": self.watchdog.state.halted,
            "halt_reason": self.watchdog.state.halt_reason,
            "last_payload": payload,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    def fetch_recent_data(self, limit: int = 300):
        rows = self.exchange.fetch_ohlcv(self.context.contract.symbol, timeframe=self.context.timeframe, limit=limit)
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df

    def enrich_snapshot(self, signal_df: pd.DataFrame, latest):
        snapshot = super().enrich_snapshot(signal_df, latest)
        ticker = self.exchange.fetch_ticker(self.context.contract.symbol)
        snapshot.mark_price = float(ticker.get("last") or snapshot.close)
        snapshot.bid = float(ticker.get("bid") or snapshot.bid or snapshot.close)
        snapshot.ask = float(ticker.get("ask") or snapshot.ask or snapshot.close)
        return snapshot

    def on_blocked_snapshot(self, payload: dict):
        self.audit.log("live_session_blocked", payload)
        self.save_state(payload)
        return payload

    def on_hold(self, payload: dict):
        self.audit.log("live_session_hold", payload)
        self.save_state(payload)
        return payload

    def on_decision(self, payload: dict):
        state = self.gov_state.load()
        if state.get("emergency_stop"):
            halted = {"event": "halted", "reason": "emergency_stop", "timestamp": self.now_iso()}
            self.audit.log("live_session_halt", halted)
            self.save_state(halted)
            return halted
        if state.get("maintenance"):
            halted = {"event": "halted", "reason": "maintenance_mode", "timestamp": self.now_iso()}
            self.audit.log("live_session_halt", halted)
            self.save_state(halted)
            return halted

        intended = payload.get("intended_order") or {}
        reconcile = self.adapter.reconcile_state(self.core.position.side, 0)
        reconcile_ok = bool(reconcile.ok and reconcile.payload and reconcile.payload.get("ok", False))
        result = self.executor.submit_intended_order(
            symbol=self.context.contract.symbol,
            signal=payload["signal"],
            quantity=float(intended.get("quantity", 0.0)),
            notional=float(intended.get("notional", 0.0)),
            stale=payload["snapshot"].get("stale", False),
            reconcile_ok=reconcile_ok,
            watchdog_halted=self.watchdog.state.halted,
            emergency_stop=state.get("emergency_stop", False),
            maintenance=state.get("maintenance", False),
            current_daily_loss_pct=0.0,
        )
        payload["result"] = result
        self.audit.log("live_session_decision", payload)
        self.save_state(payload)
        return payload

    def step(self):
        state = self.gov_state.load()
        if state.get("emergency_stop"):
            payload = {"event": "halted", "reason": "emergency_stop", "timestamp": self.now_iso()}
            self.audit.log("live_session_halt", payload)
            self.save_state(payload)
            return payload
        if state.get("maintenance"):
            payload = {"event": "halted", "reason": "maintenance_mode", "timestamp": self.now_iso()}
            self.audit.log("live_session_halt", payload)
            self.save_state(payload)
            return payload
        return super().step()

    def run_loop(self, interval_seconds: int = 60, iterations: Optional[int] = None):
        count = 0
        while True:
            if self.watchdog.check_timeout():
                payload = {"event": "halted", "reason": "heartbeat_timeout", "timestamp": self.now_iso()}
                self.audit.log("live_session_halt", payload)
                self.save_state(payload)
                print(json.dumps(payload, indent=2, default=str))
                break
            payload = self.step()
            print(json.dumps(payload, indent=2, default=str))
            count += 1
            if iterations is not None and count >= iterations:
                break
            time.sleep(interval_seconds)
