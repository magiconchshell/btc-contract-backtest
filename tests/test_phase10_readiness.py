import json
from pathlib import Path

from btc_contract_backtest.live.submit_policy import PostSubmitPolicy


def test_post_submit_policy_decisions():
    policy = PostSubmitPolicy(allow_replace_on_stuck=True, cancel_partial_fill=False)
    assert policy.decide("stuck_open").action == "cancel_replace"
    assert policy.decide("partial_fill").action == "observe"


def test_live_readiness_check(tmp_path):
    import subprocess, sys

    gov = Path(tmp_path) / "gov.json"
    gov.write_text(json.dumps({"mode": "guarded_live", "emergency_stop": False, "maintenance": False}))
    audit = Path(tmp_path) / "audit.jsonl"
    audit.write_text(json.dumps({"event_type": "shadow_decision", "reconcile": {"differences": []}}) + "\n")
    approvals = Path(tmp_path) / "approvals.json"
    approvals.write_text(json.dumps({"requests": [], "approved_ids": [], "rejected_ids": []}))

    proc = subprocess.run(
        [sys.executable, "research/live_readiness_check.py", str(gov), str(audit), str(approvals)],
        cwd="/Users/magiconch/.openclaw/workspace/github-btc-backtest",
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["ready"] is True
