from __future__ import annotations

import json
from pathlib import Path


class ShadowRecovery:
    def __init__(self, state_path: str):
        self.path = Path(state_path)

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    def save(self, payload: dict):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, default=str))
