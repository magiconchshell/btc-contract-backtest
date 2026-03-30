from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from btc_contract_backtest.live.governance import GovernanceState, OperatorApprovalQueue
from btc_contract_backtest.runtime.calibration_store import CalibrationSampleStore
from btc_contract_backtest.runtime.funding_loader import FundingSnapshotStore
from btc_contract_backtest.runtime.runtime_state_store import JsonRuntimeStateStore


@dataclass
class PilotReadinessReport:
    ready: bool
    score: float
    blocking: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OperatorPreflightReport:
    proceed: bool
    hard_blocks: list[str] = field(default_factory=list)
    soft_blocks: list[str] = field(default_factory=list)
    checklist: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PilotRiskEnvelope:
    enabled: bool = True
    max_symbols: int = 1
    max_open_positions: int = 1
    max_notional: float = 100.0
    require_approval: bool = True
    require_reconcile_after_submit: bool = True
    block_on_missing_funding: bool = True
    min_calibration_samples: int = 10
    min_readiness_score: float = 0.75

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PilotRiskEnvelopeStore:
    def __init__(self, path: str = "pilot_risk_envelope.json"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save(PilotRiskEnvelope())

    def load(self) -> PilotRiskEnvelope:
        return PilotRiskEnvelope(**json.loads(self.path.read_text()))

    def save(self, envelope: PilotRiskEnvelope):
        self.path.write_text(json.dumps(envelope.to_dict(), indent=2, ensure_ascii=False))


def build_pilot_readiness(
    *,
    state_file: str,
    governance_state_file: str,
    approval_file: str,
    calibration_samples_path: str = "data/calibration/samples.jsonl",
    funding_snapshots_path: str = "data/calibration/funding_snapshots.jsonl",
) -> PilotReadinessReport:
    state = JsonRuntimeStateStore(state_file, mode="governed_live").get_state()
    governance = GovernanceState(governance_state_file).load()
    approvals = OperatorApprovalQueue(approval_file).load()
    calibration_samples = CalibrationSampleStore(calibration_samples_path).load()
    funding_rows = FundingSnapshotStore(funding_snapshots_path).load()

    blocking = []
    warnings = []
    score = 1.0

    if state.get("watchdog", {}).get("halted"):
        blocking.append("watchdog_halted")
        score -= 0.35
    if governance.get("emergency_stop"):
        blocking.append("emergency_stop_enabled")
        score -= 0.40
    if governance.get("maintenance"):
        blocking.append("maintenance_mode_enabled")
        score -= 0.25
    if len(calibration_samples) < 10:
        warnings.append("low_calibration_sample_count")
        score -= 0.15
    if not funding_rows:
        warnings.append("missing_funding_snapshots")
        score -= 0.10
    if approvals.get("requests"):
        warnings.append("pending_operator_approvals")
        score -= 0.05
    if not state.get("orders") and not state.get("runtime_steps"):
        warnings.append("limited_runtime_activity")
        score -= 0.10

    score = max(0.0, min(1.0, score))
    ready = len(blocking) == 0 and score >= 0.75
    return PilotReadinessReport(
        ready=ready,
        score=score,
        blocking=blocking,
        warnings=warnings,
        evidence={
            "order_count": len(state.get("orders", [])),
            "runtime_step_count": len(state.get("runtime_steps", [])),
            "calibration_sample_count": len(calibration_samples),
            "funding_snapshot_count": len(funding_rows),
            "pending_approvals": len(approvals.get("requests", [])),
        },
    )


def build_operator_preflight(
    *,
    readiness: PilotReadinessReport,
    state_file: str,
    governance_state_file: str,
    envelope_file: str = "pilot_risk_envelope.json",
) -> OperatorPreflightReport:
    state = JsonRuntimeStateStore(state_file, mode="governed_live").get_state()
    governance = GovernanceState(governance_state_file).load()
    envelope = PilotRiskEnvelopeStore(envelope_file).load()

    hard_blocks = list(readiness.blocking)
    soft_blocks = list(readiness.warnings)
    checklist = {
        "readiness_score": readiness.score,
        "watchdog_halted": state.get("watchdog", {}).get("halted", False),
        "open_positions": 0 if not state.get("position") or state.get("position", {}).get("side", 0) == 0 else 1,
        "open_orders": len([o for o in state.get("orders", []) if o.get("state") not in {"filled", "canceled", "rejected", "expired"}]),
        "governance_mode": governance.get("mode"),
        "emergency_stop": governance.get("emergency_stop", False),
        "maintenance": governance.get("maintenance", False),
        "risk_envelope": envelope.to_dict(),
    }

    if readiness.score < envelope.min_readiness_score:
        hard_blocks.append("readiness_score_below_minimum")
    if checklist["open_positions"] > envelope.max_open_positions:
        hard_blocks.append("too_many_open_positions")
    if governance.get("mode") != "approval_required":
        soft_blocks.append("governance_mode_not_approval_required")
    if envelope.require_approval and governance.get("mode") == "guarded_live":
        soft_blocks.append("approval_bypass_mode_active")

    proceed = len(hard_blocks) == 0
    return OperatorPreflightReport(proceed=proceed, hard_blocks=hard_blocks, soft_blocks=soft_blocks, checklist=checklist)
