from __future__ import annotations

import json
from pathlib import Path


class FileAlertTransport:
    def __init__(self, path: str = "live_alerts.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def send(self, alert_type: str, payload: dict):
        with self.path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {"alert_type": alert_type, **payload},
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )
