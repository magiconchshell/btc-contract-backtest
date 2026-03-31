from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AuditLogger:
    def __init__(
        self, path: str = "shadow_audit.jsonl", rotate_max_bytes: int = 2_000_000
    ):
        self.path = Path(path)
        self.rotate_max_bytes = rotate_max_bytes
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _rotate_if_needed(self):
        if not self.path.exists():
            return
        if self.path.stat().st_size < self.rotate_max_bytes:
            return
        rotated = self.path.with_suffix(self.path.suffix + ".1")
        if rotated.exists():
            rotated.unlink()
        self.path.rename(rotated)

    def log(self, event_type: str, payload: dict[str, Any]):
        self._rotate_if_needed()
        row = {"event_type": event_type, **payload}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
