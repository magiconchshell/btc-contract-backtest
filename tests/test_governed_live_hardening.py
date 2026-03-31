import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

from btc_contract_backtest.config.models import LiveRiskConfig, RiskConfig
from btc_contract_backtest.live.governance import (
    GovernanceState,
    OperatorApprovalQueue,
    TradingMode,
)


def test_governance_cli_mode_and_emergency_stop(tmp_path):
    import subprocess, sys

    state_path = Path(tmp_path) / "gov.json"
    subprocess.run(
        [
            sys.executable,
            "research/governance_cli.py",
            str(state_path),
            "set-mode",
            "guarded_live",
        ],
        cwd=REPO_ROOT,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            "research/governance_cli.py",
            str(state_path),
            "emergency-stop",
            "true",
        ],
        cwd=REPO_ROOT,
        check=True,
    )
    data = json.loads(state_path.read_text())
    assert data["mode"] == TradingMode.GUARDED_LIVE.value
    assert data["emergency_stop"] is True


def test_governance_cli_approve_request(tmp_path):
    import subprocess, sys

    approval_path = Path(tmp_path) / "approvals.json"
    approvals = OperatorApprovalQueue(str(approval_path))
    approvals.request_approval("req-1", {"symbol": "BTC/USDT"})
    subprocess.run(
        [
            sys.executable,
            "research/governance_cli.py",
            str(approval_path),
            "approve",
            "req-1",
        ],
        cwd=REPO_ROOT,
        check=True,
    )
    data = json.loads(approval_path.read_text())
    assert "req-1" in data["approved_ids"]
