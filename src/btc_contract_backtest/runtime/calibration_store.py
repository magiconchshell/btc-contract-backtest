from __future__ import annotations

import json
from pathlib import Path

from btc_contract_backtest.runtime.calibration_models import CalibrationSample


class CalibrationSampleStore:
    def __init__(self, path: str = "data/calibration/samples.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, sample: CalibrationSample) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(sample.to_dict(), ensure_ascii=False, default=str) + "\n")

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows
