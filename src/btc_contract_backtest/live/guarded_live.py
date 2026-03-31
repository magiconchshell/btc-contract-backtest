from __future__ import annotations

import uuid
from datetime import datetime, timezone

from btc_contract_backtest.engine.execution_models import Order, OrderSide, OrderType
from btc_contract_backtest.live.audit_logger import AuditLogger
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter
from btc_contract_backtest.live.governance import AlertSink, GovernancePolicy, OperatorApprovalQueue
from btc_contract_backtest.live.submit_ledger import SubmitAttempt, SubmitIntent, SubmitLedger


class GuardedLiveExecutor:
    def __init__(
        self,
        adapter: ExchangeExecutionAdapter,
        governance: GovernancePolicy,
        approvals: OperatorApprovalQueue,
        alerts: AlertSink,
        audit: AuditLogger,
        submit_ledger: SubmitLedger | None = None,
    ):
        self.adapter = adapter
        self.governance = governance
        self.approvals = approvals
        self.alerts = alerts
        self.audit = audit
        self.submit_ledger = submit_ledger or SubmitLedger()

    def submit_intended_order(
        self,
        *,
        symbol: str,
        signal: int,
        quantity: float,
        notional: float,
        stale: bool,
        reconcile_ok: bool,
        watchdog_halted: bool,
        emergency_stop: bool = False,
        maintenance: bool = False,
        current_daily_loss_pct: float = 0.0,
    ):
        request_id = str(uuid.uuid4())
        client_order_id = request_id
        intent = SubmitIntent(
            request_id=request_id,
            client_order_id=client_order_id,
            symbol=symbol,
            signal=signal,
            quantity=quantity,
            notional=notional,
            state="created",
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        self.submit_ledger.upsert(intent)
        decision = self.governance.evaluate(
            symbol=symbol,
            notional=notional,
            signal=signal,
            stale=stale,
            reconcile_ok=reconcile_ok,
            watchdog_halted=watchdog_halted,
            quantity=quantity,
            emergency_stop=emergency_stop,
            maintenance=maintenance,
            current_daily_loss_pct=current_daily_loss_pct,
        )
        if not decision.allowed:
            if decision.requires_approval:
                self.submit_ledger.mark_state(request_id, state="pending_approval", timestamp=datetime.now(timezone.utc).isoformat(), metadata={"reason": decision.reason})
                self.approvals.request_approval(request_id, {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "symbol": symbol,
                    "signal": signal,
                    "quantity": quantity,
                    "notional": notional,
                    "decision": decision.reason,
                    "client_order_id": client_order_id,
                })
                self.audit.log("governance_pending_approval", {"request_id": request_id, "client_order_id": client_order_id, "symbol": symbol, "signal": signal, "quantity": quantity, "notional": notional})
                return {"status": "pending_approval", "request_id": request_id, "client_order_id": client_order_id, "reason": decision.reason}
            self.submit_ledger.mark_state(request_id, state="blocked", timestamp=datetime.now(timezone.utc).isoformat(), error=decision.reason)
            self.alerts.emit("governance_block", {"timestamp": datetime.now(timezone.utc).isoformat(), "reason": decision.reason, "symbol": symbol})
            self.audit.log("governance_block", {"request_id": request_id, "client_order_id": client_order_id, "reason": decision.reason, "symbol": symbol, "signal": signal})
            return {"status": "blocked", "request_id": request_id, "client_order_id": client_order_id, "reason": decision.reason}

        side = OrderSide.BUY if signal == 1 else OrderSide.SELL
        existing = self.submit_ledger.get_by_client_order_id(client_order_id)
        if existing and existing.get("state") in {"submitted", "acked", "partial", "filled"}:
            self.audit.log("governance_submit_deduped", {"request_id": request_id, "client_order_id": client_order_id, "existing": existing})
            return {"status": "deduped", "request_id": request_id, "client_order_id": client_order_id, "existing": existing}

        order = Order(
            order_id=request_id,
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            client_order_id=client_order_id,
        )
        self.submit_ledger.mark_state(request_id, state="submit_pending", timestamp=datetime.now(timezone.utc).isoformat())
        self.submit_ledger.append_attempt(request_id, SubmitAttempt(timestamp=datetime.now(timezone.utc).isoformat(), action="submit", status="started", payload={"symbol": symbol, "signal": signal, "quantity": quantity, "notional": notional}))
        result = self.adapter.submit_order(order)
        if result.ok:
            exchange_order_id = (result.payload or {}).get("id") if isinstance(result.payload, dict) else None
            self.submit_ledger.append_attempt(request_id, SubmitAttempt(timestamp=datetime.now(timezone.utc).isoformat(), action="submit", status="ok", payload={"response": result.payload}))
            self.submit_ledger.mark_state(request_id, state="submitted", timestamp=datetime.now(timezone.utc).isoformat(), exchange_order_id=exchange_order_id)
            self.audit.log("governance_submit", {"request_id": request_id, "client_order_id": client_order_id, "symbol": symbol, "signal": signal, "quantity": quantity, "notional": notional, "response": result.payload})
            return {"status": "submitted", "request_id": request_id, "client_order_id": client_order_id, "response": result.payload, "order": order}
        self.submit_ledger.append_attempt(request_id, SubmitAttempt(timestamp=datetime.now(timezone.utc).isoformat(), action="submit", status="error", payload={"error": result.error}))
        remote_lookup = self.adapter.fetch_open_orders_by_client_order_id(client_order_id)
        if remote_lookup.ok and remote_lookup.payload:
            remote_order = remote_lookup.payload[0]
            exchange_order_id = remote_order.get("id")
            self.submit_ledger.mark_state(request_id, state="submitted", timestamp=datetime.now(timezone.utc).isoformat(), exchange_order_id=exchange_order_id, metadata={"recovered_from": "client_order_lookup"})
            self.audit.log("governance_submit_recovered", {"request_id": request_id, "client_order_id": client_order_id, "response": remote_order, "original_error": result.error})
            return {"status": "submitted_recovered", "request_id": request_id, "client_order_id": client_order_id, "response": remote_order, "order": order}
        self.submit_ledger.mark_state(request_id, state="unknown", timestamp=datetime.now(timezone.utc).isoformat(), error=result.error)
        self.alerts.emit("governance_submit_failed", {"timestamp": datetime.now(timezone.utc).isoformat(), "request_id": request_id, "error": result.error})
        self.audit.log("governance_submit_failed", {"request_id": request_id, "client_order_id": client_order_id, "error": result.error})
        return {"status": "submit_failed", "request_id": request_id, "client_order_id": client_order_id, "error": result.error}

    def governed_cancel_replace(self, cancel_order_id: str, symbol: str, new_signal: int, quantity: float, notional: float):
        side = OrderSide.BUY if new_signal == 1 else OrderSide.SELL
        new_order = Order(
            order_id=str(uuid.uuid4()),
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            client_order_id=str(uuid.uuid4()),
        )
        result = self.adapter.cancel_replace_order(cancel_order_id, new_order)
        if result.ok:
            self.audit.log("governed_cancel_replace", {"cancel_order_id": cancel_order_id, "new_signal": new_signal, "quantity": quantity, "notional": notional, "response": result.payload})
            return {"status": "cancel_replaced", "response": result.payload}
        self.alerts.emit("governed_cancel_replace_failed", {"timestamp": datetime.now(timezone.utc).isoformat(), "cancel_order_id": cancel_order_id, "error": result.error})
        self.audit.log("governed_cancel_replace_failed", {"cancel_order_id": cancel_order_id, "error": result.error})
        return {"status": "cancel_replace_failed", "error": result.error}

    def process_approved_request(self, request_id: str):
        if self.approvals.is_rejected(request_id):
            self.submit_ledger.mark_state(request_id, state="rejected", timestamp=datetime.now(timezone.utc).isoformat(), error="operator_rejected")
            self.audit.log("governance_request_rejected", {"request_id": request_id})
            return {"status": "rejected", "request_id": request_id}
        if not self.approvals.is_approved(request_id):
            return {"status": "not_approved", "request_id": request_id}
        req = self.approvals.consume_request(request_id)
        if req is None:
            return {"status": "missing_request", "request_id": request_id}
        self.submit_ledger.mark_state(request_id, state="approved", timestamp=datetime.now(timezone.utc).isoformat())
        existing = self.submit_ledger.get(request_id)
        if existing and existing.get("state") in {"submitted", "acked", "partial", "filled"}:
            return {"status": "deduped", "request_id": request_id, "existing": existing}
        return self.submit_intended_order(
            symbol=req["symbol"],
            signal=req["signal"],
            quantity=req["quantity"],
            notional=req["notional"],
            stale=False,
            reconcile_ok=True,
            watchdog_halted=False,
            emergency_stop=False,
            maintenance=False,
            current_daily_loss_pct=0.0,
        )
