from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional, Any


def _sequence_components(value: Any) -> tuple[int, Any]:
    if value in (None, ""):
        return (2, "")
    try:
        return (0, int(str(value)))
    except (TypeError, ValueError):
        return (1, str(value))


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


class AmbiguousOrderState(ValueError):
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

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _remote_event_rank(cls, event: OrderEvent) -> int:
        state_ranks = {
            CanonicalOrderState.NEW.value: 10,
            CanonicalOrderState.ACKED.value: 20,
            CanonicalOrderState.CANCEL_PENDING.value: 25,
            CanonicalOrderState.REPLACE_PENDING.value: 30,
            CanonicalOrderState.PARTIAL.value: 40,
            CanonicalOrderState.CANCELED.value: 50,
            CanonicalOrderState.REJECTED.value: 60,
            CanonicalOrderState.EXPIRED.value: 70,
            CanonicalOrderState.FILLED.value: 80,
        }
        filled = cls._to_float(event.payload.get("filled_quantity"))
        if filled is None:
            filled = cls._to_float(event.payload.get("filled"))
        bonus = 1 if filled and filled > 0 else 0
        return state_ranks.get(event.state, 0) + bonus

    @classmethod
    def _resolve_remote_precedence(
        cls,
        record: CanonicalOrderRecord,
        event: OrderEvent,
        next_state: CanonicalOrderState,
    ) -> tuple[bool, bool]:
        current = CanonicalOrderState(record.state)
        if event.source != "remote":
            return False, False
        tags = record.tags
        last_event_id = tags.get("last_remote_event_id")
        event_id = event.payload.get("event_id") or event.payload.get(
            "external_sequence"
        )
        if event_id and last_event_id == event_id:
            return True, False

        last_sequence = tags.get("last_remote_sequence")
        incoming_sequence = event.payload.get("external_sequence")
        if incoming_sequence is not None:
            incoming_sequence = str(incoming_sequence)
        current_rank = cls._remote_event_rank(
            OrderEvent(
                source="remote",
                event_type="current",
                state=current.value,
                payload={"filled": record.filled_quantity},
            )
        )
        incoming_rank = cls._remote_event_rank(event)

        if cls.is_terminal(record.state):
            if next_state == current:
                return False, False
            if incoming_rank < current_rank:
                return False, False
            raise AmbiguousOrderState(
                "terminal order "
                f"{record.order_id} received conflicting remote state "
                f"{next_state.value} after {current.value}"
            )

        if (
            current == CanonicalOrderState.REPLACE_PENDING
            and next_state == CanonicalOrderState.ACKED
        ):
            return True, False

        if current == CanonicalOrderState.PARTIAL and next_state in {
            CanonicalOrderState.NEW,
            CanonicalOrderState.ACKED,
        }:
            return True, False

        if (
            last_sequence is not None
            and incoming_sequence is not None
            and _sequence_components(incoming_sequence)
            < _sequence_components(last_sequence)
        ):
            if incoming_rank <= current_rank:
                return True, False
            raise AmbiguousOrderState(
                "out-of-order remote event for "
                f"{record.order_id} advanced state from {current.value} "
                f"to {next_state.value}"
            )
        return False, False

    @classmethod
    def _update_tags(
        cls,
        record: CanonicalOrderRecord,
        *,
        event: OrderEvent,
        target: CanonicalOrderState,
        filled_quantity: Optional[float],
        exchange_order_id: Optional[str],
    ) -> None:
        if event.source == "remote":
            event_id = event.payload.get("event_id") or event.payload.get(
                "external_sequence"
            )
            if event_id is not None:
                record.tags["last_remote_event_id"] = event_id
            external_sequence = event.payload.get("external_sequence")
            if external_sequence is not None:
                record.tags["last_remote_sequence"] = str(external_sequence)
            if event.timestamp is not None:
                record.tags["last_remote_timestamp"] = event.timestamp

        if filled_quantity is not None:
            residual = max(record.quantity - record.filled_quantity, 0.0)
            record.tags["residual_quantity"] = residual
            if residual > 0 and record.filled_quantity > 0:
                record.tags["has_residual_open_quantity"] = True
            else:
                record.tags["has_residual_open_quantity"] = False

        if exchange_order_id is not None:
            record.tags.setdefault("exchange_order_ids", [])
            if exchange_order_id not in record.tags["exchange_order_ids"]:
                record.tags["exchange_order_ids"].append(exchange_order_id)

        if target in TERMINAL_STATES:
            record.tags["residual_quantity"] = max(
                record.quantity - record.filled_quantity, 0.0
            )
            record.tags["has_residual_open_quantity"] = False

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

        should_ignore, _ = cls._resolve_remote_precedence(record, event, target)
        if should_ignore:
            return record

        if target not in VALID_TRANSITIONS[current]:
            raise InvalidOrderTransition(
                f"invalid transition {current.value} -> {target.value}"
            )

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
        if target in TERMINAL_STATES and record.final_at is None:
            record.final_at = event.timestamp
        cls._update_tags(
            record,
            event=event,
            target=target,
            filled_quantity=filled_quantity,
            exchange_order_id=exchange_order_id,
        )
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
