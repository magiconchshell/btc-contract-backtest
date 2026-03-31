from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from btc_contract_backtest.runtime.order_state_bridge import apply_remote_status
from btc_contract_backtest.runtime.order_state_machine import OrderStateMachine


OPEN_REMOTE_ORDER_STATES = {"new", "open", "acked", "partially_filled", "partial", "working"}
TERMINAL_INTENT_STATES = {"filled", "canceled", "rejected", "expired", "failed"}
TERMINAL_REPLAY_ORDER_STATES = {"filled", "canceled", "rejected", "expired"}


@dataclass
class ConvergenceWatermark:
    last_sequence: Optional[int] = None
    last_event_timestamp: Optional[str] = None
    last_received_at: Optional[str] = None
    last_external_sequence: Optional[str] = None
    replay_event_count: int = 0
    replayable_event_count: int = 0
    replay_order_event_count: int = 0
    replay_fill_event_count: int = 0
    poll_fallback_required: bool = True
    upstream_live: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PositionConvergence:
    ok: bool
    local_side: int = 0
    remote_side: int = 0
    local_quantity: float = 0.0
    remote_quantity: float = 0.0
    local_entry_price: Optional[float] = None
    remote_entry_price: Optional[float] = None
    mismatch_types: list[str] = field(default_factory=list)
    severity: str = "info"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IntentConvergence:
    request_id: str
    client_order_id: Optional[str]
    state: str
    classification: str
    severity: str
    reason: str
    exchange_order_id: Optional[str] = None
    remote_order_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RecoveryAction:
    action: str
    severity: str
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StartupConvergenceReport:
    ok: bool
    timestamp: str
    environment: str = "testnet"
    watermark: dict[str, Any] = field(default_factory=dict)
    position: dict[str, Any] = field(default_factory=dict)
    unresolved_intents: list[dict[str, Any]] = field(default_factory=list)
    replay_hooks: dict[str, Any] = field(default_factory=dict)
    actions: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _position_side(position: Optional[dict[str, Any]]) -> int:
    if not isinstance(position, dict):
        return 0
    qty = float(
        position.get("quantity")
        or position.get("contracts")
        or position.get("positionAmt")
        or position.get("pa")
        or 0.0
    )
    side = position.get("side")
    if side in (-1, 0, 1):
        return int(side)
    if qty > 0:
        return 1
    if qty < 0:
        return -1
    return 0


def _position_quantity(position: Optional[dict[str, Any]]) -> float:
    if not isinstance(position, dict):
        return 0.0
    qty = float(
        position.get("quantity")
        or position.get("contracts")
        or position.get("positionAmt")
        or position.get("pa")
        or 0.0
    )
    return abs(qty)


def _position_entry_price(position: Optional[dict[str, Any]]) -> Optional[float]:
    if not isinstance(position, dict):
        return None
    value = position.get("entry_price")
    if value is None:
        value = position.get("entryPrice")
    if value in (None, ""):
        return None
    return float(str(value))


def _normalize_order_state(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower()
    aliases = {
        "cancelled": "canceled",
        "closed": "filled",
        "partiallyfilled": "partially_filled",
        "partially_filled": "partial",
        "partially-filled": "partial",
        "partial_fill": "partial",
        "partialfilled": "partial",
        "trade": "partial",
        "new": "new",
    }
    return aliases.get(normalized, normalized)


def _safe_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def build_convergence_watermark(
    *,
    boundary: Optional[dict[str, Any]],
    events: Optional[list[dict[str, Any]]],
) -> ConvergenceWatermark:
    boundary = boundary or {}
    events = events or []
    replayable = [event for event in events if bool(event.get("replayable", True))]
    order_events = [
        event for event in replayable
        if str(event.get("event_type") or "").startswith("order_")
        or str(event.get("event_type") or "") in {"runtime_decision"}
    ]
    fill_events = [
        event for event in replayable
        if str(event.get("event_type") or "") in {"order_trade_update", "fill", "fill_update"}
        or str((_event_payload(event).get("execution_type") or "")).lower() == "trade"
    ]
    upstream_value = boundary.get("upstream")
    upstream = upstream_value if isinstance(upstream_value, dict) else {}
    return ConvergenceWatermark(
        last_sequence=boundary.get("last_sequence"),
        last_event_timestamp=boundary.get("last_event_timestamp"),
        last_received_at=boundary.get("last_received_at"),
        last_external_sequence=boundary.get("last_external_sequence"),
        replay_event_count=len(events),
        replayable_event_count=len(replayable),
        replay_order_event_count=len(order_events),
        replay_fill_event_count=len(fill_events),
        poll_fallback_required=bool(boundary.get("poll_fallback_required", True)),
        upstream_live=bool(upstream.get("connected") and upstream.get("listen_key_present")),
    )


def build_position_convergence(
    *,
    local_position: Optional[dict[str, Any]],
    remote_position: Optional[dict[str, Any]],
    quantity_tolerance: float = 1e-9,
    price_tolerance: float = 1e-9,
) -> PositionConvergence:
    local_side = _position_side(local_position)
    remote_side = _position_side(remote_position)
    local_qty = _position_quantity(local_position)
    remote_qty = _position_quantity(remote_position)
    local_entry = _position_entry_price(local_position)
    remote_entry = _position_entry_price(remote_position)
    mismatch_types: list[str] = []
    if local_side != remote_side:
        mismatch_types.append("side")
    if abs(local_qty - remote_qty) > quantity_tolerance:
        mismatch_types.append("quantity")
    if local_entry is not None and remote_entry is not None and abs(local_entry - remote_entry) > price_tolerance:
        mismatch_types.append("entry_basis")
    severity = "info"
    if mismatch_types:
        severity = "critical" if any(item in {"side", "quantity"} for item in mismatch_types) else "warning"
    return PositionConvergence(
        ok=not mismatch_types,
        local_side=local_side,
        remote_side=remote_side,
        local_quantity=local_qty,
        remote_quantity=remote_qty,
        local_entry_price=local_entry,
        remote_entry_price=remote_entry,
        mismatch_types=mismatch_types,
        severity=severity,
    )


def summarize_replay_state(events: Optional[list[dict[str, Any]]]) -> dict[str, Any]:
    replayable = [event for event in (events or []) if bool(event.get("replayable", True))]
    orders_by_client: dict[str, dict[str, Any]] = {}
    latest_account_update: Optional[dict[str, Any]] = None

    for event in replayable:
        payload = _event_payload(event)
        event_type = str(event.get("event_type") or "")
        client_order_id = payload.get("client_order_id")
        order_id = payload.get("order_id")
        state = _normalize_order_state(payload.get("status")) or _normalize_order_state(event_type.removeprefix("order_"))
        filled_quantity = _safe_float(payload.get("filled_quantity"))
        last_fill_quantity = _safe_float(payload.get("last_fill_quantity")) or 0.0
        average_price = _safe_float(payload.get("average_price"))
        target = None
        if client_order_id:
            target = orders_by_client.setdefault(
                str(client_order_id),
                {
                    "client_order_id": str(client_order_id),
                    "order_id": order_id,
                    "state": None,
                    "terminal": False,
                    "filled_quantity": 0.0,
                    "last_fill_quantity": 0.0,
                    "average_price": None,
                    "last_sequence": None,
                    "last_timestamp": None,
                    "event_types": [],
                },
            )
        elif order_id is not None:
            target = orders_by_client.setdefault(
                str(order_id),
                {
                    "client_order_id": None,
                    "order_id": order_id,
                    "state": None,
                    "terminal": False,
                    "filled_quantity": 0.0,
                    "last_fill_quantity": 0.0,
                    "average_price": None,
                    "last_sequence": None,
                    "last_timestamp": None,
                    "event_types": [],
                },
            )

        if target is not None and event_type.startswith("order_"):
            target["order_id"] = target.get("order_id") or order_id
            target["state"] = state or target.get("state")
            target["terminal"] = bool(target.get("state") in TERMINAL_REPLAY_ORDER_STATES)
            target["last_sequence"] = event.get("sequence")
            target["last_timestamp"] = event.get("timestamp")
            target["last_fill_quantity"] = last_fill_quantity
            if filled_quantity is not None:
                target["filled_quantity"] = filled_quantity
            elif event_type == "order_trade_update":
                target["filled_quantity"] = max(float(target.get("filled_quantity") or 0.0), last_fill_quantity)
            if average_price is not None:
                target["average_price"] = average_price
            target.setdefault("event_types", []).append(event_type)

        if event_type == "account_update":
            latest_account_update = event

    position_hint = None
    if latest_account_update is not None:
        payload = _event_payload(latest_account_update)
        positions = payload.get("positions") or []
        if positions:
            best = positions[0]
            for position in positions:
                qty = abs(float(position.get("pa") or position.get("positionAmt") or position.get("quantity") or 0.0))
                if qty > abs(float(best.get("pa") or best.get("positionAmt") or best.get("quantity") or 0.0)):
                    best = position
            position_hint = {
                "side": _position_side(best),
                "quantity": _position_quantity(best),
                "entry_price": _position_entry_price(best),
                "raw": best,
                "timestamp": latest_account_update.get("timestamp"),
                "sequence": latest_account_update.get("sequence"),
            }

    return {
        "orders_by_client_order_id": orders_by_client,
        "terminal_order_count": sum(1 for item in orders_by_client.values() if item.get("terminal")),
        "position_hint": position_hint,
        "latest_account_update_sequence": latest_account_update.get("sequence") if latest_account_update else None,
    }


def classify_unresolved_intents(
    *,
    intents: list[dict[str, Any]],
    remote_orders: list[dict[str, Any]],
    replay_state: Optional[dict[str, Any]] = None,
) -> list[IntentConvergence]:
    remote_by_client: dict[str, dict[str, Any]] = {}
    for order in remote_orders:
        info = order.get("info")
        remote_info = info if isinstance(info, dict) else {}
        client_id = order.get("clientOrderId") or remote_info.get("clientOrderId")
        if client_id:
            remote_by_client[str(client_id)] = order

    replay_by_client = ((replay_state or {}).get("orders_by_client_order_id") or {}) if isinstance(replay_state, dict) else {}
    results: list[IntentConvergence] = []
    for intent in intents:
        state = str(intent.get("state") or "unknown")
        client_id = intent.get("client_order_id")
        request_id = str(intent.get("request_id") or "")
        remote = remote_by_client.get(str(client_id)) if client_id else None
        replay = replay_by_client.get(str(client_id)) if client_id else None
        if not client_id:
            results.append(IntentConvergence(
                request_id=request_id,
                client_order_id=client_id,
                state=state,
                classification="missing_client_order_id",
                severity="critical",
                reason="Intent cannot be matched remotely without client_order_id",
            ))
            continue
        if remote is not None:
            results.append(IntentConvergence(
                request_id=request_id,
                client_order_id=client_id,
                state=state,
                classification="remote_open_order_present",
                severity="warning",
                reason="Remote open order still exists and requires local state convergence",
                exchange_order_id=intent.get("exchange_order_id"),
                remote_order_id=remote.get("id"),
            ))
            continue
        replay_state_name = _normalize_order_state((replay or {}).get("state"))
        replay_filled_quantity = float((replay or {}).get("filled_quantity") or 0.0)
        if replay_state_name in TERMINAL_REPLAY_ORDER_STATES:
            results.append(IntentConvergence(
                request_id=request_id,
                client_order_id=client_id,
                state=state,
                classification="replay_terminal_state",
                severity="info",
                reason=f"Replay recorded terminal state={replay_state_name}; intent can converge without open remote order",
                exchange_order_id=intent.get("exchange_order_id") or (replay or {}).get("order_id"),
            ))
            continue
        if replay_filled_quantity > 0.0:
            results.append(IntentConvergence(
                request_id=request_id,
                client_order_id=client_id,
                state=state,
                classification="replay_partial_fill_without_terminal",
                severity="warning",
                reason="Replay recorded fills but no terminal state or remote open order remains",
                exchange_order_id=intent.get("exchange_order_id") or (replay or {}).get("order_id"),
            ))
            continue
        if state in {"unknown", "submit_pending", "submitted"}:
            results.append(IntentConvergence(
                request_id=request_id,
                client_order_id=client_id,
                state=state,
                classification="submit_ack_ambiguous",
                severity="critical",
                reason="Intent has no remote open order and requires replay / order lookup resolution",
                exchange_order_id=intent.get("exchange_order_id"),
            ))
            continue
        if state in TERMINAL_INTENT_STATES:
            continue
        results.append(IntentConvergence(
            request_id=request_id,
            client_order_id=client_id,
            state=state,
            classification="operator_review_required",
            severity="warning",
            reason="Intent is non-terminal and does not cleanly map to remote state",
            exchange_order_id=intent.get("exchange_order_id"),
        ))
    return results


def recommend_recovery_actions(
    *,
    position: PositionConvergence,
    unresolved_intents: list[IntentConvergence],
    remote_only_orders: list[dict[str, Any]],
    local_only_orders: list[dict[str, Any]],
    watermark: ConvergenceWatermark,
) -> list[RecoveryAction]:
    actions: list[RecoveryAction] = []
    if not position.ok:
        actions.append(RecoveryAction(
            action="halt_and_manual_position_reconcile",
            severity=position.severity,
            reason="Position quantity / side / entry basis diverged at startup",
            metadata=position.to_dict(),
        ))
    blocking_intents = [item for item in unresolved_intents if item.classification != "replay_terminal_state"]
    if blocking_intents:
        highest = "critical" if any(item.severity == "critical" for item in blocking_intents) else "warning"
        actions.append(RecoveryAction(
            action="replay_and_lookup_unresolved_intents",
            severity=highest,
            reason="Submit intents remain unresolved after remote open-order snapshot",
            metadata={"count": len(blocking_intents)},
        ))
    if remote_only_orders:
        actions.append(RecoveryAction(
            action="adopt_or_cancel_remote_only_orders",
            severity="critical",
            reason="Exchange has open orders missing from local runtime state",
            metadata={"count": len(remote_only_orders)},
        ))
    if local_only_orders:
        actions.append(RecoveryAction(
            action="expire_local_only_orders",
            severity="warning",
            reason="Local runtime still tracks open orders absent from exchange snapshot",
            metadata={"count": len(local_only_orders)},
        ))
    if watermark.poll_fallback_required:
        actions.append(RecoveryAction(
            action="enable_poll_catchup",
            severity="warning",
            reason="Live user-data stream boundary unavailable; startup must rely on polling catch-up",
            metadata=watermark.to_dict(),
        ))
    if not actions:
        actions.append(RecoveryAction(
            action="resume_guarded_live",
            severity="info",
            reason="Startup convergence found no blocking divergence",
        ))
    return actions


def build_replay_hooks(events: list[dict[str, Any]]) -> dict[str, Any]:
    replayable = [event for event in events if bool(event.get("replayable", True))]
    order_events = [
        {
            "sequence": event.get("sequence"),
            "event_type": event.get("event_type"),
            "timestamp": event.get("timestamp"),
            "client_order_id": (_event_payload(event)).get("client_order_id"),
            "order_id": (_event_payload(event)).get("order_id"),
            "status": (_event_payload(event)).get("status"),
        }
        for event in replayable
        if str(event.get("event_type") or "").startswith("order_")
    ]
    fill_events = [
        {
            "sequence": event.get("sequence"),
            "event_type": event.get("event_type"),
            "timestamp": event.get("timestamp"),
            "client_order_id": (_event_payload(event)).get("client_order_id"),
            "order_id": (_event_payload(event)).get("order_id"),
            "last_fill_quantity": (_event_payload(event)).get("last_fill_quantity"),
            "last_fill_price": (_event_payload(event)).get("last_fill_price"),
            "average_price": (_event_payload(event)).get("average_price"),
        }
        for event in replayable
        if str(event.get("event_type") or "") == "order_trade_update"
        or str((_event_payload(event).get("execution_type") or "")).lower() == "trade"
    ]
    replay_state = summarize_replay_state(replayable)
    return {
        "order_update_events": order_events,
        "fill_events": fill_events,
        "last_order_update_sequence": order_events[-1]["sequence"] if order_events else None,
        "last_fill_sequence": fill_events[-1]["sequence"] if fill_events else None,
        "orders_by_client_order_id": replay_state["orders_by_client_order_id"],
        "terminal_order_count": replay_state["terminal_order_count"],
        "position_hint": replay_state["position_hint"],
        "latest_account_update_sequence": replay_state["latest_account_update_sequence"],
    }


def build_startup_convergence_report(
    *,
    environment: str,
    local_position: Optional[dict[str, Any]],
    remote_position: Optional[dict[str, Any]],
    unresolved_intents: list[dict[str, Any]],
    remote_only_orders: list[dict[str, Any]],
    local_only_orders: list[dict[str, Any]],
    events: Optional[list[dict[str, Any]]],
    boundary: Optional[dict[str, Any]],
) -> StartupConvergenceReport:
    events = events or []
    watermark = build_convergence_watermark(boundary=boundary, events=events)
    position = build_position_convergence(local_position=local_position, remote_position=remote_position)
    replay_hooks = build_replay_hooks(events)
    classified = classify_unresolved_intents(
        intents=unresolved_intents,
        remote_orders=remote_only_orders,
        replay_state={
            "orders_by_client_order_id": replay_hooks.get("orders_by_client_order_id") or {},
        },
    )
    actions = recommend_recovery_actions(
        position=position,
        unresolved_intents=classified,
        remote_only_orders=remote_only_orders,
        local_only_orders=local_only_orders,
        watermark=watermark,
    )
    ok = not any(action.severity == "critical" for action in actions)
    summary = {
        "critical_action_count": sum(1 for action in actions if action.severity == "critical"),
        "warning_action_count": sum(1 for action in actions if action.severity == "warning"),
        "unresolved_intent_count": len(classified),
        "blocking_unresolved_intent_count": sum(1 for item in classified if item.classification != "replay_terminal_state"),
        "remote_only_order_count": len(remote_only_orders),
        "local_only_order_count": len(local_only_orders),
        "replay_fill_event_count": watermark.replay_fill_event_count,
        "replay_order_event_count": watermark.replay_order_event_count,
        "position_ok": position.ok,
        "replay_terminal_order_count": replay_hooks.get("terminal_order_count") or 0,
    }
    return StartupConvergenceReport(
        ok=ok,
        timestamp=_now_iso(),
        environment=environment,
        watermark=watermark.to_dict(),
        position=position.to_dict(),
        unresolved_intents=[item.to_dict() for item in classified],
        replay_hooks=replay_hooks,
        actions=[action.to_dict() for action in actions],
        summary=summary,
    )
