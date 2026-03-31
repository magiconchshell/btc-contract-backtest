from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


OPEN_REMOTE_ORDER_STATES = {"new", "open", "acked", "partially_filled", "partial", "working"}
TERMINAL_INTENT_STATES = {"filled", "canceled", "rejected", "expired", "failed"}


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
    return float(value)


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
        or str((event.get("payload") or {}).get("execution_type") or "").lower() == "trade"
    ]
    upstream = boundary.get("upstream") if isinstance(boundary.get("upstream"), dict) else {}
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


def classify_unresolved_intents(
    *,
    intents: list[dict[str, Any]],
    remote_orders: list[dict[str, Any]],
) -> list[IntentConvergence]:
    remote_by_client: dict[str, dict[str, Any]] = {}
    for order in remote_orders:
        client_id = order.get("clientOrderId") or ((order.get("info") or {}).get("clientOrderId") if isinstance(order.get("info"), dict) else None)
        if client_id:
            remote_by_client[str(client_id)] = order

    results: list[IntentConvergence] = []
    for intent in intents:
        state = str(intent.get("state") or "unknown")
        client_id = intent.get("client_order_id")
        request_id = str(intent.get("request_id") or "")
        remote = remote_by_client.get(str(client_id)) if client_id else None
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
    if unresolved_intents:
        highest = "critical" if any(item.severity == "critical" for item in unresolved_intents) else "warning"
        actions.append(RecoveryAction(
            action="replay_and_lookup_unresolved_intents",
            severity=highest,
            reason="Submit intents remain unresolved after remote open-order snapshot",
            metadata={"count": len(unresolved_intents)},
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
            "client_order_id": (event.get("payload") or {}).get("client_order_id"),
            "order_id": (event.get("payload") or {}).get("order_id"),
            "status": (event.get("payload") or {}).get("status"),
        }
        for event in replayable
        if str(event.get("event_type") or "").startswith("order_")
    ]
    fill_events = [
        {
            "sequence": event.get("sequence"),
            "event_type": event.get("event_type"),
            "timestamp": event.get("timestamp"),
            "client_order_id": (event.get("payload") or {}).get("client_order_id"),
            "order_id": (event.get("payload") or {}).get("order_id"),
            "last_fill_quantity": (event.get("payload") or {}).get("last_fill_quantity"),
            "last_fill_price": (event.get("payload") or {}).get("last_fill_price"),
            "average_price": (event.get("payload") or {}).get("average_price"),
        }
        for event in replayable
        if str(event.get("event_type") or "") == "order_trade_update"
        or str((event.get("payload") or {}).get("execution_type") or "").lower() == "trade"
    ]
    return {
        "order_update_events": order_events,
        "fill_events": fill_events,
        "last_order_update_sequence": order_events[-1]["sequence"] if order_events else None,
        "last_fill_sequence": fill_events[-1]["sequence"] if fill_events else None,
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
    classified = classify_unresolved_intents(intents=unresolved_intents, remote_orders=remote_only_orders)
    replay_hooks = build_replay_hooks(events)
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
        "remote_only_order_count": len(remote_only_orders),
        "local_only_order_count": len(local_only_orders),
        "replay_fill_event_count": watermark.replay_fill_event_count,
        "replay_order_event_count": watermark.replay_order_event_count,
        "position_ok": position.ok,
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
