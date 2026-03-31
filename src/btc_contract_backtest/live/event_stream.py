from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional, Any


@dataclass
class ExecutionEvent:
    event_type: str
    timestamp: str
    payload: dict[str, Any] = field(default_factory=dict)
    sequence: Optional[int] = None
    source: str = "poll"

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
    def __init__(self, recorder: EventRecorder | None = None):
        self.recorder = recorder or EventRecorder()
        self.last_sequence: Optional[int] = None

    def emit(self, event_type: str, timestamp: str, payload: dict[str, Any], *, source: str = "poll", sequence: Optional[int] = None) -> dict[str, Any]:
        if sequence is None:
            sequence = 1 if self.last_sequence is None else self.last_sequence + 1
        self.last_sequence = sequence
        event = ExecutionEvent(event_type=event_type, timestamp=timestamp, payload=payload, sequence=sequence, source=source)
        self.recorder.append(event)
        return event.to_dict()

    def replay(self) -> list[dict[str, Any]]:
        return self.recorder.load()
