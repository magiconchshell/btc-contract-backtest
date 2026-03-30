from __future__ import annotations

from datetime import datetime, timezone

from btc_contract_backtest.engine.execution_models import Order, OrderStatus
from btc_contract_backtest.live.audit_logger import AuditLogger
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter
from btc_contract_backtest.live.governance import AlertSink


class OrderLifecycleMonitor:
    def __init__(self, adapter: ExchangeExecutionAdapter, alerts: AlertSink, audit: AuditLogger):
        self.adapter = adapter
        self.alerts = alerts
        self.audit = audit

    def inspect(self, order: Order):
        result = self.adapter.reconcile_order_status(order)
        if not result.ok:
            self.alerts.emit("order_reconcile_failed", {"timestamp": datetime.now(timezone.utc).isoformat(), "order_id": order.order_id, "error": result.error})
            self.audit.log("order_reconcile_failed", {"order_id": order.order_id, "error": result.error})
            return {"status": "error", "error": result.error}

        mapped = result.payload["mapped_status"]
        remote = result.payload["remote"]
        self.audit.log("order_reconcile", {"order_id": order.order_id, "mapped_status": mapped, "remote": remote})

        if mapped == OrderStatus.PARTIALLY_FILLED.value:
            self.alerts.emit("order_partial_fill", {"timestamp": datetime.now(timezone.utc).isoformat(), "order_id": order.order_id})
            return {"status": "partial_fill", "remote": remote}
        if mapped == OrderStatus.NEW.value:
            self.alerts.emit("order_stuck_open", {"timestamp": datetime.now(timezone.utc).isoformat(), "order_id": order.order_id})
            return {"status": "stuck_open", "remote": remote}
        return {"status": mapped, "remote": remote}
