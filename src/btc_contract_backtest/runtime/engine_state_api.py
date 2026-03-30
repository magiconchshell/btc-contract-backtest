from __future__ import annotations

from typing import Any


class EngineStateStoreAPI:
    def get_state(self) -> dict[str, Any]:
        raise NotImplementedError

    def set_mode(self, mode: str) -> None:
        raise NotImplementedError

    def set_capital(self, capital: float | None) -> None:
        raise NotImplementedError

    def set_position(self, position: dict[str, Any] | None) -> None:
        raise NotImplementedError

    def set_orders(self, orders: list[dict[str, Any]]) -> None:
        raise NotImplementedError

    def upsert_order(self, order: dict[str, Any]) -> None:
        raise NotImplementedError

    def append_fill(self, fill: dict[str, Any]) -> None:
        raise NotImplementedError

    def set_trades(self, trades: list[dict[str, Any]]) -> None:
        raise NotImplementedError

    def append_operator_action(self, action: dict[str, Any]) -> None:
        raise NotImplementedError

    def set_governance_state(self, governance_state: dict[str, Any]) -> None:
        raise NotImplementedError

    def set_watchdog(self, watchdog: dict[str, Any]) -> None:
        raise NotImplementedError

    def set_last_runtime_snapshot(self, snapshot: dict[str, Any]) -> None:
        raise NotImplementedError

    def flush(self) -> None:
        raise NotImplementedError
