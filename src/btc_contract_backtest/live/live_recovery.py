from __future__ import annotations

import json
from pathlib import Path


class LiveSessionRecovery:
    def __init__(self, path: str = "live_session_state.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    def save(self, payload: dict):
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, default=str)
        )
