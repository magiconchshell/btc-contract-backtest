from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from btc_contract_backtest.engine.execution_models import Order, OrderSide, OrderType
from btc_contract_backtest.live.audit_logger import AuditLogger
from btc_contract_backtest.live.event_stream import EventDrivenExecutionSource
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter
from btc_contract_backtest.live.governance import (
    AlertSink,
    GovernancePolicy,
    OperatorApprovalQueue,
)
from btc_contract_backtest.live.submit_ledger import (
    SubmitAttempt,
    SubmitIntent,
    SubmitLedger,
)
from btc_contract_backtest.runtime.order_state_bridge import (
    apply_local_cancel,
    apply_local_replace,
)
from btc_contract_backtest.runtime.order_state_machine import CanonicalOrderState

logger = logging.getLogger(__name__)


class GuardedLiveExecutor:
    def __init__(
        self,
        adapter: ExchangeExecutionAdapter,
        governance: GovernancePolicy,
        approvals: OperatorApprovalQueue,
        alerts: AlertSink,
        audit: AuditLogger,
        submit_ledger: Optional[SubmitLedger] = None,
        event_source: Optional[EventDrivenExecutionSource] = None,
    ):
        self.adapter = adapter
        self.governance = governance
        self.approvals = approvals
        self.alerts = alerts
        self.audit = audit
        self.submit_ledger = submit_ledger or SubmitLedger()
        self.event_source = event_source or EventDrivenExecutionSource()

    def submit_intended_order(
        self,
        *,
        symbol: str,
        signal: int,
        quantity: float,
        notional: float,
        request_id: Optional[str] = None,
        client_order_id: Optional[str] = None,
        stale: bool,
        reconcile_ok: bool,
        watchdog_halted: bool,
        available_margin: Optional[float] = None,
        leverage: Optional[int] = None,
        position_side: int = 0,
        account_mode: str = "one_way",
        current_open_positions: int = 0,
        emergency_stop: bool = False,
        maintenance: bool = False,
        current_daily_loss_pct: float = 0.0,
        capital: Optional[float] = None,
    ):
        request_id = request_id or str(uuid.uuid4())
        client_order_id = client_order_id or request_id

        # De-duplication: Skip if already in the desired position side
        if signal != 0 and signal == position_side:
            logger.info(
                "Already in position matching signal %d, skipping submission.", signal
            )
            return {
                "status": "already_in_position",
                "request_id": request_id,
                "client_order_id": client_order_id,
            }
        existing = self.submit_ledger.get_by_client_order_id(client_order_id)
        if existing is not None and self.submit_ledger.is_pending(existing):
            self.audit.log(
                "governance_submit_deduped_pending",
                {
                    "request_id": request_id,
                    "client_order_id": client_order_id,
                    "existing": existing,
                },
            )
            self.event_source.emit(
                "submit_intent_deduped_pending",
                datetime.now(timezone.utc).isoformat(),
                {
                    "request_id": request_id,
                    "client_order_id": client_order_id,
                    "existing": existing,
                },
            )
            return {
                "status": "deduped_pending",
                "request_id": existing.get("request_id", request_id),
                "client_order_id": client_order_id,
                "existing": existing,
            }
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
        self.event_source.emit(
            "submit_intent_created",
            intent.created_at or datetime.now(timezone.utc).isoformat(),
            {
                "request_id": request_id,
                "client_order_id": client_order_id,
                "symbol": symbol,
                "signal": signal,
                "quantity": quantity,
                "notional": notional,
            },
        )
        decision = self.governance.evaluate(
            symbol=symbol,
            notional=notional,
            signal=signal,
            stale=stale,
            reconcile_ok=reconcile_ok,
            watchdog_halted=watchdog_halted,
            quantity=quantity,
            available_margin=available_margin,
            leverage=leverage,
            position_side=position_side,
            account_mode=account_mode,
            current_open_positions=current_open_positions,
            emergency_stop=emergency_stop,
            maintenance=maintenance,
            current_daily_loss_pct=current_daily_loss_pct,
            capital=capital,
        )
        if not decision.allowed:
            if decision.requires_approval:
                self.submit_ledger.mark_state(
                    request_id,
                    state="pending_approval",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    metadata={"reason": decision.reason},
                )
                self.event_source.emit(
                    "submit_intent_pending_approval",
                    datetime.now(timezone.utc).isoformat(),
                    {
                        "request_id": request_id,
                        "client_order_id": client_order_id,
                        "reason": decision.reason,
                    },
                )
                self.approvals.request_approval(
                    request_id,
                    {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "symbol": symbol,
                        "signal": signal,
                        "quantity": quantity,
                        "notional": notional,
                        "decision": decision.reason,
                        "client_order_id": client_order_id,
                    },
                )
                self.audit.log(
                    "governance_pending_approval",
                    {
                        "request_id": request_id,
                        "client_order_id": client_order_id,
                        "symbol": symbol,
                        "signal": signal,
                        "quantity": quantity,
                        "notional": notional,
                    },
                )
                return {
                    "status": "pending_approval",
                    "request_id": request_id,
                    "client_order_id": client_order_id,
                    "reason": decision.reason,
                }
            self.submit_ledger.mark_state(
                request_id,
                state="blocked",
                timestamp=datetime.now(timezone.utc).isoformat(),
                error=decision.reason,
            )
            self.event_source.emit(
                "submit_intent_blocked",
                datetime.now(timezone.utc).isoformat(),
                {
                    "request_id": request_id,
                    "client_order_id": client_order_id,
                    "reason": decision.reason,
                },
            )
            self.alerts.emit(
                "governance_block",
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reason": decision.reason,
                    "symbol": symbol,
                },
            )
            self.audit.log(
                "governance_block",
                {
                    "request_id": request_id,
                    "client_order_id": client_order_id,
                    "reason": decision.reason,
                    "symbol": symbol,
                    "signal": signal,
                },
            )
            return {
                "status": "blocked",
                "request_id": request_id,
                "client_order_id": client_order_id,
                "reason": decision.reason,
            }

        side = OrderSide.BUY if signal == 1 else OrderSide.SELL
        existing = self.submit_ledger.get_by_client_order_id(client_order_id)
        if existing and existing.get("state") in {
            "submitted",
            "acked",
            "partial",
            "filled",
        }:
            self.audit.log(
                "governance_submit_deduped",
                {
                    "request_id": request_id,
                    "client_order_id": client_order_id,
                    "existing": existing,
                },
            )
            self.event_source.emit(
                "submit_intent_deduped",
                datetime.now(timezone.utc).isoformat(),
                {
                    "request_id": request_id,
                    "client_order_id": client_order_id,
                    "existing": existing,
                },
            )
            return {
                "status": "deduped",
                "request_id": request_id,
                "client_order_id": client_order_id,
                "existing": existing,
            }

        order = Order(
            order_id=request_id,
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            client_order_id=client_order_id,
        )
        self.submit_ledger.mark_state(
            request_id,
            state="submit_pending",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.submit_ledger.append_attempt(
            request_id,
            SubmitAttempt(
                timestamp=datetime.now(timezone.utc).isoformat(),
                action="submit",
                status="started",
                payload={
                    "symbol": symbol,
                    "signal": signal,
                    "quantity": quantity,
                    "notional": notional,
                },
            ),
        )
        result = self.adapter.submit_order(order)
        if result.ok:
            exchange_order_id = (
                (result.payload or {}).get("id")
                if isinstance(result.payload, dict)
                else None
            )
            self.submit_ledger.append_attempt(
                request_id,
                SubmitAttempt(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    action="submit",
                    status="ok",
                    payload={"response": result.payload},
                ),
            )
            self.submit_ledger.mark_state(
                request_id,
                state="submitted",
                timestamp=datetime.now(timezone.utc).isoformat(),
                exchange_order_id=exchange_order_id,
            )
            self.event_source.emit(
                "submit_intent_submitted",
                datetime.now(timezone.utc).isoformat(),
                {
                    "request_id": request_id,
                    "client_order_id": client_order_id,
                    "exchange_order_id": exchange_order_id,
                    "response": result.payload,
                },
            )
            self.audit.log(
                "governance_submit",
                {
                    "request_id": request_id,
                    "client_order_id": client_order_id,
                    "symbol": symbol,
                    "signal": signal,
                    "quantity": quantity,
                    "notional": notional,
                    "response": result.payload,
                },
            )
            return {
                "status": "submitted",
                "request_id": request_id,
                "client_order_id": client_order_id,
                "response": result.payload,
                "order": order,
            }
        self.submit_ledger.append_attempt(
            request_id,
            SubmitAttempt(
                timestamp=datetime.now(timezone.utc).isoformat(),
                action="submit",
                status="error",
                payload={"error": result.error},
            ),
        )
        remote_lookup = self.adapter.fetch_open_orders_by_client_order_id(
            client_order_id
        )
        recovered_orders = (
            remote_lookup.payload if isinstance(remote_lookup.payload, list) else []
        )
        if remote_lookup.ok and recovered_orders:
            remote_order = recovered_orders[0]
            exchange_order_id = remote_order.get("id")
            self.submit_ledger.mark_state(
                request_id,
                state="submitted",
                timestamp=datetime.now(timezone.utc).isoformat(),
                exchange_order_id=exchange_order_id,
                metadata={"recovered_from": "client_order_lookup"},
            )
            self.event_source.emit(
                "submit_intent_recovered",
                datetime.now(timezone.utc).isoformat(),
                {
                    "request_id": request_id,
                    "client_order_id": client_order_id,
                    "exchange_order_id": exchange_order_id,
                    "response": remote_order,
                    "original_error": result.error,
                },
            )
            self.audit.log(
                "governance_submit_recovered",
                {
                    "request_id": request_id,
                    "client_order_id": client_order_id,
                    "response": remote_order,
                    "original_error": result.error,
                },
            )
            return {
                "status": "submitted_recovered",
                "request_id": request_id,
                "client_order_id": client_order_id,
                "response": remote_order,
                "order": order,
            }
        self.submit_ledger.mark_state(
            request_id,
            state="unknown",
            timestamp=datetime.now(timezone.utc).isoformat(),
            error=result.error,
        )
        self.event_source.emit(
            "submit_intent_unknown",
            datetime.now(timezone.utc).isoformat(),
            {
                "request_id": request_id,
                "client_order_id": client_order_id,
                "error": result.error,
            },
        )
        self.alerts.emit(
            "governance_submit_failed",
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "request_id": request_id,
                "error": result.error,
            },
        )
        self.audit.log(
            "governance_submit_failed",
            {
                "request_id": request_id,
                "client_order_id": client_order_id,
                "error": result.error,
            },
        )
        return {
            "status": "submit_failed",
            "request_id": request_id,
            "client_order_id": client_order_id,
            "error": result.error,
        }

    def governed_cancel_replace(
        self,
        cancel_order_id: str,
        symbol: str,
        new_signal: int,
        quantity: float,
        notional: float,
        record=None,
    ):
        timestamp = datetime.now(timezone.utc).isoformat()
        residual_quantity = quantity
        if record is not None:
            residual_quantity = max(
                float(record.quantity) - float(record.filled_quantity or 0.0),
                0.0,
            )
            quarantine = record.tags.get("quarantine") or {}
            duplicate_risk = record.tags.get("duplicate_exposure_risk") or {}
            terminal_states = {
                CanonicalOrderState.FILLED.value,
                CanonicalOrderState.CANCELED.value,
                CanonicalOrderState.REJECTED.value,
                CanonicalOrderState.EXPIRED.value,
            }
            reason = None
            if quarantine.get("blocked"):
                reason = quarantine.get("reason") or "order_state_quarantined"
            elif duplicate_risk.get("blocked"):
                reason = duplicate_risk.get("reason") or "duplicate_exposure_risk"
            elif record.state in terminal_states:
                reason = f"replace_requested_for_terminal_order:{record.state}"
            elif record.tags.get("pending_replacement_order_id"):
                reason = "replace_already_in_flight"
            elif record.tags.get("replaced_by_order_id"):
                reason = "order_already_replaced"
            elif residual_quantity <= 0.0:
                reason = "replace_requested_with_no_residual_quantity"
                record.tags.setdefault("quarantine", {}).update(
                    {
                        "blocked": True,
                        "reason": reason,
                        "at": timestamp,
                    }
                )
            if reason is not None:
                block_details = {
                    "cancel_order_id": cancel_order_id,
                    "reason": reason,
                    "quarantine": record.tags.get("quarantine") or quarantine,
                    "duplicate_exposure_risk": duplicate_risk,
                    "state": record.state,
                }
                self.event_source.emit(
                    "cancel_replace_blocked", timestamp, block_details
                )
                self.alerts.emit(
                    "governed_cancel_replace_blocked",
                    {
                        "timestamp": timestamp,
                        "cancel_order_id": cancel_order_id,
                        "reason": reason,
                    },
                    severity="critical",
                )
                self.audit.log("governed_cancel_replace_blocked", block_details)
                return {
                    "status": "blocked",
                    "reason": reason,
                    "record": record,
                }
        side = OrderSide.BUY if new_signal == 1 else OrderSide.SELL
        constraint_checker = getattr(self.governance, "constraint_checker", None)
        if constraint_checker is not None:
            constraint_result = constraint_checker.validate_order(
                quantity=residual_quantity,
                price=None,
                side=side.value,
                order_type=OrderType.MARKET.value,
                notional=notional,
                reduce_only=bool(getattr(record, "reduce_only", False)),
                position_side=getattr(record, "side", 0) if record is not None else 0,
                account_mode=(
                    getattr(self.governance.contract, "position_mode", "one_way")
                    if self.governance.contract is not None
                    else "one_way"
                ),
                current_position_notional=notional,
                current_position_side=(
                    getattr(record, "side", 0) if record is not None else 0
                ),
                max_open_positions=self.governance.live_risk.max_open_positions,
                current_open_positions=1 if record is not None else 0,
            )
            if not constraint_result.ok:
                first = constraint_result.violations[0]
                self.event_source.emit(
                    "cancel_replace_blocked",
                    timestamp,
                    {
                        "cancel_order_id": cancel_order_id,
                        "reason": first["code"],
                        "violations": constraint_result.violations,
                    },
                )
                self.alerts.emit(
                    "governed_cancel_replace_blocked",
                    {
                        "timestamp": timestamp,
                        "cancel_order_id": cancel_order_id,
                        "reason": first["code"],
                    },
                    severity="critical",
                )
                self.audit.log(
                    "governed_cancel_replace_blocked",
                    {
                        "cancel_order_id": cancel_order_id,
                        "reason": first["code"],
                        "violations": constraint_result.violations,
                    },
                )
                return {
                    "status": "blocked",
                    "reason": first["code"],
                    "violations": constraint_result.violations,
                    "record": record,
                }
        new_order = Order(
            order_id=str(uuid.uuid4()),
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=residual_quantity,
            client_order_id=str(uuid.uuid4()),
        )
        if record is not None:
            try:
                cancel_pending = apply_local_cancel(
                    record,
                    timestamp=timestamp,
                    payload={
                        "cancel_order_id": cancel_order_id,
                        "residual_quantity": residual_quantity,
                    },
                )
                record = apply_local_replace(
                    cancel_pending,
                    timestamp=timestamp,
                    payload={
                        "new_order_id": new_order.order_id,
                        "residual_quantity": residual_quantity,
                    },
                )
            except Exception:  # noqa: BLE001
                record.state = CanonicalOrderState.REPLACE_PENDING.value
            record.tags["replace_residual_quantity"] = residual_quantity
            record.tags["replace_target_order_id"] = new_order.order_id
        self.event_source.emit(
            "cancel_replace_requested",
            timestamp,
            {
                "cancel_order_id": cancel_order_id,
                "new_order_id": new_order.order_id,
                "symbol": symbol,
                "quantity": residual_quantity,
                "notional": notional,
            },
        )
        result = self.adapter.cancel_replace_order(cancel_order_id, new_order)
        if result.ok:
            self.event_source.emit(
                "cancel_replace_completed",
                datetime.now(timezone.utc).isoformat(),
                {
                    "cancel_order_id": cancel_order_id,
                    "new_order_id": new_order.order_id,
                    "response": result.payload,
                },
            )
            self.audit.log(
                "governed_cancel_replace",
                {
                    "cancel_order_id": cancel_order_id,
                    "new_signal": new_signal,
                    "quantity": residual_quantity,
                    "notional": notional,
                    "response": result.payload,
                },
            )
            if record is not None:
                record.tags["replaced_by_order_id"] = new_order.order_id
                record.tags["pending_replacement_order_id"] = new_order.order_id
                record.tags["replace_residual_quantity"] = residual_quantity
            return {
                "status": "cancel_replaced",
                "response": result.payload,
                "record": record,
                "new_order": new_order,
            }
        self.event_source.emit(
            "cancel_replace_failed",
            datetime.now(timezone.utc).isoformat(),
            {
                "cancel_order_id": cancel_order_id,
                "new_order_id": new_order.order_id,
                "error": result.error,
            },
        )
        self.alerts.emit(
            "governed_cancel_replace_failed",
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "cancel_order_id": cancel_order_id,
                "error": result.error,
            },
        )
        self.audit.log(
            "governed_cancel_replace_failed",
            {
                "cancel_order_id": cancel_order_id,
                "error": result.error,
            },
        )
        return {
            "status": "cancel_replace_failed",
            "error": result.error,
            "record": record,
        }

    def process_approved_request(self, request_id: str):
        if self.approvals.is_rejected(request_id):
            self.submit_ledger.mark_state(
                request_id,
                state="rejected",
                timestamp=datetime.now(timezone.utc).isoformat(),
                error="operator_rejected",
            )
            self.audit.log("governance_request_rejected", {"request_id": request_id})
            return {"status": "rejected", "request_id": request_id}
        if not self.approvals.is_approved(request_id):
            return {"status": "not_approved", "request_id": request_id}
        req = self.approvals.consume_request(request_id)
        if req is None:
            return {"status": "missing_request", "request_id": request_id}
        self.submit_ledger.mark_state(
            request_id,
            state="approved",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self.event_source.emit(
            "submit_intent_approved",
            datetime.now(timezone.utc).isoformat(),
            {"request_id": request_id},
        )
        existing = self.submit_ledger.get(request_id)
        if existing and existing.get("state") in {
            "submitted",
            "acked",
            "partial",
            "filled",
        }:
            return {
                "status": "deduped",
                "request_id": request_id,
                "existing": existing,
            }
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
