from pathlib import Path

from scripts.generate_gate_c_readiness_bundle import build_bundle


REPO_ROOT = Path(__file__).resolve().parents[1]
FAULT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "gate_c_fault_injection_matrix.json"
SOAK_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "gate_c_soak_requirements.json"
DRILL_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "gate_c_restart_recovery_drills.json"
PILOT_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "gate_c_supervised_testnet_pilot.json"
)


def test_gate_c_readiness_bundle_includes_required_evidence(tmp_path):
    result = build_bundle(
        fault_matrix=FAULT_FIXTURE,
        soak_requirements=SOAK_FIXTURE,
        restart_drills=DRILL_FIXTURE,
        pilot_fixture=PILOT_FIXTURE,
        out_dir=tmp_path / "bundle",
    )

    payload = result["payload"]
    assert payload["fault_injection_scenarios"] == 5
    assert payload["restart_drills"] == 6
    assert payload["soak_campaigns"] == 2
    assert payload["pilot_preflight"]["governance_mode"] == "approval_required"

    json_path = Path(result["json"])
    md_path = Path(result["markdown"])
    assert json_path.exists()
    assert md_path.exists()
    md = md_path.read_text(encoding="utf-8")
    assert "partial-fill continuity" in md.lower()
    assert "single-symbol tiny-size approval-required runs" in md.lower()


def test_gate_c_readiness_bundle_references_operator_artifacts(tmp_path):
    result = build_bundle(
        fault_matrix=FAULT_FIXTURE,
        soak_requirements=SOAK_FIXTURE,
        restart_drills=DRILL_FIXTURE,
        pilot_fixture=PILOT_FIXTURE,
        out_dir=tmp_path / "bundle",
    )

    payload = result["payload"]
    assert payload["inputs"]["fault_injection"].endswith(
        "gate_c_fault_injection_matrix.json"
    )
    assert payload["inputs"]["soak_requirements"].endswith(
        "gate_c_soak_requirements.json"
    )
    assert payload["inputs"]["restart_drills"].endswith(
        "gate_c_restart_recovery_drills.json"
    )
    assert payload["inputs"]["pilot_fixture"].endswith(
        "gate_c_supervised_testnet_pilot.json"
    )
