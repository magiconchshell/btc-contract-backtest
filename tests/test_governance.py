import json
from pathlib import Path

from btc_contract_backtest.config.models import LiveRiskConfig, RiskConfig
from btc_contract_backtest.live.governance import (
    AlertSink,
    GovernancePolicy,
    OperatorApprovalQueue,
    TradingMode,
)
from btc_contract_backtest.live.guarded_live import GuardedLiveExecutor
from btc_contract_backtest.live.audit_logger import AuditLogger
from btc_contract_backtest.live.exchange_adapter import AdapterResult


class FakeAdapter:
    def submit_order(self, order):
        return AdapterResult(ok=True, payload={"id": "ex-1", "status": "open"})


def test_governance_blocks_stale_market():
    policy = GovernancePolicy(RiskConfig(), LiveRiskConfig(), TradingMode.GUARDED_LIVE)
    decision = policy.evaluate(
        symbol="BTC/USDT",
        notional=100,
        signal=1,
        stale=True,
        reconcile_ok=True,
        watchdog_halted=False,
    )
    assert decision.allowed is False
    assert decision.reason == "stale_market_data"


def test_governance_requires_approval_when_mode_is_approval_required(tmp_path):
    policy = GovernancePolicy(
        RiskConfig(), LiveRiskConfig(), TradingMode.APPROVAL_REQUIRED
    )
    approvals = OperatorApprovalQueue(str(Path(tmp_path) / "approvals.json"))
    alerts = AlertSink(str(Path(tmp_path) / "alerts.jsonl"))
    audit = AuditLogger(str(Path(tmp_path) / "audit.jsonl"))
    executor = GuardedLiveExecutor(FakeAdapter(), policy, approvals, alerts, audit)
    result = executor.submit_intended_order(
        symbol="BTC/USDT",
        signal=1,
        quantity=1.0,
        notional=100.0,
        stale=False,
        reconcile_ok=True,
        watchdog_halted=False,
    )
    assert result["status"] == "pending_approval"
    data = approvals.load()
    assert len(data["requests"]) == 1


def test_governance_submits_when_guarded_live_allows(tmp_path):
    policy = GovernancePolicy(RiskConfig(), LiveRiskConfig(), TradingMode.GUARDED_LIVE)
    approvals = OperatorApprovalQueue(str(Path(tmp_path) / "approvals.json"))
    alerts = AlertSink(str(Path(tmp_path) / "alerts.jsonl"))
    audit = AuditLogger(str(Path(tmp_path) / "audit.jsonl"))
    executor = GuardedLiveExecutor(FakeAdapter(), policy, approvals, alerts, audit)
    result = executor.submit_intended_order(
        symbol="BTC/USDT",
        signal=1,
        quantity=1.0,
        notional=100.0,
        stale=False,
        reconcile_ok=True,
        watchdog_halted=False,
    )
    assert result["status"] == "submitted"
