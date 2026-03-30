from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from btc_contract_backtest.runtime.engine_state_api import EngineStateStoreAPI
from btc_contract_backtest.runtime.engine_state_schema import normalize_legacy_state
from btc_contract_backtest.runtime.runtime_persistence import RuntimePersistence, RuntimeStepRecord


class JsonRuntimeStateStore(RuntimePersistence, EngineStateStoreAPI):
    def __init__(self, path: str, *, mode: str = "unknown", symbol: str = "UNKNOWN", leverage: float = 1.0):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.mode = mode
        self.symbol = symbol
        self.leverage = leverage
        self.state = normalize_legacy_state(self._load(), mode=mode, symbol=symbol, leverage=leverage)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text())

    def _serialize(self, value: Any):
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, dict):
            return {k: self._serialize(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._serialize(v) for v in value]
        return value

    def save(self):
        self.path.write_text(json.dumps(self.state, indent=2, ensure_ascii=False, default=str))

    def set_state_fields(self, **fields: Any) -> None:
        for key, value in fields.items():
            self.state[key] = self._serialize(value)

    def get_state(self) -> dict[str, Any]:
        return self.state

    def load_normalized_state(self) -> dict[str, Any]:
        return self.state

    def set_mode(self, mode: str) -> None:
        self.state["mode"] = mode

    def set_capital(self, capital: float | None) -> None:
        self.state["capital"] = capital

    def set_position(self, position: dict[str, Any] | None) -> None:
        self.state["position"] = self._serialize(position)

    def set_orders(self, orders: list[dict[str, Any]]) -> None:
        self.state["orders"] = self._serialize(orders)

    def append_fill(self, fill: dict[str, Any]) -> None:
        self.state.setdefault("fills", []).append(self._serialize(fill))

    def set_trades(self, trades: list[dict[str, Any]]) -> None:
        self.state["trades"] = self._serialize(trades)

    def append_operator_action(self, action: dict[str, Any]) -> None:
        self.state.setdefault("operator_actions", []).append(self._serialize(action))

    def set_governance_state(self, governance_state: dict[str, Any]) -> None:
        self.state["governance_state"] = self._serialize(governance_state)

    def set_watchdog(self, watchdog: dict[str, Any]) -> None:
        self.state["watchdog"] = self._serialize(watchdog)

    def set_last_runtime_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.state["last_runtime_snapshot"] = self._serialize(snapshot)

    def flush(self) -> None:
        self.save()

    def record_runtime_step(self, record: RuntimeStepRecord) -> None:
        self.state.setdefault("runtime_steps", []).append(self._serialize(record))

    def record_risk_event(self, event: dict[str, Any]) -> None:
        self.state.setdefault("risk_events", []).append(self._serialize(event))
