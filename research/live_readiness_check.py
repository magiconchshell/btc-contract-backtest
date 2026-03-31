#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys


def read_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text())


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


def main():
    if len(sys.argv) < 4:
        raise SystemExit(
            "usage: live_readiness_check.py <governance_state.json> <shadow_or_live_audit.jsonl> <approval.json>"
        )

    gov = read_json(Path(sys.argv[1]))
    audit_rows = load_jsonl(Path(sys.argv[2]))
    approvals = read_json(Path(sys.argv[3]))

    blocked = sum(
        1
        for r in audit_rows
        if r.get("event_type") in {"shadow_blocked", "live_session_blocked"}
    )
    mismatches = 0
    for r in audit_rows:
        result = r.get("result") or r.get("reconcile") or {}
        if isinstance(result, dict) and result.get("differences"):
            mismatches += 1

    checklist = {
        "mode_set": gov.get("mode") is not None,
        "not_in_emergency_stop": not gov.get("emergency_stop", False),
        "not_in_maintenance": not gov.get("maintenance", False),
        "approval_queue_accessible": isinstance(approvals.get("requests", []), list),
        "recent_blocked_events_reasonable": blocked < 10,
        "reconcile_mismatches_reasonable": mismatches < 5,
    }
    ready = all(checklist.values())
    payload = {
        "ready": ready,
        "checklist": checklist,
        "blocked_events": blocked,
        "reconcile_mismatches": mismatches,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
