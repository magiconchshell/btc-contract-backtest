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
    event_counts = Counter(r.get("event_type", "unknown") for r in rows)
    blocked = [r for r in rows if r.get("event_type") == "shadow_blocked"]
    decisions = [r for r in rows if r.get("event_type") == "shadow_decision"]
    reconciles = [r for r in rows if r.get("event_type") == "reconcile"]

    reconcile_mismatches = 0
    for r in reconciles:
        result = r.get("result", {})
        if isinstance(result, dict) and result.get("ok") is False:
            reconcile_mismatches += 1
        elif isinstance(result, dict) and result.get("differences"):
            reconcile_mismatches += 1

    blocked_reasons = Counter(r.get("reason", "unknown") for r in blocked)
    unsafe_markets = 0
    for r in blocked:
        for evt in r.get("risk_events", []):
            if evt.get("event_type") in {"stale_data", "mark_inconsistency"}:
                unsafe_markets += 1
                break

    return {
        "total_rows": len(rows),
        "event_counts": dict(event_counts),
        "blocked_reasons": dict(blocked_reasons),
        "reconcile_mismatches": reconcile_mismatches,
        "unsafe_market_blocks": unsafe_markets,
        "decision_count": len(decisions),
    }


def write_reports(audit_path: Path, summary: dict):
    out_md = audit_path.with_suffix(".summary.md")
    out_json = audit_path.with_suffix(".summary.json")
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Shadow Audit Summary",
        "",
        f"- total rows: {summary['total_rows']}",
        f"- decision count: {summary['decision_count']}",
        f"- reconcile mismatches: {summary['reconcile_mismatches']}",
        f"- unsafe market blocks: {summary['unsafe_market_blocks']}",
        "",
        "## Event counts",
    ]
    for k, v in summary["event_counts"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Blocked reasons")
    for k, v in summary["blocked_reasons"].items():
        lines.append(f"- {k}: {v}")

    out_md.write_text("\n".join(lines), encoding="utf-8")
    return out_md, out_json


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: shadow_audit_tools.py <shadow_audit.jsonl>")
    audit_path = Path(sys.argv[1])
    rows = load_jsonl(audit_path)
    summary = summarize(rows)
    md, js = write_reports(audit_path, summary)
    print(json.dumps({"summary": summary, "markdown": str(md), "json": str(js)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
