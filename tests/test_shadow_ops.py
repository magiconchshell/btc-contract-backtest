import json
from pathlib import Path

from btc_contract_backtest.live.audit_logger import AuditLogger


def test_audit_logger_rotation(tmp_path):
    path = Path(tmp_path) / "audit.jsonl"
    logger = AuditLogger(str(path), rotate_max_bytes=50)
    logger.log("evt", {"x": "a" * 100})
    logger.log("evt", {"x": "b" * 100})
    rotated = Path(str(path) + ".1")
    assert path.exists()
    assert rotated.exists()


def test_shadow_summary_and_review_tools(tmp_path):
    audit = Path(tmp_path) / "shadow.jsonl"
    audit.write_text(
        "\n".join(
            [
                json.dumps({"event_type": "reconcile", "result": {"ok": False, "differences": ["x"]}}),
                json.dumps({"event_type": "shadow_blocked", "reason": "snapshot_safety_failed", "risk_events": [{"event_type": "mark_inconsistency"}]}),
                json.dumps({"event_type": "shadow_decision", "signal": 1}),
            ]
        ),
        encoding="utf-8",
    )

    import subprocess, sys

    p1 = subprocess.run([sys.executable, "research/shadow_audit_tools.py", str(audit)], cwd="/Users/magiconch/.openclaw/workspace/github-btc-backtest", check=True, capture_output=True, text=True)
    p2 = subprocess.run([sys.executable, "research/shadow_review_report.py", str(audit)], cwd="/Users/magiconch/.openclaw/workspace/github-btc-backtest", check=True, capture_output=True, text=True)
    assert "summary" in p1.stdout
    assert "review_markdown" in p2.stdout
