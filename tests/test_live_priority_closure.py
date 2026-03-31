from pathlib import Path

from btc_contract_backtest.config.models import ContractSpec, LiveRiskConfig, RiskConfig
from btc_contract_backtest.live.audit_logger import AuditLogger
from btc_contract_backtest.live.governance import AlertSink, GovernancePolicy, OperatorApprovalQueue, TradingMode
from btc_contract_backtest.live.guarded_live import GuardedLiveExecutor
from btc_contract_backtest.live.order_monitor import OrderLifecycleMonitor
from btc_contract_backtest.live.submit_ledger import SubmitLedger
from btc_contract_backtest.engine.execution_models import Order, OrderSide, OrderType
from btc_contract_backtest.runtime.order_state_bridge import apply_local_submit, canonical_record_from_order
from btc_contract_backtest.runtime.order_state_machine import CanonicalOrderState
from btc_contract_backtest.live.exchange_adapter import AdapterResult


class RecoveringAdapter:
    def __init__(self):
        self.submits = 0

    def submit_order(self, order):
        self.submits += 1
        return AdapterResult(ok=False, error="timeout")

    def fetch_open_orders_by_client_order_id(self, client_order_id):
        return AdapterResult(ok=True, payload=[{"id": "ex-1", "clientOrderId": client_order_id, "status": "open", "side": "buy", "type": "market", "amount": 1.0, "filled": 0.0}])


class PartialAdapter:
    def reconcile_order_status(self, order):
        return AdapterResult(ok=True, payload={"mapped_status": "partially_filled", "remote": {"id": "ex-1", "status": "open", "filled": 0.5, "average": 100.5}})


def test_guarded_live_recovers_unknown_submit_via_client_order_lookup(tmp_path):
    policy = GovernancePolicy(RiskConfig(), LiveRiskConfig(), TradingMode.GUARDED_LIVE, contract=ContractSpec(symbol="BTC/USDT", leverage=3, lot_size=0.001))
    approvals = OperatorApprovalQueue(str(Path(tmp_path) / "approvals.json"))
    alerts = AlertSink(str(Path(tmp_path) / "alerts.jsonl"))
    audit = AuditLogger(str(Path(tmp_path) / "audit.jsonl"))
    ledger = SubmitLedger(str(Path(tmp_path) / "submit_ledger.json"))
    executor = GuardedLiveExecutor(RecoveringAdapter(), policy, approvals, alerts, audit, submit_ledger=ledger)

    result = executor.submit_intended_order(symbol="BTC/USDT", signal=1, quantity=0.001, notional=10.0, stale=False, reconcile_ok=True, watchdog_halted=False)
    assert result["status"] == "submitted_recovered"
    intent = ledger.get(result["request_id"])
    assert intent is not None
    assert intent["state"] == "submitted"
    assert intent["exchange_order_id"] == "ex-1"


def test_order_monitor_advances_canonical_record_on_partial_fill(tmp_path):
    alerts = AlertSink(str(Path(tmp_path) / "alerts.jsonl"))
    audit = AuditLogger(str(Path(tmp_path) / "audit.jsonl"))
    monitor = OrderLifecycleMonitor(PartialAdapter(), alerts, audit)
    order = Order(order_id="o1", symbol="BTC/USDT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1.0)
    record = canonical_record_from_order(order, submission_mode="governed_live")
    record = apply_local_submit(record, timestamp="2026-01-01T00:00:00+00:00")

    result = monitor.inspect(order, record=record)
    assert result["status"] == "partial_fill"
    assert result["record"].state == CanonicalOrderState.PARTIAL.value
    assert result["record"].filled_quantity == 0.5
