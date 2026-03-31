from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


OPEN_STATES = {"new", "open", "acked", "partially_filled", "partial", "working"}
TERMINAL_STATES = {"filled", "canceled", "rejected", "expired", "closed"}


@dataclass
class OrderMismatch:
    key: str
    mismatch_types: list[str] = field(default_factory=list)
    local: Optional[dict[str, Any]] = None
    remote: Optional[dict[str, Any]] = None
    severity: str = "warning"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PositionMismatch:
    mismatch_types: list[str] = field(default_factory=list)
    local: Optional[dict[str, Any]] = None
    remote: Optional[dict[str, Any]] = None
    severity: str = "warning"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DetailedReconcileReport:
    ok: bool
    timestamp: str
    local_position: dict[str, Any] = field(default_factory=dict)
    remote_position: dict[str, Any] = field(default_factory=dict)
    position_mismatch: Optional[dict[str, Any]] = None
    order_mismatches: list[dict[str, Any]] = field(default_factory=list)
    orphan_local_orders: list[dict[str, Any]] = field(default_factory=list)
    orphan_remote_orders: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_status(raw: Any) -> str:
    return str(raw or "").strip().lower()


def _is_open_status(status: str) -> bool:
    return _normalize_status(status) in OPEN_STATES


def _contracts(raw: dict[str, Any]) -> float:
    return float(
        raw.get("contracts")
        or raw.get("positionAmt")
        or raw.get("quantity")
        or raw.get("qty")
        or 0.0
    )


def _optional_float(value: Any) -> Optional[float]:
    return None if value in (None, "") else float(value)


def _position_side(raw: dict[str, Any]) -> int:
    qty = _contracts(raw)
    if qty > 0:
        return 1
    if qty < 0:
        return -1
    return 0


def _position_entry(raw: dict[str, Any]) -> Optional[float]:
    val = raw.get("entry_price")
    if val is None:
        val = raw.get("entryPrice")
    return _optional_float(val)


def _order_key(raw: dict[str, Any]) -> Optional[str]:
    return (
        raw.get("client_order_id")
        or raw.get("clientOrderId")
        or raw.get("exchange_order_id")
        or raw.get("id")
        or raw.get("order_id")
    )


def _normalize_local_order(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": _order_key(raw),
        "order_id": raw.get("order_id"),
        "client_order_id": raw.get("client_order_id"),
        "exchange_order_id": raw.get("exchange_order_id"),
        "side": raw.get("side"),
        "type": raw.get("order_type") or raw.get("type"),
        "quantity": float(raw.get("quantity") or 0.0),
        "filled_quantity": float(raw.get("filled_quantity") or 0.0),
        "avg_fill_price": _optional_float(raw.get("avg_fill_price")),
        "reduce_only": bool(raw.get("reduce_only", False)),
        "status": _normalize_status(raw.get("status") or raw.get("state")),
    }


def _normalize_remote_order(raw: dict[str, Any]) -> dict[str, Any]:
    side = raw.get("side")
    order_type = raw.get("type")
    amount = raw.get("amount")
    if amount is None:
        amount = raw.get("quantity")
    filled = raw.get("filled")
    if filled is None:
        filled = raw.get("filled_quantity")
    avg = raw.get("average")
    if avg is None:
        avg = raw.get("avg_fill_price")
    if isinstance(raw.get("info"), dict):
        reduce_only = bool((raw.get("info") or {}).get("reduceOnly"))
    else:
        reduce_only = bool(raw.get("reduceOnly", False))
    return {
        "key": _order_key(raw),
        "order_id": raw.get("order_id") or raw.get("id"),
        "client_order_id": (
            raw.get("client_order_id")
            or raw.get("clientOrderId")
            or (
                (raw.get("info") or {}).get("clientOrderId")
                if isinstance(raw.get("info"), dict)
                else raw.get("clientOrderId")
            )
        ),
        "exchange_order_id": raw.get("exchange_order_id") or raw.get("id"),
        "side": side,
        "type": order_type,
        "quantity": float(amount or 0.0),
        "filled_quantity": float(filled or 0.0),
        "avg_fill_price": _optional_float(avg),
        "reduce_only": reduce_only,
        "status": _normalize_status(raw.get("status")),
    }


def build_detailed_reconcile_report(
    *,
    local_position: Optional[dict[str, Any]],
    remote_positions: Optional[list[dict[str, Any]]],
    local_orders: Optional[list[dict[str, Any]]],
    remote_orders: Optional[list[dict[str, Any]]],
    quantity_tolerance: float = 1e-9,
    price_tolerance: float = 1e-9,
) -> DetailedReconcileReport:
    local_position = local_position or {}
    remote_positions = remote_positions or []
    local_orders = local_orders or []
    remote_orders = remote_orders or []

    remote_position_raw = next(
        (p for p in remote_positions if _position_side(p) != 0),
        remote_positions[0] if remote_positions else {},
    )
    local_side = int(local_position.get("side", 0) or 0)
    local_quantity = float(local_position.get("quantity") or 0.0)
    local_entry_price = _position_entry(local_position)
    normalized_local_position = {
        "side": local_side,
        "quantity": local_quantity,
        "entry_price": local_entry_price,
    }
    remote_side = _position_side(remote_position_raw)
    remote_quantity = abs(_contracts(remote_position_raw))
    remote_entry_price = _position_entry(remote_position_raw)
    normalized_remote_position = {
        "side": remote_side,
        "quantity": remote_quantity,
        "entry_price": remote_entry_price,
    }

    position_mismatch_types: list[str] = []
    if local_side != remote_side:
        position_mismatch_types.append("side")
    if abs(local_quantity - remote_quantity) > quantity_tolerance:
        position_mismatch_types.append("quantity")
    if local_entry_price is not None and remote_entry_price is not None:
        if abs(local_entry_price - remote_entry_price) > price_tolerance:
            position_mismatch_types.append("entry_price")

    position_mismatch = None
    if position_mismatch_types:
        position_mismatch = PositionMismatch(
            mismatch_types=position_mismatch_types,
            local=normalized_local_position,
            remote=normalized_remote_position,
            severity=(
                "critical"
                if "side" in position_mismatch_types
                or "quantity" in position_mismatch_types
                else "warning"
            ),
        ).to_dict()

    local_index = {}
    for raw in local_orders:
        norm = _normalize_local_order(raw)
        if norm["key"]:
            local_index[norm["key"]] = norm

    remote_index = {}
    for raw in remote_orders:
        norm = _normalize_remote_order(raw)
        if norm["key"]:
            remote_index[norm["key"]] = norm

    order_mismatches: list[dict[str, Any]] = []
    orphan_local_orders: list[dict[str, Any]] = []
    orphan_remote_orders: list[dict[str, Any]] = []

    for key, local in local_index.items():
        remote = remote_index.get(key)
        if remote is None:
            if _is_open_status(local["status"]):
                orphan_local_orders.append(local)
            continue
        mismatch_types: list[str] = []
        if str(local.get("side") or "") != str(remote.get("side") or ""):
            mismatch_types.append("side")
        if str(local.get("type") or "") != str(remote.get("type") or ""):
            mismatch_types.append("type")
        if (
            abs(
                float(local.get("quantity") or 0.0)
                - float(remote.get("quantity") or 0.0)
            )
            > quantity_tolerance
        ):
            mismatch_types.append("quantity")
        if (
            abs(
                float(local.get("filled_quantity") or 0.0)
                - float(remote.get("filled_quantity") or 0.0)
            )
            > quantity_tolerance
        ):
            mismatch_types.append("filled_quantity")
        local_avg = _optional_float(local.get("avg_fill_price"))
        remote_avg = _optional_float(remote.get("avg_fill_price"))
        if (
            local_avg is not None
            and remote_avg is not None
            and abs(local_avg - remote_avg) > price_tolerance
        ):
            mismatch_types.append("avg_fill_price")
        if bool(local.get("reduce_only")) != bool(remote.get("reduce_only")):
            mismatch_types.append("reduce_only")
        if _normalize_status(local.get("status")) != _normalize_status(
            remote.get("status")
        ):
            mismatch_types.append("status")
        if mismatch_types:
            severity = (
                "critical"
                if any(
                    item in {"quantity", "filled_quantity", "side", "reduce_only"}
                    for item in mismatch_types
                )
                else "warning"
            )
            order_mismatches.append(
                OrderMismatch(
                    key=key,
                    mismatch_types=mismatch_types,
                    local=local,
                    remote=remote,
                    severity=severity,
                ).to_dict()
            )

    for key, remote in remote_index.items():
        if key not in local_index and _is_open_status(remote["status"]):
            orphan_remote_orders.append(remote)

    ok = not position_mismatch and not order_mismatches and not orphan_local_orders and not orphan_remote_orders
    summary = {
        "position_mismatch": bool(position_mismatch),
        "order_mismatch_count": len(order_mismatches),
        "orphan_local_order_count": len(orphan_local_orders),
        "orphan_remote_order_count": len(orphan_remote_orders),
    }

    return DetailedReconcileReport(
        ok=ok,
        timestamp=_now_iso(),
        local_position=normalized_local_position,
        remote_position=normalized_remote_position,
        position_mismatch=position_mismatch,
        order_mismatches=order_mismatches,
        orphan_local_orders=orphan_local_orders,
        orphan_remote_orders=orphan_remote_orders,
        summary=summary,
    )
