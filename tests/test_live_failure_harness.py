from pathlib import Path

from btc_contract_backtest.config.models import ContractSpec, LiveRiskConfig, RiskConfig
from btc_contract_backtest.live.audit_logger import AuditLogger
from btc_contract_backtest.live.governance import (
    AlertSink,
    GovernancePolicy,
    OperatorApprovalQueue,
    TradingMode,
)
from btc_contract_backtest.live.guarded_live import GuardedLiveExecutor
from btc_contract_backtest.live.exchange_adapter import AdapterResult
from btc_contract_backtest.live.submit_ledger import SubmitLedger


class FlakyAdapter:
    def __init__(self):
        self.calls = []

    def submit_order(self, order):
        self.calls.append(("submit", order.client_order_id))
        return AdapterResult(ok=False, error="network_timeout")

    def fetch_open_orders_by_client_order_id(self, client_order_id):
        self.calls.append(("lookup", client_order_id))
        return AdapterResult(ok=True, payload=[])


def test_live_failure_harness_marks_unresolved_submit_unknown(tmp_path):
    policy = GovernancePolicy(
        RiskConfig(),
        LiveRiskConfig(),
        TradingMode.GUARDED_LIVE,
        contract=ContractSpec(symbol="BTC/USDT", leverage=3, lot_size=0.001),
    )
    approvals = OperatorApprovalQueue(str(Path(tmp_path) / "approvals.json"))
    alerts = AlertSink(str(Path(tmp_path) / "alerts.jsonl"))
    audit = AuditLogger(str(Path(tmp_path) / "audit.jsonl"))
    ledger = SubmitLedger(str(Path(tmp_path) / "submit_ledger.json"))
    adapter = FlakyAdapter()
    executor = GuardedLiveExecutor(
        adapter, policy, approvals, alerts, audit, submit_ledger=ledger
    )

    result = executor.submit_intended_order(
        symbol="BTC/USDT",
        signal=1,
        quantity=0.001,
        notional=10.0,
        stale=False,
        reconcile_ok=True,
        watchdog_halted=False,
    )
    assert result["status"] == "submit_failed"
    intent = ledger.get(result["request_id"])
    assert intent is not None
    assert intent["state"] == "unknown"
    assert adapter.calls[0][0] == "submit"
    assert adapter.calls[1][0] == "lookup"
