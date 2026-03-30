from __future__ import annotations

import uuid
from datetime import datetime, timezone

from btc_contract_backtest.engine.execution_models import Order, OrderSide, OrderType
from btc_contract_backtest.live.audit_logger import AuditLogger
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter
from btc_contract_backtest.live.governance import AlertSink, GovernancePolicy, OperatorApprovalQueue


class GuardedLiveExecutor:
    def __init__(
        self,
        adapter: ExchangeExecutionAdapter,
        governance: GovernancePolicy,
        approvals: OperatorApprovalQueue,
        alerts: AlertSink,
        audit: AuditLogger,
    ):
        self.adapter = adapter
        self.governance = governance
        self.approvals = approvals
        self.alerts = alerts
        self.audit = audit

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
        decision = self.governance.evaluate(
            symbol=symbol,
            notional=notional,
            signal=signal,
            stale=stale,
            reconcile_ok=reconcile_ok,
            watchdog_halted=watchdog_halted,
            emergency_stop=emergency_stop,
            maintenance=maintenance,
            current_daily_loss_pct=current_daily_loss_pct,
        )
        request_id = str(uuid.uuid4())
        if not decision.allowed:
            if decision.requires_approval:
                self.approvals.request_approval(request_id, {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "symbol": symbol,
                    "signal": signal,
                    "quantity": quantity,
                    "notional": notional,
                    "decision": decision.reason,
                })
                self.audit.log("governance_pending_approval", {"request_id": request_id, "symbol": symbol, "signal": signal, "quantity": quantity, "notional": notional})
                return {"status": "pending_approval", "request_id": request_id, "reason": decision.reason}
            self.alerts.emit("governance_block", {"timestamp": datetime.now(timezone.utc).isoformat(), "reason": decision.reason, "symbol": symbol})
            self.audit.log("governance_block", {"request_id": request_id, "reason": decision.reason, "symbol": symbol, "signal": signal})
            return {"status": "blocked", "reason": decision.reason}

        side = OrderSide.BUY if signal == 1 else OrderSide.SELL
        order = Order(
            order_id=request_id,
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            client_order_id=request_id,
        )
        result = self.adapter.submit_order(order)
        if result.ok:
            self.audit.log("governance_submit", {"request_id": request_id, "symbol": symbol, "signal": signal, "quantity": quantity, "notional": notional, "response": result.payload})
            return {"status": "submitted", "request_id": request_id, "response": result.payload, "order": order}
        self.alerts.emit("governance_submit_failed", {"timestamp": datetime.now(timezone.utc).isoformat(), "request_id": request_id, "error": result.error})
        self.audit.log("governance_submit_failed", {"request_id": request_id, "error": result.error})
        return {"status": "submit_failed", "request_id": request_id, "error": result.error}

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
            self.audit.log("governance_request_rejected", {"request_id": request_id})
            return {"status": "rejected", "request_id": request_id}
        if not self.approvals.is_approved(request_id):
            return {"status": "not_approved", "request_id": request_id}
        req = self.approvals.consume_request(request_id)
        if req is None:
            return {"status": "missing_request", "request_id": request_id}
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
