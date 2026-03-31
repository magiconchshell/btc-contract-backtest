from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional, Any

from btc_contract_backtest.engine.execution_models import PositionState


SCHEMA_VERSION = 2


@dataclass
class EngineState:
    schema_version: int = SCHEMA_VERSION
    mode: str = "unknown"
    capital: Optional[float] = None
    position: Optional[dict[str, Any]] = None
    orders: list[dict[str, Any]] = field(default_factory=list)
    fills: list[dict[str, Any]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    risk_events: list[dict[str, Any]] = field(default_factory=list)
    governance_state: dict[str, Any] = field(default_factory=dict)
    operator_actions: list[dict[str, Any]] = field(default_factory=list)
    last_runtime_snapshot: dict[str, Any] = field(default_factory=dict)
    watchdog: dict[str, Any] = field(default_factory=dict)
    runtime_steps: list[dict[str, Any]] = field(default_factory=list)
    reconcile_report: dict[str, Any] = field(default_factory=dict)
    submit_ledger: dict[str, Any] = field(default_factory=dict)
    recovery_report: dict[str, Any] = field(default_factory=dict)
    startup_report: dict[str, Any] = field(default_factory=dict)
    event_stream_boundary: dict[str, Any] = field(default_factory=dict)
    execution_events: list[dict[str, Any]] = field(default_factory=list)
    updated_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_position(symbol: str = "UNKNOWN", leverage: float = 1.0) -> dict[str, Any]:
    return asdict(PositionState(symbol=symbol, leverage=leverage))


def normalize_legacy_state(raw: dict[str, Any], *, mode: str, symbol: str, leverage: float) -> dict[str, Any]:
    state = EngineState(mode=mode, position=default_position(symbol, leverage)).to_dict()

    if not raw:
        return state

    state["schema_version"] = raw.get("schema_version", SCHEMA_VERSION)
    state["mode"] = raw.get("mode", mode)
    state["capital"] = raw.get("capital", state["capital"])
    state["position"] = raw.get("position") or state["position"]
    state["orders"] = raw.get("orders", [])
    state["fills"] = raw.get("fills", [])
    state["trades"] = raw.get("trades", [])
    state["risk_events"] = raw.get("risk_events", [])
    state["governance_state"] = raw.get("governance_state", {})
    state["operator_actions"] = raw.get("operator_actions", [])
    state["last_runtime_snapshot"] = raw.get("last_runtime_snapshot") or raw.get("last_payload") or {}
    state["watchdog"] = raw.get("watchdog") or {
        "last_heartbeat_at": raw.get("last_heartbeat_at"),
        "consecutive_failures": raw.get("consecutive_failures", 0),
        "halted": raw.get("halted", False),
        "halt_reason": raw.get("halt_reason"),
    }
    state["runtime_steps"] = raw.get("runtime_steps", [])
    state["reconcile_report"] = raw.get("reconcile_report", {})
    state["submit_ledger"] = raw.get("submit_ledger", {})
    state["recovery_report"] = raw.get("recovery_report", {})
    state["startup_report"] = raw.get("startup_report", {})
    state["event_stream_boundary"] = raw.get("event_stream_boundary", {})
    state["execution_events"] = raw.get("execution_events", [])
    state["updated_at"] = raw.get("updated_at")
    return state
