from __future__ import annotations
from typing import Optional

from datetime import datetime, timezone

from btc_contract_backtest.engine.execution_models import Order, OrderStatus
from btc_contract_backtest.live.audit_logger import AuditLogger
from btc_contract_backtest.live.exchange_adapter import ExchangeExecutionAdapter
from btc_contract_backtest.live.governance import AlertSink
from btc_contract_backtest.runtime.order_state_bridge import apply_remote_status
from btc_contract_backtest.runtime.order_state_machine import CanonicalOrderRecord


class OrderLifecycleMonitor:
    def __init__(self, adapter: ExchangeExecutionAdapter, alerts: AlertSink, audit: AuditLogger):
        self.adapter = adapter
        self.alerts = alerts
        self.audit = audit

    def inspect(self, order: Order, record: Optional[CanonicalOrderRecord] = None):
        result = self.adapter.reconcile_order_status(order)
        if not result.ok:
            self.alerts.emit("order_reconcile_failed", {"timestamp": datetime.now(timezone.utc).isoformat(), "order_id": order.order_id, "error": result.error})
            self.audit.log("order_reconcile_failed", {"order_id": order.order_id, "error": result.error})
            return {"status": "error", "error": result.error, "record": record}

        mapped = result.payload["mapped_status"]
        remote = result.payload["remote"]
        if record is not None:
            filled_quantity = remote.get("filled")
            avg_fill_price = remote.get("average")
            exchange_order_id = remote.get("id")
            record = apply_remote_status(
                record,
                status=mapped,
                timestamp=datetime.now(timezone.utc).isoformat(),
                payload=remote,
                filled_quantity=None if filled_quantity is None else float(filled_quantity),
                avg_fill_price=None if avg_fill_price is None else float(avg_fill_price),
                exchange_order_id=exchange_order_id,
            )
        self.audit.log("order_reconcile", {"order_id": order.order_id, "mapped_status": mapped, "remote": remote})

        if mapped == OrderStatus.PARTIALLY_FILLED.value:
            self.alerts.emit("order_partial_fill", {"timestamp": datetime.now(timezone.utc).isoformat(), "order_id": order.order_id})
            return {"status": "partial_fill", "remote": remote, "record": record}
        if mapped == OrderStatus.NEW.value:
            self.alerts.emit("order_stuck_open", {"timestamp": datetime.now(timezone.utc).isoformat(), "order_id": order.order_id})
            return {"status": "stuck_open", "remote": remote, "record": record}
        return {"status": mapped, "remote": remote, "record": record}
