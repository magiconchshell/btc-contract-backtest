from __future__ import annotations
from typing import Optional

from btc_contract_backtest.engine.execution_models import Order, OrderStatus
from btc_contract_backtest.runtime.order_state_machine import (
    CanonicalOrderRecord,
    CanonicalOrderState,
    OrderEvent,
    OrderStateMachine,
)


STATUS_MAP = {
    OrderStatus.NEW.value: CanonicalOrderState.NEW,
    OrderStatus.PARTIALLY_FILLED.value: CanonicalOrderState.PARTIAL,
    OrderStatus.FILLED.value: CanonicalOrderState.FILLED,
    OrderStatus.CANCELED.value: CanonicalOrderState.CANCELED,
    OrderStatus.REJECTED.value: CanonicalOrderState.REJECTED,
    OrderStatus.EXPIRED.value: CanonicalOrderState.EXPIRED,
}


def canonical_record_from_order(order: Order, submission_mode: str) -> CanonicalOrderRecord:
    return OrderStateMachine.create_record(
        order_id=order.order_id,
        client_order_id=order.client_order_id,
        exchange_order_id=order.exchange_order_id,
        symbol=order.symbol,
        side=order.side.value,
        order_type=order.order_type.value,
        quantity=order.quantity,
        reduce_only=order.reduce_only,
        submission_mode=submission_mode,
        created_at=order.created_at,
        tags=order.tags,
    )


def apply_local_submit(record: CanonicalOrderRecord, *, timestamp: Optional[str], payload: Optional[dict] = None) -> CanonicalOrderRecord:
    return OrderStateMachine.apply_transition(
        record,
        next_state=CanonicalOrderState.NEW.value,
        event=OrderEvent(source="local", event_type="submit_intent", state=CanonicalOrderState.NEW.value, timestamp=timestamp, payload=payload or {}),
    )


def apply_local_cancel(record: CanonicalOrderRecord, *, timestamp: Optional[str], payload: Optional[dict] = None) -> CanonicalOrderRecord:
    return OrderStateMachine.apply_transition(
        record,
        next_state=CanonicalOrderState.CANCEL_PENDING.value,
        event=OrderEvent(source="local", event_type="cancel_intent", state=CanonicalOrderState.CANCEL_PENDING.value, timestamp=timestamp, payload=payload or {}),
    )


def apply_local_replace(record: CanonicalOrderRecord, *, timestamp: Optional[str], payload: Optional[dict] = None) -> CanonicalOrderRecord:
    return OrderStateMachine.apply_transition(
        record,
        next_state=CanonicalOrderState.REPLACE_PENDING.value,
        event=OrderEvent(source="local", event_type="replace_intent", state=CanonicalOrderState.REPLACE_PENDING.value, timestamp=timestamp, payload=payload or {}),
    )


def apply_remote_status(
    record: CanonicalOrderRecord,
    *,
    status: str,
    timestamp: Optional[str],
    payload: Optional[dict] = None,
    filled_quantity: Optional[float] = None,
    avg_fill_price: Optional[float] = None,
    exchange_order_id: Optional[str] = None,
    last_error: Optional[str] = None,
) -> CanonicalOrderRecord:
    mapped = STATUS_MAP.get(status, CanonicalOrderState.ACKED)
    event_type = f"remote_{mapped.value}"
    return OrderStateMachine.apply_transition(
        record,
        next_state=mapped.value,
        event=OrderEvent(source="remote", event_type=event_type, state=mapped.value, timestamp=timestamp, payload=payload or {}),
        filled_quantity=filled_quantity,
        avg_fill_price=avg_fill_price,
        exchange_order_id=exchange_order_id,
        last_error=last_error,
    )
