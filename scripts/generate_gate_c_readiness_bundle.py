#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_markdown(out_path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Gate C Readiness Bundle",
        "",
        f"- fault injection scenarios: {payload['fault_injection_scenarios']}",
        f"- restart drills: {payload['restart_drills']}",
        f"- soak campaigns: {payload['soak_campaigns']}",
        f"- supervised pilot preflight: {payload['pilot_preflight']}",
        f"- supervised pilot exit criteria: {payload['pilot_exit_criteria']}",
        "",
        "## Evidence files",
    ]
    for key, value in payload["inputs"].items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    lines.append("## Operator notes")
    for note in payload["operator_notes"]:
        lines.append(f"- {note}")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def build_bundle(
    *,
    fault_matrix: Path,
    soak_requirements: Path,
    restart_drills: Path,
    pilot_fixture: Path,
    out_dir: Path,
) -> dict[str, Any]:
    fault_rows = _load_json(fault_matrix)
    soak_rows = _load_json(soak_requirements)
    drill_rows = _load_json(restart_drills)
    pilot = _load_json(pilot_fixture)

    required_faults = [row for row in fault_rows if row.get("required")]
    required_drills = [row for row in drill_rows if row.get("required")]
    campaigns = soak_rows.get("campaigns", [])

    payload = {
        "fault_injection_scenarios": len(required_faults),
        "restart_drills": len(required_drills),
        "soak_campaigns": len(campaigns),
        "pilot_preflight": pilot.get("preflight", {}),
        "pilot_exit_criteria": pilot.get("exit_criteria", []),
        "inputs": {
            "fault_injection": str(fault_matrix),
            "soak_requirements": str(soak_requirements),
            "restart_drills": str(restart_drills),
            "pilot_fixture": str(pilot_fixture),
        },
        "operator_notes": [
            "Review partial-fill continuity across restart before widening automation.",
            "Keep supervised pilot limited to single-symbol tiny-size approval-required runs.",
            "Attach reconcile, recovery, incident, and pilot dossier artifacts to every soak.",
        ],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "gate_c_readiness_bundle.json"
    md_path = out_dir / "gate_c_readiness_bundle.md"
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _write_markdown(md_path, payload)
    return {"json": str(json_path), "markdown": str(md_path), "payload": payload}


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if len(args) != 5:
        raise SystemExit(
            "usage: generate_gate_c_readiness_bundle.py <fault_matrix> <soak_requirements> <restart_drills> <pilot_fixture> <out_dir>"
        )
    result = build_bundle(
        fault_matrix=Path(args[0]),
        soak_requirements=Path(args[1]),
        restart_drills=Path(args[2]),
        pilot_fixture=Path(args[3]),
        out_dir=Path(args[4]),
    )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "payload"},
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
