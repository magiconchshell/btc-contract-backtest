from __future__ import annotations

import json
from pathlib import Path

from btc_contract_backtest.engine.execution_models import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)


class SessionRecovery:
    def __init__(self, state_path: str):
        self.path = Path(state_path)

    def load_state(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    def restore_orders(self, state: dict) -> dict[str, Order]:
        restored = {}
        for raw in state.get("orders", []):
            order = Order(
                order_id=raw["order_id"],
                symbol=raw["symbol"],
                side=OrderSide(raw["side"]),
                order_type=OrderType(raw["order_type"]),
                quantity=raw["quantity"],
                price=raw.get("price"),
                stop_price=raw.get("stop_price"),
                reduce_only=raw.get("reduce_only", False),
                post_only=raw.get("post_only", False),
                client_order_id=raw.get("client_order_id"),
                exchange_order_id=raw.get("exchange_order_id"),
                status=OrderStatus(raw.get("status", "new")),
                filled_quantity=raw.get("filled_quantity", 0.0),
                avg_fill_price=raw.get("avg_fill_price"),
                created_at=raw.get("created_at"),
                updated_at=raw.get("updated_at"),
                last_error=raw.get("last_error"),
                tags=raw.get("tags", {}),
            )
            restored[order.order_id] = order
        return restored

    def dedupe_client_order_ids(self, orders: dict[str, Order]) -> list[str]:
        seen = set()
        duplicates = []
        for order in orders.values():
            if not order.client_order_id:
                continue
            if order.client_order_id in seen:
                duplicates.append(order.client_order_id)
            seen.add(order.client_order_id)
        return duplicates
