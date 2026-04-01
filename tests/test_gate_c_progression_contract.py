import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC = REPO_ROOT / "documentations" / "gate-c-supervised-mainnet-pilot-plan.md"
FAULT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "gate_c_fault_injection_matrix.json"
SOAK_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "gate_c_soak_requirements.json"
DRILL_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "gate_c_restart_recovery_drills.json"
PILOT_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "gate_c_supervised_mainnet_pilot.json"
)


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_gate_c_plan_references_versioned_acceptance_fixtures():
    text = DOC.read_text(encoding="utf-8")
    assert "tests/fixtures/gate_c_fault_injection_matrix.json" in text
    assert "tests/fixtures/gate_c_soak_requirements.json" in text
    assert "tests/fixtures/gate_c_restart_recovery_drills.json" in text
    assert "tests/fixtures/gate_c_supervised_mainnet_pilot.json" in text
    assert "partial fill" in text.lower()
    assert "supervised mainnet pilot" in text.lower()


def test_gate_c_fault_matrix_covers_races_and_partial_fill_continuity():
    scenarios = _load(FAULT_FIXTURE)
    names = {row["name"] for row in scenarios if row.get("required")}
    assert "partial_fill_then_restart_then_completion" in names
    assert "fill_while_cancel_replace_in_flight" in names
    assert "ambiguous_submit_resolves_remote_open_after_restart" in names

    partial = next(
        row
        for row in scenarios
        if row["name"] == "partial_fill_then_restart_then_completion"
    )
    assert "cumulative_fill_quantity_preserved" in partial["pass_conditions"]
    assert "average_entry_basis_converges" in partial["pass_conditions"]


def test_gate_c_soak_requirements_include_supervised_campaign_and_human_review():
    payload = _load(SOAK_FIXTURE)
    campaigns = {row["name"]: row for row in payload["campaigns"]}
    assert campaigns["ci_deterministic_short_soak"]["minimum_event_count"] >= 250
    assert campaigns["supervised_operator_soak"]["minimum_runtime_minutes"] >= 60
    assert campaigns["supervised_operator_soak"]["notes_required"] is True
    assert payload["human_review"]["required"] is True
    assert "pilot_dossier" in payload["human_review"]["artifacts"]


def test_gate_c_restart_drills_include_blocking_and_reviewed_resume_cases():
    drills = _load(DRILL_FIXTURE)
    expected = {row["name"]: row for row in drills if row.get("required")}
    assert expected["restart_after_critical_divergence"]["expected_resume"] == "blocked"
    assert (
        expected["restart_during_partial_fill"]["expected_resume"]
        == "allowed_after_review"
    )
    assert (
        "operator_decision_record"
        in expected["restart_with_remote_only_open_order"]["required_artifacts"]
    )


def test_gate_c_pilot_fixture_requires_approval_mode_and_safe_exit_criteria():
    payload = _load(PILOT_FIXTURE)
    assert payload["preflight"]["governance_mode"] == "approval_required"
    assert payload["preflight"]["single_symbol_only"] is True
    assert payload["preflight"]["tiny_size_only"] is True
    exit_criteria = set(payload["exit_criteria"])
    assert "all_live_intents_operator_approved" in exit_criteria
    assert "partial_fill_quantity_continuity_preserved_across_restart" in exit_criteria
    assert "post_run_recommendation_not_rollback" in exit_criteria
