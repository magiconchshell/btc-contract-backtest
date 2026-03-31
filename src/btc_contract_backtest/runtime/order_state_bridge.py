from __future__ import annotations
from typing import Optional

from btc_contract_backtest.engine.execution_models import Order, OrderStatus
from btc_contract_backtest.runtime.order_state_machine import (
    AmbiguousOrderState,
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


def apply_local_submit(
    record: CanonicalOrderRecord,
    *,
    timestamp: Optional[str],
    payload: Optional[dict] = None,
) -> CanonicalOrderRecord:
    return OrderStateMachine.apply_transition(
        record,
        next_state=CanonicalOrderState.NEW.value,
        event=OrderEvent(
            source="local",
            event_type="submit_intent",
            state=CanonicalOrderState.NEW.value,
            timestamp=timestamp,
            payload=payload or {},
        ),
    )


def apply_local_cancel(
    record: CanonicalOrderRecord,
    *,
    timestamp: Optional[str],
    payload: Optional[dict] = None,
) -> CanonicalOrderRecord:
    return OrderStateMachine.apply_transition(
        record,
        next_state=CanonicalOrderState.CANCEL_PENDING.value,
        event=OrderEvent(
            source="local",
            event_type="cancel_intent",
            state=CanonicalOrderState.CANCEL_PENDING.value,
            timestamp=timestamp,
            payload=payload or {},
        ),
    )


def apply_local_replace(
    record: CanonicalOrderRecord,
    *,
    timestamp: Optional[str],
    payload: Optional[dict] = None,
) -> CanonicalOrderRecord:
    tags = record.tags
    payload = payload or {}
    root_id = tags.get("replace_chain_root_order_id") or record.order_id
    next_order_id = payload.get("new_order_id")
    replacements = tags.setdefault("replacement_order_ids", [])
    if next_order_id is not None and next_order_id not in replacements:
        replacements.append(next_order_id)
    tags["replace_chain_root_order_id"] = root_id
    tags["replacement_count"] = int(tags.get("replacement_count") or 0) + 1
    tags["pending_replacement_order_id"] = next_order_id
    return OrderStateMachine.apply_transition(
        record,
        next_state=CanonicalOrderState.REPLACE_PENDING.value,
        event=OrderEvent(
            source="local",
            event_type="replace_intent",
            state=CanonicalOrderState.REPLACE_PENDING.value,
            timestamp=timestamp,
            payload=payload,
        ),
    )


def _mark_replace_race_risk(
    record: CanonicalOrderRecord,
    *,
    mapped: CanonicalOrderState,
    timestamp: Optional[str],
    event_payload: dict,
) -> None:
    replacement_order_id = record.tags.get("pending_replacement_order_id") or record.tags.get("replaced_by_order_id")
    if replacement_order_id is None:
        return

    duplicate_risk = record.tags.setdefault("duplicate_exposure_risk", {})
    duplicate_risk.update(
        {
            "blocked": True,
            "reason": "late_fill_after_replace_intent",
            "at": timestamp,
            "original_order_id": record.order_id,
            "replacement_order_id": replacement_order_id,
            "incoming_status": mapped.value,
        }
    )
    quarantine = record.tags.setdefault("quarantine", {})
    quarantine.update(
        {
            "blocked": True,
            "reason": "late_fill_after_replace_intent",
            "at": timestamp,
            "incoming_status": mapped.value,
            "incoming_payload": event_payload,
            "replacement_order_id": replacement_order_id,
        }
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
    event_payload = dict(payload or {})
    if filled_quantity is not None:
        event_payload.setdefault("filled_quantity", filled_quantity)
    if exchange_order_id is not None:
        event_payload.setdefault("exchange_order_id", exchange_order_id)
    try:
        updated = OrderStateMachine.apply_transition(
            record,
            next_state=mapped.value,
            event=OrderEvent(
                source="remote",
                event_type=event_type,
                state=mapped.value,
                timestamp=timestamp,
                payload=event_payload,
            ),
            filled_quantity=filled_quantity,
            avg_fill_price=avg_fill_price,
            exchange_order_id=exchange_order_id,
            last_error=last_error,
        )
        if mapped == CanonicalOrderState.FILLED:
            _mark_replace_race_risk(
                updated,
                mapped=mapped,
                timestamp=timestamp,
                event_payload=event_payload,
            )
        return updated
    except AmbiguousOrderState as exc:
        quarantine = record.tags.setdefault("quarantine", {})
        quarantine.update(
            {
                "blocked": True,
                "reason": str(exc),
                "at": timestamp,
                "incoming_status": mapped.value,
                "incoming_payload": event_payload,
            }
        )
        raise


def propagate_replace_chain(parent: CanonicalOrderRecord, child: CanonicalOrderRecord) -> CanonicalOrderRecord:
    root_id = parent.tags.get("replace_chain_root_order_id") or parent.order_id
    lineage = list(parent.tags.get("replace_lineage", []))
    if parent.order_id not in lineage:
        lineage.append(parent.order_id)
    child.tags["replace_chain_root_order_id"] = root_id
    child.tags["replaces_order_id"] = parent.order_id
    child.tags["replace_lineage"] = lineage
    child.tags["replacement_depth"] = len(lineage)
    parent.tags["replaced_by_order_id"] = child.order_id
    parent.tags["pending_replacement_order_id"] = child.order_id
    return child
