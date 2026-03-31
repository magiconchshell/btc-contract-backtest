from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from btc_contract_backtest.live.event_stream import (
    EventDrivenExecutionSource,
    EventRecorder,
)


@dataclass
class SequenceObservation:
    status: str
    source: str
    symbol: Optional[str]
    external_sequence: Optional[str]
    expected_external_sequence: Optional[int] = None
    gap_size: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EventSequenceMonitor:
    """Detect websocket/event-stream gaps, duplicates, and reorders.

    This is intentionally lightweight so it can be reused by CI harnesses,
    replay tests, and eventually real stream health checks.
    """

    def __init__(self):
        self._last_seen: dict[tuple[str, Optional[str]], int] = {}
        self.observations: list[dict[str, Any]] = []

    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        if value in (None, ""):
            return None
        try:
            return int(str(value))
        except Exception:  # noqa: BLE001
            return None

    def observe(self, event: dict[str, Any]) -> SequenceObservation:
        source = str(event.get("source") or "unknown")
        symbol = event.get("symbol")
        key = (source, symbol)
        external_sequence = event.get("external_sequence")
        seq = self._to_int(external_sequence)
        if seq is None:
            observation = SequenceObservation(
                status="non_numeric",
                source=source,
                symbol=symbol,
                external_sequence=(
                    None if external_sequence is None else str(external_sequence)
                ),
            )
            self.observations.append(observation.to_dict())
            return observation

        previous = self._last_seen.get(key)
        if previous is None:
            self._last_seen[key] = seq
            observation = SequenceObservation(
                status="ok",
                source=source,
                symbol=symbol,
                external_sequence=str(seq),
                expected_external_sequence=seq,
            )
            self.observations.append(observation.to_dict())
            return observation

        expected = previous + 1
        if seq == expected:
            self._last_seen[key] = seq
            observation = SequenceObservation(
                status="ok",
                source=source,
                symbol=symbol,
                external_sequence=str(seq),
                expected_external_sequence=expected,
            )
        elif seq > expected:
            self._last_seen[key] = seq
            observation = SequenceObservation(
                status="gap",
                source=source,
                symbol=symbol,
                external_sequence=str(seq),
                expected_external_sequence=expected,
                gap_size=seq - expected,
                details={"previous_external_sequence": previous},
            )
        else:
            observation = SequenceObservation(
                status="reorder_or_duplicate",
                source=source,
                symbol=symbol,
                external_sequence=str(seq),
                expected_external_sequence=expected,
                details={"previous_external_sequence": previous},
            )
        self.observations.append(observation.to_dict())
        return observation

    def reconnect_required(self) -> bool:
        return any(item.get("status") == "gap" for item in self.observations)

    def summary(self) -> dict[str, Any]:
        counts = {
            "ok": 0,
            "gap": 0,
            "reorder_or_duplicate": 0,
            "non_numeric": 0,
        }
        for item in self.observations:
            status = item.get("status")
            if status in counts:
                counts[status] += 1
        return {
            "counts": counts,
            "reconnect_required": counts["gap"] > 0,
            "observations": list(self.observations),
        }


@dataclass
class CancelReplaceRiskReport:
    ok: bool
    status: str
    notes: list[str] = field(default_factory=list)
    overlapping_open_orders: list[str] = field(default_factory=list)
    residual_filled_order_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResidualRiskInspector:
    TERMINAL_ORDER_STATES = {"canceled", "cancelled", "rejected", "expired"}
    FILLED_ORDER_STATES = {"filled", "closed"}
    OPEN_ORDER_STATES = {
        "new",
        "open",
        "partially_filled",
        "partially-filled",
        "partial",
        "submitted",
    }

    @classmethod
    def inspect_cancel_replace(
        cls,
        *,
        cancel_order_id: str,
        replacement_order_id: Optional[str],
        remote_orders: list[dict[str, Any]],
    ) -> CancelReplaceRiskReport:
        notes: list[str] = []
        overlapping: list[str] = []
        residual_fills: list[str] = []

        def _status(order: dict[str, Any]) -> str:
            return str(order.get("status") or order.get("state") or "").lower()

        old_order = None
        new_order = None
        for order in remote_orders:
            oid = order.get("id") or order.get("order_id")
            if oid == cancel_order_id:
                old_order = order
            if replacement_order_id is not None and oid == replacement_order_id:
                new_order = order

        if old_order is not None and _status(old_order) in cls.OPEN_ORDER_STATES:
            overlapping.append(cancel_order_id)
            notes.append("cancel_target_still_open")
        if new_order is not None and _status(new_order) in cls.OPEN_ORDER_STATES:
            overlapping.append(str(replacement_order_id))

        if old_order is not None and _status(old_order) in cls.FILLED_ORDER_STATES:
            residual_fills.append(cancel_order_id)
            notes.append("cancel_target_filled_during_replace")

        ok = True
        status = "clean"
        if len(overlapping) >= 2:
            ok = False
            status = "double_open_risk"
            notes.append("both_old_and_new_orders_open")
        elif (
            residual_fills
            and new_order is not None
            and _status(new_order) in cls.OPEN_ORDER_STATES
        ):
            ok = False
            status = "residual_exposure_risk"
            notes.append("filled_old_order_and_live_replacement")
        elif overlapping:
            status = "replace_pending"

        return CancelReplaceRiskReport(
            ok=ok,
            status=status,
            notes=notes,
            overlapping_open_orders=overlapping,
            residual_filled_order_ids=residual_fills,
        )


class SoakHarness:
    """Deterministic long-run harness foundation for CI-friendly event soak tests."""

    def __init__(
        self,
        recorder: EventRecorder | None = None,
        monitor: EventSequenceMonitor | None = None,
    ):
        self.source = EventDrivenExecutionSource(recorder or EventRecorder())
        self.monitor = monitor or EventSequenceMonitor()

    def ingest_events(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        ingested = []
        for event in events:
            row = self.source.ingest(event)
            ingested.append(row)
            self.monitor.observe(row)
        return {
            "processed": len(ingested),
            "boundary": self.source.boundary_state(),
            "monitor": self.monitor.summary(),
        }

    def restart_and_replay(self) -> dict[str, Any]:
        replayed = self.source.replay()
        return {
            "replayed": len(replayed),
            "boundary": self.source.boundary_state(),
        }
