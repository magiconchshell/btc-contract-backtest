from pathlib import Path

from btc_contract_backtest.config.models import LiveRiskConfig, RiskConfig
from btc_contract_backtest.live.governance import AlertSink, GovernancePolicy, OperatorApprovalQueue, TradingMode
from btc_contract_backtest.live.guarded_live import GuardedLiveExecutor
from btc_contract_backtest.live.audit_logger import AuditLogger
from btc_contract_backtest.live.exchange_adapter import AdapterResult
from btc_contract_backtest.live.order_monitor import OrderLifecycleMonitor
from btc_contract_backtest.engine.execution_models import Order, OrderSide, OrderType


class FakeAdapter:
    def submit_order(self, order):
        return AdapterResult(ok=True, payload={"id": "ex-1", "status": "open"})

    def cancel_replace_order(self, cancel_order_id, new_order):
        return AdapterResult(ok=True, payload={"id": "ex-2", "status": "open", "replaces": cancel_order_id})

    def reconcile_order_status(self, order):
        return AdapterResult(ok=True, payload={"mapped_status": "partially_filled", "remote": {"id": order.order_id, "status": "open", "filled": 0.5}})


def test_governed_cancel_replace(tmp_path):
    policy = GovernancePolicy(RiskConfig(), LiveRiskConfig(), TradingMode.GUARDED_LIVE)
    approvals = OperatorApprovalQueue(str(Path(tmp_path) / "approvals.json"))
    alerts = AlertSink(str(Path(tmp_path) / "alerts.jsonl"))
    audit = AuditLogger(str(Path(tmp_path) / "audit.jsonl"))
    executor = GuardedLiveExecutor(FakeAdapter(), policy, approvals, alerts, audit)
    result = executor.governed_cancel_replace("old-1", symbol="BTC/USDT", new_signal=1, quantity=1.0, notional=100.0)
    assert result["status"] == "cancel_replaced"


def test_order_monitor_detects_partial_fill(tmp_path):
    alerts = AlertSink(str(Path(tmp_path) / "alerts.jsonl"))
    audit = AuditLogger(str(Path(tmp_path) / "audit.jsonl"))
    monitor = OrderLifecycleMonitor(FakeAdapter(), alerts, audit)
    order = Order(order_id="o1", symbol="BTC/USDT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1.0)
    result = monitor.inspect(order)
    assert result["status"] == "partial_fill"
