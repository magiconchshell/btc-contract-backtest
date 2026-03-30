from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class IncidentRecord:
    incident_id: str
    incident_type: str
    severity: str
    state: str
    timestamp: str
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)
    annotations: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IncidentStore:
    def __init__(self, path: str = "pilot_incidents.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({"incidents": []}, indent=2, ensure_ascii=False))

    def load(self) -> dict:
        return json.loads(self.path.read_text())

    def save(self, payload: dict):
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))

    def append(self, incident: IncidentRecord):
        payload = self.load()
        payload.setdefault("incidents", []).append(incident.to_dict())
        self.save(payload)
