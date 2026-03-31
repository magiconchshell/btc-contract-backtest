from __future__ import annotations
from typing import Any, Callable, Optional

from dataclasses import dataclass
from datetime import datetime, timezone
import time

import ccxt

from btc_contract_backtest.engine.execution_models import Order, OrderStatus, ReconcileReport
from btc_contract_backtest.live.reconcile import build_detailed_reconcile_report


@dataclass
class AdapterResult:
    ok: bool
    payload: dict[str, Any] | list[dict[str, Any]] | None = None
    error: Optional[str] = None


class ExchangeExecutionAdapter:
    def __init__(self, exchange: ccxt.Exchange, symbol: str, max_retries: int = 3, retry_delay_seconds: float = 1.0):
        self.exchange = exchange
        self.symbol = symbol
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    def _retry(self, fn: Callable[[], dict[str, Any] | list[dict[str, Any]]]) -> AdapterResult:
        last_error = None
        for _ in range(self.max_retries):
            try:
                return AdapterResult(ok=True, payload=fn())
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                time.sleep(self.retry_delay_seconds)
        return AdapterResult(ok=False, error=last_error)

    def submit_order(self, order: Order) -> AdapterResult:
        def op():
            params = {}
            if order.reduce_only:
                params["reduceOnly"] = True
            if order.client_order_id:
                params["newClientOrderId"] = order.client_order_id
            payload = self.exchange.create_order(
                symbol=order.symbol,
                type=order.order_type.value.replace("_", "-"),
                side=order.side.value,
                amount=order.quantity,
                price=order.price,
                params=params,
            )
            return payload

        return self._retry(op)

    def cancel_order(self, order_id: str) -> AdapterResult:
        return self._retry(lambda: self.exchange.cancel_order(order_id, self.symbol))

    def cancel_replace_order(self, cancel_order_id: str, new_order: Order) -> AdapterResult:
        cancel_result = self.cancel_order(cancel_order_id)
        if not cancel_result.ok:
            return cancel_result
        submit_result = self.submit_order(new_order)
        if not submit_result.ok:
            return submit_result
        return AdapterResult(ok=True, payload={"cancel": cancel_result.payload, "replace": submit_result.payload})

    def fetch_open_orders(self) -> AdapterResult:
        return self._retry(lambda: self.exchange.fetch_open_orders(self.symbol))

    def fetch_balance(self) -> AdapterResult:
        return self._retry(lambda: self.exchange.fetch_balance())

    def fetch_positions(self) -> AdapterResult:
        return self._retry(lambda: self.exchange.fetch_positions([self.symbol]))

    def fetch_order(self, order_id: str) -> AdapterResult:
        return self._retry(lambda: self.exchange.fetch_order(order_id, self.symbol))

    def fetch_open_orders_by_client_order_id(self, client_order_id: str) -> AdapterResult:
        result = self.fetch_open_orders()
        if not result.ok:
            return result
        matches: list[dict[str, Any]] = []
        open_orders = result.payload if isinstance(result.payload, list) else []
        for row in open_orders:
            info = row.get("info")
            if row.get("clientOrderId") == client_order_id or (isinstance(info, dict) and info.get("clientOrderId") == client_order_id):
                matches.append(row)
        return AdapterResult(ok=True, payload=matches)

    def reconcile_order_status(self, order: Order) -> AdapterResult:
        def op():
            remote = self.exchange.fetch_order(order.exchange_order_id or order.order_id, order.symbol)
            status = str(remote.get("status", "")).lower()
            mapped = OrderStatus.FILLED if status == "closed" else OrderStatus.CANCELED if status == "canceled" else OrderStatus.PARTIALLY_FILLED if remote.get("filled", 0) not in (0, None) else OrderStatus.NEW
            return {"remote": remote, "mapped_status": mapped.value}

        return self._retry(op)

    def reconcile_state(self, local_position_side: int, local_open_orders: int, local_position: Optional[dict] = None, local_orders: Optional[list[dict]] = None) -> AdapterResult:
        positions = self.fetch_positions()
        open_orders = self.fetch_open_orders()
        if not positions.ok:
            return AdapterResult(ok=False, error=positions.error)
        if not open_orders.ok:
            return AdapterResult(ok=False, error=open_orders.error)

        remote_position_side = 0
        remote_positions_payload = positions.payload
        remote_positions = remote_positions_payload if isinstance(remote_positions_payload, list) else []
        for pos in remote_positions:
            contracts = float(pos.get("contracts") or pos.get("positionAmt") or 0.0)
            if contracts > 0:
                remote_position_side = 1
                break
            if contracts < 0:
                remote_position_side = -1
                break

        remote_orders_payload = open_orders.payload
        remote_orders = remote_orders_payload if isinstance(remote_orders_payload, list) else []
        remote_open_order_count = len(remote_orders)
        differences = []
        if remote_position_side != local_position_side:
            differences.append(f"position side mismatch local={local_position_side} remote={remote_position_side}")
        if remote_open_order_count != local_open_orders:
            differences.append(f"open order count mismatch local={local_open_orders} remote={remote_open_order_count}")

        details = build_detailed_reconcile_report(
            local_position=local_position or {"side": local_position_side, "quantity": 0.0, "entry_price": None},
            remote_positions=remote_positions,
            local_orders=local_orders or [],
            remote_orders=remote_orders,
        ).to_dict()
        if not details.get("ok", True):
            differences.extend([
                f"order_mismatch_count={details.get('summary', {}).get('order_mismatch_count', 0)}",
                f"orphan_local_order_count={details.get('summary', {}).get('orphan_local_order_count', 0)}",
                f"orphan_remote_order_count={details.get('summary', {}).get('orphan_remote_order_count', 0)}",
            ])
            if details.get("position_mismatch"):
                differences.append("detailed_position_mismatch")

        report = ReconcileReport(
            ok=len(differences) == 0 and bool(details.get("ok", False)),
            timestamp=datetime.now(timezone.utc).isoformat(),
            local_position_side=local_position_side,
            remote_position_side=remote_position_side,
            local_open_orders=local_open_orders,
            remote_open_orders=remote_open_order_count,
            differences=differences,
            details=details,
        )
        return AdapterResult(ok=True, payload=report.__dict__)
