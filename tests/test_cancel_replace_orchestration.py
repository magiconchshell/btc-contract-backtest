from pathlib import Path

from btc_contract_backtest.config.models import ContractSpec, LiveRiskConfig, RiskConfig
from btc_contract_backtest.live.audit_logger import AuditLogger
from btc_contract_backtest.live.governance import AlertSink, GovernancePolicy, OperatorApprovalQueue, TradingMode
from btc_contract_backtest.live.guarded_live import GuardedLiveExecutor
from btc_contract_backtest.live.exchange_adapter import AdapterResult
from btc_contract_backtest.runtime.order_state_bridge import apply_local_submit, canonical_record_from_order
from btc_contract_backtest.runtime.order_state_machine import CanonicalOrderState
from btc_contract_backtest.engine.execution_models import Order, OrderSide, OrderType


class CancelReplaceAdapter:
    def submit_order(self, order):
        return AdapterResult(ok=True, payload={"id": "ex-new", "status": "open"})

    def cancel_order(self, order_id, symbol=None):
        return {"id": order_id, "status": "canceled"}

    def cancel_replace_order(self, cancel_order_id, new_order):
        return AdapterResult(ok=True, payload={"cancel": {"id": cancel_order_id, "status": "canceled"}, "replace": {"id": "ex-new", "status": "open"}})


def test_cancel_replace_moves_record_into_pending_states(tmp_path):
    policy = GovernancePolicy(RiskConfig(), LiveRiskConfig(), TradingMode.GUARDED_LIVE, contract=ContractSpec(symbol="BTC/USDT", leverage=3, lot_size=0.001))
    approvals = OperatorApprovalQueue(str(Path(tmp_path) / "approvals.json"))
    alerts = AlertSink(str(Path(tmp_path) / "alerts.jsonl"))
    audit = AuditLogger(str(Path(tmp_path) / "audit.jsonl"))
    executor = GuardedLiveExecutor(CancelReplaceAdapter(), policy, approvals, alerts, audit)

    order = Order(order_id="o1", symbol="BTC/USDT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=0.001, client_order_id="c1")
    record = canonical_record_from_order(order, submission_mode="governed_live")
    record = apply_local_submit(record, timestamp="2026-01-01T00:00:00+00:00")
    result = executor.governed_cancel_replace("o1", symbol="BTC/USDT", new_signal=1, quantity=0.001, notional=10.0, record=record)

    assert result["status"] == "cancel_replaced"
    assert result["record"].state == CanonicalOrderState.REPLACE_PENDING.value
