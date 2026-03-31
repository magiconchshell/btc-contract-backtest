#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import sys


def load_jsonl(path: Path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def summarize(rows: list[dict]):
    counts = Counter(r.get("event_type", "unknown") for r in rows)
    alerts = [r for r in rows if r.get("alert_type")]
    incidents = [
        r
        for r in rows
        if r.get("event_type")
        in {
            "governance_submit_failed",
            "order_reconcile_failed",
            "governed_cancel_replace_failed",
        }
    ]
    return {
        "total_rows": len(rows),
        "event_counts": dict(counts),
        "alert_count": len(alerts),
        "incident_count": len(incidents),
    }


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: live_incident_report.py <audit-or-alert-jsonl>")
    path = Path(sys.argv[1])
    rows = load_jsonl(path)
    summary = summarize(rows)
    out = path.with_suffix(".incidents.json")
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {"summary": summary, "output": str(out)}, indent=2, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
