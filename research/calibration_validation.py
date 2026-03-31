#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

from btc_contract_backtest.runtime.calibration_engine import validate_samples
from btc_contract_backtest.runtime.calibration_models import CalibrationConfig
from btc_contract_backtest.runtime.calibration_store import CalibrationSampleStore


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "data/calibration/samples.jsonl"
    store = CalibrationSampleStore(path)
    samples = store.load()
    result = validate_samples(samples, CalibrationConfig())
    out = Path(path).with_suffix(".validation.json")
    out.write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        json.dumps(
            {"sample_count": result.sample_count, "validation": str(out)},
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
