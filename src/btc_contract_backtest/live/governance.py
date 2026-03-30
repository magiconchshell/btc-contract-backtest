from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

from btc_contract_backtest.config.models import LiveRiskConfig, RiskConfig


class TradingMode(str, Enum):
    DISABLED = "disabled"
    SHADOW = "shadow"
    PAPER = "paper"
    APPROVAL_REQUIRED = "approval_required"
    GUARDED_LIVE = "guarded_live"
    MAINTENANCE = "maintenance"


@dataclass
class GovernanceDecision:
    allowed: bool
    reason: str
    severity: str = "info"
    requires_approval: bool = False
    metadata: dict | None = None


class OperatorApprovalQueue:
    def __init__(self, path: str = "operator_approvals.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps({"requests": [], "approved_ids": []}, indent=2))

    def load(self) -> dict:
        return json.loads(self.path.read_text())

    def save(self, payload: dict):
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    def request_approval(self, request_id: str, payload: dict):
        data = self.load()
        data["requests"].append({"request_id": request_id, **payload})
        self.save(data)

    def is_approved(self, request_id: str) -> bool:
        data = self.load()
        return request_id in data.get("approved_ids", [])


class AlertSink:
    def __init__(self, path: str = "live_alerts.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, alert_type: str, payload: dict):
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"alert_type": alert_type, **payload}, ensure_ascii=False, default=str) + "\n")


class GovernancePolicy:
    def __init__(self, risk: RiskConfig, live_risk: LiveRiskConfig, mode: TradingMode):
        self.risk = risk
        self.live_risk = live_risk
        self.mode = mode

    def evaluate(
        self,
        *,
        symbol: str,
        notional: float,
        signal: int,
        stale: bool,
        reconcile_ok: bool,
        watchdog_halted: bool,
        current_daily_loss_pct: float = 0.0,
    ) -> GovernanceDecision:
        if self.mode in {TradingMode.DISABLED, TradingMode.MAINTENANCE}:
            return GovernanceDecision(False, f"mode={self.mode.value}", severity="critical")
        if watchdog_halted:
            return GovernanceDecision(False, "watchdog_halted", severity="critical")
        if stale:
            return GovernanceDecision(False, "stale_market_data", severity="critical")
        if not reconcile_ok:
            return GovernanceDecision(False, "reconcile_mismatch", severity="critical")
        if self.risk.max_symbol_exposure_pct is not None and notional > self.risk.max_symbol_exposure_pct:
            return GovernanceDecision(False, "symbol_exposure_limit", severity="critical", metadata={"notional": notional})
        if self.risk.max_daily_loss_pct is not None and current_daily_loss_pct >= self.risk.max_daily_loss_pct:
            return GovernanceDecision(False, "daily_loss_limit", severity="critical", metadata={"current_daily_loss_pct": current_daily_loss_pct})
        if self.mode == TradingMode.APPROVAL_REQUIRED:
            return GovernanceDecision(False, "operator_approval_required", severity="warning", requires_approval=True)
        if self.mode == TradingMode.GUARDED_LIVE:
            return GovernanceDecision(True, "guarded_live_allowed", severity="info")
        return GovernanceDecision(False, f"mode={self.mode.value}_non_live", severity="info")

    def snapshot(self) -> dict:
        return {"mode": self.mode.value, "live_risk": asdict(self.live_risk), "risk": asdict(self.risk)}
