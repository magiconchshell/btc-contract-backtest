import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "release_gate.py"


def test_release_gate_report_lists_expected_hard_steps():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--report", "--json"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout)
    assert [step["name"] for step in payload["required_steps"]] == [
        "pytest",
        "ruff",
        "mypy",
        "build",
    ]
    assert payload["required_steps"][0]["command"][-2:] == ["pytest", "-q"]
    assert payload["required_steps"][1]["command"][-2:] == ["check", "src"]
    assert payload["required_steps"][2]["command"][-2:] == ["mypy", "src"]
    assert payload["required_steps"][3]["command"][-1] == "build"


def test_release_gate_check_clean_report_reflects_working_tree_state():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--report", "--json", "--check-clean"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout)
    assert isinstance(payload["working_tree_clean"], bool)
    assert payload["ready"] is payload["working_tree_clean"]
    assert proc.returncode == (0 if payload["working_tree_clean"] else 1)
