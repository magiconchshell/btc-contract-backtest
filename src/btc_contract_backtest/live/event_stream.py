from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol


class RawExecutionEventSource(Protocol):
    """Interface for exchange-backed event sources.

    The first implementation is Binance Futures websocket/user-data oriented,
    but the normalized plane is intentionally exchange-agnostic.
    """

    def source_name(self) -> str:
        ...

    def source_kind(self) -> str:
        ...

    def is_live(self) -> bool:
        ...

    def describe(self) -> dict[str, Any]:
        ...


@dataclass
class ExecutionEvent:
    event_type: str
    timestamp: str
    payload: dict[str, Any] = field(default_factory=dict)
    sequence: Optional[int] = None
    source: str = "poll"
    source_kind: str = "poll"
    event_id: Optional[str] = None
    exchange_timestamp: Optional[str] = None
    received_at: Optional[str] = None
    symbol: Optional[str] = None
    external_sequence: Optional[str] = None
    replayable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EventRecorder:
    def __init__(self, path: str = "execution_events.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: ExecutionEvent | dict[str, Any]) -> None:
        row = event.to_dict() if isinstance(event, ExecutionEvent) else dict(event)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows


class EventDrivenExecutionSource:
    def __init__(
        self,
        recorder: EventRecorder | None = None,
        upstream: RawExecutionEventSource | None = None,
    ):
        self.recorder = recorder or EventRecorder()
        self.upstream = upstream
        self.last_sequence: Optional[int] = None
        self.last_event_timestamp: Optional[str] = None
        self.last_received_at: Optional[str] = None
        self.last_external_sequence: Optional[str] = None

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def next_sequence(self, sequence: Optional[int] = None) -> int:
        if sequence is None:
            sequence = 1 if self.last_sequence is None else self.last_sequence + 1
        elif self.last_sequence is not None and sequence <= self.last_sequence:
            sequence = self.last_sequence + 1
        self.last_sequence = sequence
        return sequence

    def emit(
        self,
        event_type: str,
        timestamp: str,
        payload: dict[str, Any],
        *,
        source: str = "poll",
        source_kind: str = "poll",
        sequence: Optional[int] = None,
        event_id: Optional[str] = None,
        exchange_timestamp: Optional[str] = None,
        received_at: Optional[str] = None,
        symbol: Optional[str] = None,
        external_sequence: Optional[str] = None,
        replayable: bool = True,
    ) -> dict[str, Any]:
        sequence = self.next_sequence(sequence)
        received_at = received_at or self.now_iso()
        self.last_event_timestamp = timestamp
        self.last_received_at = received_at
        self.last_external_sequence = external_sequence
        event = ExecutionEvent(
            event_type=event_type,
            timestamp=timestamp,
            payload=payload,
            sequence=sequence,
            source=source,
            source_kind=source_kind,
            event_id=event_id,
            exchange_timestamp=exchange_timestamp,
            received_at=received_at,
            symbol=symbol,
            external_sequence=external_sequence,
            replayable=replayable,
        )
        self.recorder.append(event)
        return event.to_dict()

    def ingest(self, event: ExecutionEvent | dict[str, Any]) -> dict[str, Any]:
        row = event.to_dict() if isinstance(event, ExecutionEvent) else dict(event)
        return self.emit(
            row["event_type"],
            row["timestamp"],
            row.get("payload") or {},
            source=row.get("source") or "poll",
            source_kind=row.get("source_kind") or row.get("source") or "poll",
            sequence=row.get("sequence"),
            event_id=row.get("event_id"),
            exchange_timestamp=row.get("exchange_timestamp"),
            received_at=row.get("received_at"),
            symbol=row.get("symbol"),
            external_sequence=row.get("external_sequence"),
            replayable=bool(row.get("replayable", True)),
        )

    def boundary_state(self) -> dict[str, Any]:
        upstream = self.upstream.describe() if self.upstream is not None else None
        return {
            "last_sequence": self.last_sequence,
            "last_event_timestamp": self.last_event_timestamp,
            "last_received_at": self.last_received_at,
            "last_external_sequence": self.last_external_sequence,
            "upstream": upstream,
            "poll_fallback_required": self.requires_poll_fallback(),
        }

    def requires_poll_fallback(self) -> bool:
        if self.upstream is None:
            return True
        return not self.upstream.is_live()

    def replay(self) -> list[dict[str, Any]]:
        rows = self.recorder.load()
        if rows:
            last = rows[-1]
            self.last_sequence = last.get("sequence")
            self.last_event_timestamp = last.get("timestamp")
            self.last_received_at = last.get("received_at")
            self.last_external_sequence = last.get("external_sequence")
        return rows
