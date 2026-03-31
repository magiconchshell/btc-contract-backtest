from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from btc_contract_backtest.config.models import (
    ContractSpec,
    LiveRiskConfig,
    RiskConfig,
)
from btc_contract_backtest.live.exchange_constraints import (
    ExchangeConstraintChecker,
)


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
    metadata: Optional[dict] = None


class OperatorApprovalQueue:
    def __init__(self, path: str = "operator_approvals.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(
                json.dumps(
                    {
                        "requests": [],
                        "approved_ids": [],
                        "rejected_ids": [],
                    },
                    indent=2,
                )
            )

    def load(self) -> dict:
        return json.loads(self.path.read_text())

    def save(self, payload: dict):
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    def request_approval(self, request_id: str, payload: dict):
        data = self.load()
        data["requests"].append({"request_id": request_id, **payload})
        self.save(data)

    def approve(self, request_id: str):
        data = self.load()
        if request_id not in data["approved_ids"]:
            data["approved_ids"].append(request_id)
        self.save(data)

    def reject(self, request_id: str):
        data = self.load()
        if request_id not in data["rejected_ids"]:
            data["rejected_ids"].append(request_id)
        self.save(data)

    def is_approved(self, request_id: str) -> bool:
        data = self.load()
        return request_id in data.get("approved_ids", [])

    def is_rejected(self, request_id: str) -> bool:
        data = self.load()
        return request_id in data.get("rejected_ids", [])

    def consume_request(self, request_id: str) -> Optional[dict]:
        data = self.load()
        req = None
        remaining = []
        for item in data.get("requests", []):
            if item.get("request_id") == request_id and req is None:
                req = item
            else:
                remaining.append(item)
        data["requests"] = remaining
        self.save(data)
        return req


class AlertSink:
    def __init__(self, path: str = "live_alerts.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, alert_type: str, payload: dict, severity: str = "info"):
        record = {
            "alert_type": alert_type,
            "severity": severity,
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )


class GovernanceState:
    def __init__(self, path: str = "governance_state.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(
                json.dumps(
                    {
                        "mode": TradingMode.DISABLED.value,
                        "emergency_stop": False,
                        "maintenance": False,
                    },
                    indent=2,
                )
            )

    def load(self) -> dict:
        return json.loads(self.path.read_text())

    def save(self, payload: dict):
        self.path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    def set_mode(self, mode: TradingMode):
        data = self.load()
        data["mode"] = mode.value
        self.save(data)

    def set_emergency_stop(self, enabled: bool):
        data = self.load()
        data["emergency_stop"] = enabled
        self.save(data)

    def set_maintenance(self, enabled: bool):
        data = self.load()
        data["maintenance"] = enabled
        self.save(data)


class GovernancePolicy:
    def __init__(
        self,
        risk: RiskConfig,
        live_risk: LiveRiskConfig,
        mode: TradingMode,
        contract: Optional[ContractSpec] = None,
    ):
        self.risk = risk
        self.live_risk = live_risk
        self.mode = mode
        self.contract = contract
        self.constraint_checker = ExchangeConstraintChecker(contract) if contract is not None else None

    def evaluate(
        self,
        *,
        symbol: str,
        notional: float,
        signal: int,
        stale: bool,
        reconcile_ok: bool,
        watchdog_halted: bool,
        quantity: Optional[float] = None,
        reduce_only: bool = False,
        available_margin: Optional[float] = None,
        leverage: Optional[int] = None,
        position_side: int = 0,
        account_mode: str = "one_way",
        current_open_positions: int = 0,
        emergency_stop: bool = False,
        maintenance: bool = False,
        current_daily_loss_pct: float = 0.0,
    ) -> GovernanceDecision:
        if emergency_stop:
            return GovernanceDecision(False, "emergency_stop", severity="critical")
        if maintenance or self.mode in {
            TradingMode.DISABLED,
            TradingMode.MAINTENANCE,
        }:
            return GovernanceDecision(
                False,
                f"mode={self.mode.value}",
                severity="critical",
            )
        if watchdog_halted:
            return GovernanceDecision(False, "watchdog_halted", severity="critical")
        if stale:
            return GovernanceDecision(False, "stale_market_data", severity="critical")
        if not reconcile_ok:
            return GovernanceDecision(False, "reconcile_mismatch", severity="critical")
        if quantity is not None and quantity <= 0:
            return GovernanceDecision(
                False,
                "non_positive_quantity",
                severity="critical",
                metadata={"quantity": quantity},
            )
        if self.constraint_checker is not None and quantity is not None:
            constraint_result = self.constraint_checker.check(
                quantity=quantity,
                price=None,
                notional=notional,
                available_margin=available_margin,
                leverage=leverage,
                reduce_only=reduce_only,
                position_side=position_side,
                account_mode=account_mode,
                max_open_positions=self.live_risk.max_open_positions,
                current_open_positions=current_open_positions,
            )
            if not constraint_result.ok:
                first = constraint_result.violations[0]
                return GovernanceDecision(
                    False,
                    first["code"],
                    severity=first.get("severity", "critical"),
                    metadata={
                        "violations": constraint_result.violations,
                        "normalized": constraint_result.normalized,
                    },
                )
        if (
            self.risk.max_symbol_exposure_pct is not None
            and notional > self.risk.max_symbol_exposure_pct
        ):
            return GovernanceDecision(
                False,
                "symbol_exposure_limit",
                severity="critical",
                metadata={"notional": notional},
            )
        if (
            self.risk.max_daily_loss_pct is not None
            and current_daily_loss_pct >= self.risk.max_daily_loss_pct
        ):
            return GovernanceDecision(
                False,
                "daily_loss_limit",
                severity="critical",
                metadata={
                    "current_daily_loss_pct": current_daily_loss_pct,
                },
            )
        if self.mode == TradingMode.APPROVAL_REQUIRED:
            return GovernanceDecision(
                False,
                "operator_approval_required",
                severity="warning",
                requires_approval=True,
            )
        if self.mode == TradingMode.GUARDED_LIVE:
            return GovernanceDecision(True, "guarded_live_allowed", severity="info")
        return GovernanceDecision(False, f"mode={self.mode.value}_non_live", severity="info")

    def snapshot(self) -> dict:
        payload = {"mode": self.mode.value, "live_risk": asdict(self.live_risk), "risk": asdict(self.risk)}
        if self.contract is not None:
            payload["contract"] = asdict(self.contract)
        return payload
