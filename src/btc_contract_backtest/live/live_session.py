from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Optional

import ccxt
import pandas as pd

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, ExecutionConfig, LiveRiskConfig, RiskConfig
from btc_contract_backtest.engine.simulator_core import SimulatorCore
from btc_contract_backtest.live.audit_logger import AuditLogger
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter
from btc_contract_backtest.live.governance import AlertSink, GovernancePolicy, GovernanceState, OperatorApprovalQueue, TradingMode
from btc_contract_backtest.live.guarded_live import GuardedLiveExecutor
from btc_contract_backtest.live.live_recovery import LiveSessionRecovery
from btc_contract_backtest.live.watchdog import HeartbeatWatchdog
from btc_contract_backtest.strategies.base import BaseStrategy


class GovernedLiveSession:
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
        self.contract = contract
        self.account = account
        self.risk = risk
        self.strategy = strategy
        self.timeframe = timeframe
        self.execution = execution or ExecutionConfig()
        self.live_risk = live_risk or LiveRiskConfig()
        self.exchange = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})
        self.adapter = ExchangeExecutionAdapter(self.exchange, contract.symbol, max_retries=self.live_risk.max_consecutive_failures)
        self.watchdog = HeartbeatWatchdog(self.live_risk.heartbeat_timeout_seconds, self.live_risk.max_consecutive_failures)
        self.core = SimulatorCore(contract, account, risk, self.execution, self.live_risk)
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
        self.policy = GovernancePolicy(risk, live_risk, current_mode)
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
        rows = self.exchange.fetch_ohlcv(self.contract.symbol, timeframe=self.timeframe, limit=limit)
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df

    def step(self):
        state = self.gov_state.load()
        if state.get("emergency_stop"):
            payload = {"event": "halted", "reason": "emergency_stop", "timestamp": datetime.now(timezone.utc).isoformat()}
            self.audit.log("live_session_halt", payload)
            self.save_state(payload)
            return payload
        if state.get("maintenance"):
            payload = {"event": "halted", "reason": "maintenance_mode", "timestamp": datetime.now(timezone.utc).isoformat()}
            self.audit.log("live_session_halt", payload)
            self.save_state(payload)
            return payload

        self.watchdog.beat()
        df = self.fetch_recent_data()
        signal_df = self.strategy.generate_signals(df)
        latest = signal_df.iloc[-1]
        snapshot = self.core.snapshot_from_bar(signal_df.index[-1], latest)
        ticker = self.exchange.fetch_ticker(self.contract.symbol)
        snapshot.mark_price = float(ticker.get("last") or snapshot.close)
        snapshot.bid = float(ticker.get("bid") or snapshot.bid or snapshot.close)
        snapshot.ask = float(ticker.get("ask") or snapshot.ask or snapshot.close)
        if not self.core.check_snapshot_safety(snapshot):
            payload = {"event": "blocked", "reason": "snapshot_safety_failed", "timestamp": datetime.now(timezone.utc).isoformat()}
            self.audit.log("live_session_blocked", payload)
            self.save_state(payload)
            return payload

        signal = int(latest.get("signal", 0))
        if signal == 0:
            payload = {"event": "hold", "reason": "no_signal", "timestamp": datetime.now(timezone.utc).isoformat()}
            self.audit.log("live_session_hold", payload)
            self.save_state(payload)
            return payload

        atr = None if pd.isna(latest.get("atr")) else float(latest.get("atr"))
        notional = self.core.determine_notional(snapshot.close, atr)
        qty = 0.0 if snapshot.close <= 0 else notional / snapshot.close
        reconcile = self.adapter.reconcile_state(self.core.position.side, 0)
        reconcile_ok = bool(reconcile.ok and reconcile.payload and reconcile.payload.get("ok", False))
        result = self.executor.submit_intended_order(
            symbol=self.contract.symbol,
            signal=signal,
            quantity=qty,
            notional=notional,
            stale=snapshot.stale,
            reconcile_ok=reconcile_ok,
            watchdog_halted=self.watchdog.state.halted,
            emergency_stop=state.get("emergency_stop", False),
            maintenance=state.get("maintenance", False),
            current_daily_loss_pct=0.0,
        )
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "signal": signal, "quantity": qty, "notional": notional, "result": result}
        self.audit.log("live_session_decision", payload)
        self.save_state(payload)
        return result

    def run_loop(self, interval_seconds: int = 60, iterations: Optional[int] = None):
        count = 0
        while True:
            if self.watchdog.check_timeout():
                payload = {"event": "halted", "reason": "heartbeat_timeout", "timestamp": datetime.now(timezone.utc).isoformat()}
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
