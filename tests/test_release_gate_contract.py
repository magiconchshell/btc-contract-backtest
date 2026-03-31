from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "python-ci.yml"
README = REPO_ROOT / "README.md"
CHECKLIST = REPO_ROOT / "documentations" / "release-and-go-live-checklists.md"

REPORT_CMD = "python scripts/release_gate.py --report --json --check-clean"
RUN_CMD = "python scripts/release_gate.py --run --check-clean"
CI_RUN_CMD = "python scripts/release_gate.py --run --check-clean --allow-dirty"


def test_ci_uses_unified_release_gate_script():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert REPORT_CMD in workflow
    assert CI_RUN_CMD in workflow


def test_docs_reference_same_release_gate_entrypoint():
    readme = README.read_text(encoding="utf-8")
    checklist = CHECKLIST.read_text(encoding="utf-8")
    assert "python scripts/release_gate.py --report --json" in readme
    assert RUN_CMD in readme
    assert REPORT_CMD in checklist
    assert RUN_CMD in checklist
