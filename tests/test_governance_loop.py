from pathlib import Path

from btc_contract_backtest.config.models import LiveRiskConfig, RiskConfig
from btc_contract_backtest.live.governance import (
    AlertSink,
    GovernancePolicy,
    GovernanceState,
    OperatorApprovalQueue,
    TradingMode,
)
from btc_contract_backtest.live.guarded_live import GuardedLiveExecutor
from btc_contract_backtest.live.audit_logger import AuditLogger
from btc_contract_backtest.live.exchange_adapter import AdapterResult


class FakeAdapter:
    def submit_order(self, order):
        return AdapterResult(ok=True, payload={"id": "ex-1", "status": "open"})


def test_approval_queue_lifecycle(tmp_path):
    approvals = OperatorApprovalQueue(str(Path(tmp_path) / "approvals.json"))
    approvals.request_approval("r1", {"symbol": "BTC/USDT"})
    approvals.approve("r1")
    assert approvals.is_approved("r1") is True
    req = approvals.consume_request("r1")
    assert req is not None
    assert approvals.consume_request("r1") is None


def test_governance_state_emergency_stop(tmp_path):
    state = GovernanceState(str(Path(tmp_path) / "gov.json"))
    state.set_mode(TradingMode.GUARDED_LIVE)
    state.set_emergency_stop(True)
    data = state.load()
    assert data["mode"] == TradingMode.GUARDED_LIVE.value
    assert data["emergency_stop"] is True


def test_process_approved_request_submits(tmp_path):
    policy = GovernancePolicy(RiskConfig(), LiveRiskConfig(), TradingMode.GUARDED_LIVE)
    approvals = OperatorApprovalQueue(str(Path(tmp_path) / "approvals.json"))
    alerts = AlertSink(str(Path(tmp_path) / "alerts.jsonl"))
    audit = AuditLogger(str(Path(tmp_path) / "audit.jsonl"))
    executor = GuardedLiveExecutor(FakeAdapter(), policy, approvals, alerts, audit)
    approvals.request_approval(
        "req-1", {"symbol": "BTC/USDT", "signal": 1, "quantity": 1.0, "notional": 100.0}
    )
    approvals.approve("req-1")
    result = executor.process_approved_request("req-1")
    assert result["status"] == "submitted"
