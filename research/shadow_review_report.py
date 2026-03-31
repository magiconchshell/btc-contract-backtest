#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from shadow_audit_tools import load_jsonl, summarize


def build_review(rows: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    reconcile_rows = [r for r in rows if r.get("event_type") == "reconcile"]
    blocked_rows = [r for r in rows if r.get("event_type") == "shadow_blocked"]
    decision_rows = [r for r in rows if r.get("event_type") == "shadow_decision"]

    latest_decision = decision_rows[-1] if decision_rows else None
    latest_block = blocked_rows[-1] if blocked_rows else None
    latest_reconcile = reconcile_rows[-1] if reconcile_rows else None

    review: dict[str, Any] = {
        "summary": summary,
        "latest_decision": latest_decision,
        "latest_block": latest_block,
        "latest_reconcile": latest_reconcile,
        "operator_flags": [],
    }

    if summary["reconcile_mismatches"] > 0:
        review["operator_flags"].append(
            "Investigate reconcile mismatches before enabling tighter automation"
        )
    if summary["unsafe_market_blocks"] > 0:
        review["operator_flags"].append(
            "Review unsafe market blocks and stale/mark consistency thresholds"
        )
    if summary["decision_count"] == 0:
        review["operator_flags"].append(
            "No shadow decisions recorded; verify strategy activity and data freshness"
        )

    return review


def write_review(
    audit_path: Path,
    review: dict[str, Any],
) -> tuple[Path, Path]:
    out_json = audit_path.with_suffix(".review.json")
    out_md = audit_path.with_suffix(".review.md")
    out_json.write_text(
        json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    lines = [
        "# Shadow Review Report",
        "",
        f"- total rows: {review['summary']['total_rows']}",
        f"- decisions: {review['summary']['decision_count']}",
        f"- reconcile mismatches: {review['summary']['reconcile_mismatches']}",
        f"- unsafe market blocks: {review['summary']['unsafe_market_blocks']}",
        "",
        "## Operator flags",
    ]
    if review["operator_flags"]:
        for flag in review["operator_flags"]:
            lines.append(f"- {flag}")
    else:
        lines.append("- none")

    out_md.write_text("\n".join(lines), encoding="utf-8")
    return out_md, out_json


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: shadow_review_report.py <shadow_audit.jsonl>")
    audit_path = Path(sys.argv[1])
    rows = load_jsonl(audit_path)
    summary = summarize(rows)
    review = build_review(rows, summary)
    md, js = write_review(audit_path, review)
    print(
        json.dumps(
            {"review_markdown": str(md), "review_json": str(js)},
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
