from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeStepRecord:
    timestamp: str
    event: str
    signal: int | None = None
    snapshot: dict[str, Any] = field(default_factory=dict)
    intended_order: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimePersistence:
    def record_runtime_step(self, record: RuntimeStepRecord) -> None:
        raise NotImplementedError

    def record_risk_event(self, event: dict[str, Any]) -> None:
        raise NotImplementedError


class InMemoryRuntimePersistence(RuntimePersistence):
    def __init__(self):
        self.steps: list[RuntimeStepRecord] = []
        self.risk_events: list[dict[str, Any]] = []

    def record_runtime_step(self, record: RuntimeStepRecord) -> None:
        self.steps.append(record)

    def record_risk_event(self, event: dict[str, Any]) -> None:
        self.risk_events.append(event)
