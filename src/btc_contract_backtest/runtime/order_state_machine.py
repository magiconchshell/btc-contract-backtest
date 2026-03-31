from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional, Any


class CanonicalOrderState(str, Enum):
    NEW = "new"
    ACKED = "acked"
    CANCEL_PENDING = "cancel_pending"
    REPLACE_PENDING = "replace_pending"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


TERMINAL_STATES = {
    CanonicalOrderState.FILLED,
    CanonicalOrderState.CANCELED,
    CanonicalOrderState.REJECTED,
    CanonicalOrderState.EXPIRED,
}


VALID_TRANSITIONS: dict[CanonicalOrderState, set[CanonicalOrderState]] = {
    CanonicalOrderState.NEW: {
        CanonicalOrderState.NEW,
        CanonicalOrderState.ACKED,
        CanonicalOrderState.CANCEL_PENDING,
        CanonicalOrderState.REPLACE_PENDING,
        CanonicalOrderState.PARTIAL,
        CanonicalOrderState.FILLED,
        CanonicalOrderState.CANCELED,
        CanonicalOrderState.REJECTED,
        CanonicalOrderState.EXPIRED,
    },
    CanonicalOrderState.ACKED: {
        CanonicalOrderState.ACKED,
        CanonicalOrderState.CANCEL_PENDING,
        CanonicalOrderState.REPLACE_PENDING,
        CanonicalOrderState.PARTIAL,
        CanonicalOrderState.FILLED,
        CanonicalOrderState.CANCELED,
        CanonicalOrderState.REJECTED,
        CanonicalOrderState.EXPIRED,
    },
    CanonicalOrderState.CANCEL_PENDING: {
        CanonicalOrderState.CANCEL_PENDING,
        CanonicalOrderState.CANCELED,
        CanonicalOrderState.PARTIAL,
        CanonicalOrderState.FILLED,
        CanonicalOrderState.REJECTED,
        CanonicalOrderState.EXPIRED,
    },
    CanonicalOrderState.REPLACE_PENDING: {
        CanonicalOrderState.REPLACE_PENDING,
        CanonicalOrderState.ACKED,
        CanonicalOrderState.PARTIAL,
        CanonicalOrderState.FILLED,
        CanonicalOrderState.CANCELED,
        CanonicalOrderState.REJECTED,
        CanonicalOrderState.EXPIRED,
    },
    CanonicalOrderState.PARTIAL: {
        CanonicalOrderState.PARTIAL,
        CanonicalOrderState.CANCEL_PENDING,
        CanonicalOrderState.REPLACE_PENDING,
        CanonicalOrderState.FILLED,
        CanonicalOrderState.CANCELED,
        CanonicalOrderState.REJECTED,
        CanonicalOrderState.EXPIRED,
    },
    CanonicalOrderState.FILLED: {CanonicalOrderState.FILLED},
    CanonicalOrderState.CANCELED: {CanonicalOrderState.CANCELED},
    CanonicalOrderState.REJECTED: {CanonicalOrderState.REJECTED},
    CanonicalOrderState.EXPIRED: {CanonicalOrderState.EXPIRED},
}


@dataclass
class OrderEvent:
    source: str
    event_type: str
    state: str
    timestamp: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class CanonicalOrderRecord:
    order_id: str
    client_order_id: Optional[str] = None
    exchange_order_id: Optional[str] = None
    intent_id: Optional[str] = None
    symbol: Optional[str] = None
    side: Optional[str] = None
    order_type: Optional[str] = None
    quantity: float = 0.0
    filled_quantity: float = 0.0
    avg_fill_price: Optional[float] = None
    reduce_only: bool = False
    submission_mode: Optional[str] = None
    state: str = CanonicalOrderState.NEW.value
    created_at: Optional[str] = None
    acked_at: Optional[str] = None
    final_at: Optional[str] = None
    last_error: Optional[str] = None
    local_events: list[dict[str, Any]] = field(default_factory=list)
    remote_events: list[dict[str, Any]] = field(default_factory=list)
    tags: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InvalidOrderTransition(ValueError):
    pass


class OrderStateMachine:
    @staticmethod
    def is_terminal(state: str) -> bool:
        return CanonicalOrderState(state) in TERMINAL_STATES

    @staticmethod
    def _event_list_name(source: str) -> str:
        return "remote_events" if source == "remote" else "local_events"

    @staticmethod
    def _dedupe_event(events: list[dict[str, Any]], event: OrderEvent) -> bool:
        encoded = asdict(event)
        return encoded in events

    @classmethod
    def apply_transition(
        cls,
        record: CanonicalOrderRecord,
        *,
        next_state: str,
        event: OrderEvent,
        filled_quantity: Optional[float] = None,
        avg_fill_price: Optional[float] = None,
        exchange_order_id: Optional[str] = None,
        last_error: Optional[str] = None,
    ) -> CanonicalOrderRecord:
        current = CanonicalOrderState(record.state)
        target = CanonicalOrderState(next_state)

        if target not in VALID_TRANSITIONS[current]:
            raise InvalidOrderTransition(f"invalid transition {current.value} -> {target.value}")

        event_list_name = cls._event_list_name(event.source)
        event_list = getattr(record, event_list_name)
        if not cls._dedupe_event(event_list, event):
            event_list.append(asdict(event))

        if filled_quantity is not None:
            record.filled_quantity = max(record.filled_quantity, filled_quantity)
        if avg_fill_price is not None:
            record.avg_fill_price = avg_fill_price
        if exchange_order_id is not None and record.exchange_order_id is None:
            record.exchange_order_id = exchange_order_id
        if last_error is not None:
            record.last_error = last_error

        record.state = target.value
        if target == CanonicalOrderState.ACKED and record.acked_at is None:
            record.acked_at = event.timestamp
        if target in TERMINAL_STATES:
            record.final_at = event.timestamp
        return record

    @classmethod
    def create_record(
        cls,
        *,
        order_id: str,
        client_order_id: Optional[str] = None,
        exchange_order_id: Optional[str] = None,
        intent_id: Optional[str] = None,
        symbol: Optional[str] = None,
        side: Optional[str] = None,
        order_type: Optional[str] = None,
        quantity: float = 0.0,
        reduce_only: bool = False,
        submission_mode: Optional[str] = None,
        created_at: Optional[str] = None,
        tags: Optional[dict[str, Any]] = None,
    ) -> CanonicalOrderRecord:
        return CanonicalOrderRecord(
            order_id=order_id,
            client_order_id=client_order_id,
            exchange_order_id=exchange_order_id,
            intent_id=intent_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            reduce_only=reduce_only,
            submission_mode=submission_mode,
            created_at=created_at,
            tags=tags or {},
        )
