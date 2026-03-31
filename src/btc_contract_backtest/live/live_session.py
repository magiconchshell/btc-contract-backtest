from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import ccxt
import pandas as pd

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, ExecutionConfig, LiveRiskConfig, RiskConfig
from btc_contract_backtest.live.audit_logger import AuditLogger
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter
from btc_contract_backtest.live.governance import AlertSink, GovernancePolicy, GovernanceState, OperatorApprovalQueue, TradingMode
from btc_contract_backtest.live.guarded_live import GuardedLiveExecutor
from btc_contract_backtest.live.incident_store import IncidentRecord, IncidentStore
from btc_contract_backtest.live.event_stream import EventDrivenExecutionSource, EventRecorder
from btc_contract_backtest.live.live_recovery import LiveSessionRecovery
from btc_contract_backtest.live.order_monitor import OrderLifecycleMonitor
from btc_contract_backtest.live.recovery_orchestrator import RecoveryOrchestrator
from btc_contract_backtest.live.submit_ledger import SubmitLedger
from btc_contract_backtest.engine.execution_models import MarketSnapshot
from btc_contract_backtest.runtime.calibration_engine import sample_from_execution
from btc_contract_backtest.runtime.calibration_store import CalibrationSampleStore
from btc_contract_backtest.runtime.order_state_bridge import apply_local_submit, apply_remote_status, canonical_record_from_order
from btc_contract_backtest.runtime.runtime_state_store import JsonRuntimeStateStore
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
        execution: Optional[ExecutionConfig] = None,
        live_risk: Optional[LiveRiskConfig] = None,
        mode: TradingMode = TradingMode.APPROVAL_REQUIRED,
        audit_log: str = "live_governance_audit.jsonl",
        approval_file: str = "operator_approvals.json",
        governance_state_file: str = "governance_state.json",
        alerts_file: str = "live_alerts.jsonl",
        state_file: str = "live_session_state.json",
    ):
        super().__init__(
            contract,
            account,
            risk,
            strategy,
            timeframe,
            execution,
            live_risk,
            persistence=JsonRuntimeStateStore(state_file, mode="governed_live", symbol=contract.symbol, leverage=contract.leverage),
        )
        self.exchange = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})
        self.adapter = ExchangeExecutionAdapter(self.exchange, contract.symbol, max_retries=self.context.live_risk.max_consecutive_failures)
        self.audit = AuditLogger(audit_log)
        self.alerts = AlertSink(alerts_file)
        self.approvals = OperatorApprovalQueue(approval_file)
        self.gov_state = GovernanceState(governance_state_file)
        self.incidents = IncidentStore()
        self.recovery = LiveSessionRecovery(state_file)
        self.calibration_store = CalibrationSampleStore()
        loader = getattr(self.persistence, "load_normalized_state", None)
        recovered = loader() if callable(loader) else self.recovery.load()
        wd = recovered.get("watchdog") or {}
        self.watchdog.state.last_heartbeat_at = wd.get("last_heartbeat_at")
        self.watchdog.state.consecutive_failures = wd.get("consecutive_failures", 0)
        self.watchdog.state.halted = wd.get("halted", False)
        self.watchdog.state.halt_reason = wd.get("halt_reason")
        state = self.gov_state.load()
        current_mode = TradingMode(state.get("mode", mode.value))
        self.submit_ledger = SubmitLedger(str(Path(state_file).with_name("submit_ledger.json")))
        self.event_source = EventDrivenExecutionSource(EventRecorder(str(Path(state_file).with_name("execution_events.jsonl"))))
        self.policy = GovernancePolicy(risk, self.context.live_risk, current_mode, contract=contract)
        self.executor = GuardedLiveExecutor(self.adapter, self.policy, self.approvals, self.alerts, self.audit, submit_ledger=self.submit_ledger, event_source=self.event_source)
        self.order_monitor = OrderLifecycleMonitor(self.adapter, self.alerts, self.audit)
        self.recovery_orchestrator = RecoveryOrchestrator(self.adapter, self.submit_ledger)
        self._recovery_report = self.recovery_orchestrator.recover(local_orders=recovered.get("orders", []))

    def save_state(self, payload: Optional[dict] = None):
        store = self.state_store()
        if hasattr(store, "set_mode"):
            store.set_mode("governed_live")
            store.set_governance_state(self.gov_state.load())
            store.set_last_runtime_snapshot(payload or {})
            store.set_reconcile_report((payload or {}).get("reconcile_report") or {})
            store.set_submit_ledger(self.submit_ledger.load())
            store.set_state_fields(recovery_report=self._recovery_report.to_dict() if hasattr(self._recovery_report, "to_dict") else self._recovery_report, execution_events=self.event_source.replay())
            store.set_watchdog({
                "last_heartbeat_at": self.watchdog.state.last_heartbeat_at,
                "consecutive_failures": self.watchdog.state.consecutive_failures,
                "halted": self.watchdog.state.halted,
                "halt_reason": self.watchdog.state.halt_reason,
            })
            store.set_state_fields(updated_at=datetime.now(timezone.utc).isoformat())
            store.flush()
            return
        self.persist_runtime_state(updated_at=datetime.now(timezone.utc).isoformat())

    def fetch_recent_data(self, limit: int = 300):
        rows = self.exchange.fetch_ohlcv(self.context.contract.symbol, timeframe=self.context.timeframe, limit=limit)
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df

    def enrich_snapshot(self, signal_df: pd.DataFrame, latest) -> MarketSnapshot:
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
        self.event_source.emit("runtime_decision", self.now_iso(), {"signal": payload.get("signal"), "snapshot": payload.get("snapshot") or {}, "intended_order": payload.get("intended_order") or {}}, source="runtime")
        if state.get("emergency_stop"):
            halted = {"event": "halted", "reason": "emergency_stop", "timestamp": self.now_iso()}
            self.audit.log("live_session_halt", halted)
            self.alerts.emit("pilot_blocking", {"timestamp": self.now_iso(), "reason": "emergency_stop"}, severity="critical")
            self.incidents.append(IncidentRecord(incident_id=f"incident-{int(time.time())}", incident_type="governance", severity="critical", state="detected", timestamp=self.now_iso(), summary="Emergency stop active", metadata=halted))
            self.save_state(halted)
            return halted
        if state.get("maintenance"):
            halted = {"event": "halted", "reason": "maintenance_mode", "timestamp": self.now_iso()}
            self.audit.log("live_session_halt", halted)
            self.alerts.emit("pilot_blocking", {"timestamp": self.now_iso(), "reason": "maintenance_mode"}, severity="critical")
            self.incidents.append(IncidentRecord(incident_id=f"incident-{int(time.time())}", incident_type="maintenance", severity="warning", state="detected", timestamp=self.now_iso(), summary="Maintenance mode active", metadata=halted))
            self.save_state(halted)
            return halted

        intended = payload.get("intended_order") or {}
        local_orders = []
        store = self.state_store()
        if hasattr(store, "get_state"):
            local_orders = store.get_state().get("orders", [])
        balance = self.adapter.fetch_balance()
        available_margin = None
        if balance.ok and isinstance(balance.payload, dict):
            usdt_raw = balance.payload.get("USDT")
            usdt = usdt_raw if isinstance(usdt_raw, dict) else {}
            available_margin = usdt.get("free")
        local_position = {
            "side": self.core.position.side,
            "quantity": abs(self.core.position.quantity),
            "entry_price": self.core.position.entry_price,
        }
        open_local_orders = len([o for o in local_orders if str(o.get("state") or o.get("status") or "").lower() not in {"filled", "canceled", "rejected", "expired"}])
        reconcile = self.adapter.reconcile_state(self.core.position.side, open_local_orders, local_position=local_position, local_orders=local_orders)
        reconcile_payload = reconcile.payload if isinstance(reconcile.payload, dict) else {}
        reconcile_ok = bool(reconcile.ok and reconcile_payload.get("ok", False))
        payload["reconcile_report"] = reconcile.payload if reconcile.ok else {"ok": False, "error": reconcile.error}
        result = self.executor.submit_intended_order(
            symbol=self.context.contract.symbol,
            signal=payload["signal"],
            quantity=float(intended.get("quantity", 0.0)),
            notional=float(intended.get("notional", 0.0)),
            stale=payload["snapshot"].get("stale", False),
            reconcile_ok=reconcile_ok,
            watchdog_halted=self.watchdog.state.halted,
            available_margin=None if available_margin is None else float(available_margin),
            leverage=self.context.contract.leverage,
            position_side=self.core.position.side,
            account_mode="one_way",
            current_open_positions=0 if self.core.position.side == 0 else 1,
            emergency_stop=state.get("emergency_stop", False),
            maintenance=state.get("maintenance", False),
            current_daily_loss_pct=0.0,
        )
        if hasattr(store, "append_operator_action"):
            store.append_operator_action({
                "timestamp": self.now_iso(),
                "action": "submit_intended_order",
                "signal": payload["signal"],
                "quantity": float(intended.get("quantity", 0.0)),
                "notional": float(intended.get("notional", 0.0)),
                "result": result.get("status"),
            })
        order = result.get("order") if isinstance(result, dict) else None
        if order is not None and hasattr(store, "upsert_order"):
            record = canonical_record_from_order(order, submission_mode="governed_live")
            record = apply_local_submit(record, timestamp=order.created_at, payload={"signal": payload["signal"], "quantity": float(intended.get("quantity", 0.0))})
            remote_status = "new"
            if result.get("status") in {"submitted_recovered", "submitted"}:
                remote_status = "new"
            record = apply_remote_status(
                record,
                status=remote_status,
                timestamp=self.now_iso(),
                payload=result.get("response") or {},
                exchange_order_id=(result.get("response") or {}).get("id"),
            )
            store.upsert_order(record.to_dict())
            monitor_result = self.order_monitor.inspect(order, record=record)
            if monitor_result.get("record") is not None:
                store.upsert_order(monitor_result["record"].to_dict())
            payload["post_submit_monitor"] = {k: v for k, v in monitor_result.items() if k != "record"}
            if monitor_result.get("status") in {"stuck_open", "partial_fill"}:
                replace_result = self.executor.governed_cancel_replace(
                    order.order_id,
                    symbol=self.context.contract.symbol,
                    new_signal=payload["signal"],
                    quantity=float(intended.get("quantity", 0.0)),
                    notional=float(intended.get("notional", 0.0)),
                    record=monitor_result.get("record"),
                )
                payload["cancel_replace"] = {k: v for k, v in replace_result.items() if k not in {"record", "new_order"}}
                if replace_result.get("record") is not None:
                    store.upsert_order(replace_result["record"].to_dict())
                new_order = replace_result.get("new_order")
                if new_order is not None:
                    replacement_record = canonical_record_from_order(new_order, submission_mode="governed_live")
                    replacement_record = apply_local_submit(replacement_record, timestamp=new_order.created_at, payload={"replaces": order.order_id})
                    store.upsert_order(replacement_record.to_dict())
            sample = sample_from_execution(
                timestamp=self.now_iso(),
                symbol=self.context.contract.symbol,
                mode="governed_live",
                side=order.side.value,
                order_type=order.order_type.value,
                quantity=order.quantity,
                notional=float(intended.get("notional", 0.0)),
                reference_price=float(payload["snapshot"]["close"]),
                executed_price=float(payload["snapshot"]["ask"] if order.side.value == "buy" else payload["snapshot"]["bid"] or payload["snapshot"]["close"]),
                fill_quantity=order.quantity,
                spread_bps=(abs((payload["snapshot"].get("ask") or payload["snapshot"]["close"]) - (payload["snapshot"].get("bid") or payload["snapshot"]["close"])) / payload["snapshot"]["close"] * 10000) if payload["snapshot"]["close"] > 0 else None,
                depth_notional=self.context.execution.simulated_depth_notional,
                queue_model=self.context.execution.queue_priority_model,
                funding_rate=payload["snapshot"].get("funding_rate"),
                funding_cost=None,
                volatility_bucket="normal",
                latency_ms=self.context.execution.latency_ms,
                stale=payload["snapshot"].get("stale", False),
                metadata={"calibration_version": "t4-v1", "request_id": result.get("request_id")},
            )
            self.calibration_store.append(sample)
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
