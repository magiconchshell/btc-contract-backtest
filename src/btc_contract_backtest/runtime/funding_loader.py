from __future__ import annotations

import json
from bisect import bisect_right
from pathlib import Path


class FundingSnapshotStore:
    def __init__(self, path: str = "data/calibration/funding_snapshots.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._rows: list[dict] | None = None
        self._timestamps: list[str] | None = None

    def append(self, snapshot: dict) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(snapshot, ensure_ascii=False, default=str) + "\n")
        self._rows = None
        self._timestamps = None

    def load(self) -> list[dict]:
        if self._rows is not None:
            return self._rows
        if not self.path.exists():
            self._rows = []
            self._timestamps = []
            return self._rows
        rows = []
        timestamps = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            rows.append(row)
            timestamps.append(str(row.get("timestamp")))
        self._rows = rows
        self._timestamps = timestamps
        return rows

    def lookup(self, timestamp: str) -> dict | None:
        rows = self.load()
        timestamps = self._timestamps or []
        if not rows or not timestamps:
            return None
        idx = bisect_right(timestamps, str(timestamp)) - 1
        if idx < 0:
            return None
        return rows[idx]
