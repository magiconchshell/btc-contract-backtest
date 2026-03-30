from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AuditLogger:
    def __init__(self, path: str = "shadow_audit.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event_type: str, payload: dict[str, Any]):
        row = {"event_type": event_type, **payload}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
