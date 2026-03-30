from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from btc_contract_backtest.live.incident_store import IncidentStore
from btc_contract_backtest.live.pilot_controls import OperatorPreflightReport, PilotReadinessReport, PilotRiskEnvelopeStore
from btc_contract_backtest.runtime.calibration_store import CalibrationSampleStore
from btc_contract_backtest.runtime.funding_loader import FundingSnapshotStore
from btc_contract_backtest.runtime.runtime_state_store import JsonRuntimeStateStore


@dataclass
class PilotEvaluationReport:
    recommendation: str
    submit_count: int
    alert_count: int
    incident_count: int
    calibration_sample_count: int
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_post_submit_closed_loop(
    *,
    state_file: str,
    alerts_file: str,
    incidents_file: str = "pilot_incidents.json",
) -> dict[str, Any]:
    state = JsonRuntimeStateStore(state_file, mode="governed_live").get_state()
    alerts_path = Path(alerts_file)
    incident_store = IncidentStore(incidents_file)

    open_orders = [o for o in state.get("orders", []) if o.get("state") not in {"filled", "canceled", "rejected", "expired"}]
    actions = []

    if alerts_path.exists():
        alert_rows = [json.loads(line) for line in alerts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        alert_rows = []

    for order in open_orders:
        if order.get("state") == "new":
            actions.append({"order_id": order.get("order_id"), "action": "monitor_ack_timeout"})
        if order.get("state") == "partial":
            actions.append({"order_id": order.get("order_id"), "action": "monitor_partial_fill_linger"})

    for alert in alert_rows:
        if alert.get("severity") == "critical":
            actions.append({"action": "operator_escalation", "reason": alert.get("alert_type")})

    if any(a.get("action") == "operator_escalation" for a in actions):
        incident_store.append(
            __import__("btc_contract_backtest.live.incident_store", fromlist=["IncidentRecord"]).IncidentRecord(
                incident_id=f"closed-loop-{len(actions)}",
                incident_type="post_submit_monitor",
                severity="critical",
                state="detected",
                timestamp=state.get("updated_at") or "unknown",
                summary="Closed-loop monitor detected escalation condition",
                metadata={"actions": actions},
            )
        )

    state["post_submit_actions"] = actions
    JsonRuntimeStateStore(state_file, mode="governed_live").set_state_fields(post_submit_actions=actions)
    JsonRuntimeStateStore(state_file, mode="governed_live").flush()
    return {"open_order_count": len(open_orders), "actions": actions}


def build_pilot_dossier(
    *,
    dossier_dir: str,
    readiness: PilotReadinessReport,
    preflight: OperatorPreflightReport,
    state_file: str,
    alerts_file: str,
    incidents_file: str = "pilot_incidents.json",
    calibration_samples_path: str = "data/calibration/samples.jsonl",
    funding_snapshots_path: str = "data/calibration/funding_snapshots.jsonl",
    envelope_file: str = "pilot_risk_envelope.json",
) -> dict[str, str]:
    out_dir = Path(dossier_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    state = JsonRuntimeStateStore(state_file, mode="governed_live").get_state()
    alerts = []
    alerts_path = Path(alerts_file)
    if alerts_path.exists():
        alerts = [json.loads(line) for line in alerts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    incidents = IncidentStore(incidents_file).load().get("incidents", [])
    calibration_samples = CalibrationSampleStore(calibration_samples_path).load()
    funding_rows = FundingSnapshotStore(funding_snapshots_path).load()
    envelope = PilotRiskEnvelopeStore(envelope_file).load().to_dict()

    audit = {
        "readiness": readiness.to_dict(),
        "preflight": preflight.to_dict(),
        "risk_envelope": envelope,
        "state": state,
        "alerts": alerts,
        "incidents": incidents,
        "calibration_sample_count": len(calibration_samples),
        "funding_snapshot_count": len(funding_rows),
    }
    audit_path = out_dir / "audit.json"
    audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    md = [
        "# Pilot Dossier",
        "",
        f"- readiness score: {readiness.score}",
        f"- proceed: {preflight.proceed}",
        f"- alerts: {len(alerts)}",
        f"- incidents: {len(incidents)}",
        f"- calibration samples: {len(calibration_samples)}",
        f"- funding snapshots: {len(funding_rows)}",
        "",
        "## Blocking",
    ]
    for item in readiness.blocking or ["none"]:
        md.append(f"- {item}")
    md.append("")
    md.append("## Warnings")
    for item in readiness.warnings or ["none"]:
        md.append(f"- {item}")
    summary_path = out_dir / "summary.md"
    summary_path.write_text("\n".join(md), encoding="utf-8")
    return {"audit": str(audit_path), "summary": str(summary_path)}


def evaluate_pilot_run(
    *,
    state_file: str,
    alerts_file: str,
    incidents_file: str = "pilot_incidents.json",
    calibration_samples_path: str = "data/calibration/samples.jsonl",
) -> PilotEvaluationReport:
    state = JsonRuntimeStateStore(state_file, mode="governed_live").get_state()
    alerts_path = Path(alerts_file)
    alerts = [json.loads(line) for line in alerts_path.read_text(encoding="utf-8").splitlines() if line.strip()] if alerts_path.exists() else []
    incidents = IncidentStore(incidents_file).load().get("incidents", [])
    calibration_samples = CalibrationSampleStore(calibration_samples_path).load()

    submit_count = len([a for a in state.get("operator_actions", []) if a.get("action") == "submit_intended_order"])
    recommendation = "go"
    notes = []
    if incidents:
        recommendation = "hold"
        notes.append("incidents_present")
    if len(alerts) > max(submit_count, 1) * 2:
        recommendation = "rollback"
        notes.append("alert_noise_high")
    if len(calibration_samples) < 10:
        recommendation = "hold"
        notes.append("insufficient_calibration_samples")

    return PilotEvaluationReport(
        recommendation=recommendation,
        submit_count=submit_count,
        alert_count=len(alerts),
        incident_count=len(incidents),
        calibration_sample_count=len(calibration_samples),
        notes=notes,
    )
