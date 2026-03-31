#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class GateStep:
    name: str
    command: tuple[str, ...]
    scope: str
    required: bool = True


HARD_GATE_STEPS: tuple[GateStep, ...] = (
    GateStep(
        name="pytest", command=(sys.executable, "-m", "pytest", "-q"), scope="repo"
    ),
    GateStep(
        name="flake8",
        command=(sys.executable, "-m", "flake8", "src"),
        scope="production-code",
    ),
    GateStep(
        name="mypy",
        command=(sys.executable, "-m", "mypy", "src"),
        scope="production-code",
    ),
    GateStep(name="build", command=(sys.executable, "-m", "build"), scope="packaging"),
)


def git_status_lines() -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--short"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in proc.stdout.splitlines() if line.strip()]


def working_tree_is_clean() -> bool:
    return not git_status_lines()


def build_gate_report(*, check_clean: bool) -> dict:
    report = {
        "repo_root": str(REPO_ROOT),
        "python": sys.version.split()[0],
        "working_tree_clean": working_tree_is_clean(),
        "required_steps": [
            {
                **asdict(step),
                "command": list(step.command),
            }
            for step in HARD_GATE_STEPS
        ],
    }
    if check_clean:
        report["ready"] = report["working_tree_clean"]
    else:
        report["ready"] = True
    return report


def run_step(step: GateStep) -> None:
    print(f"[release-gate] running {step.name}: {' '.join(step.command)}", flush=True)
    subprocess.run(step.command, cwd=REPO_ROOT, check=True)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run or inspect the repo hard release gate."
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print the gate definition without running commands.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON for --report.")
    parser.add_argument(
        "--run", action="store_true", help="Run the hard gate commands."
    )
    parser.add_argument(
        "--check-clean",
        action="store_true",
        help="Require a clean working tree before reporting ready or running the gate.",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Permit running the gate even if the working tree is dirty.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if not args.report and not args.run:
        args.report = True

    report = build_gate_report(check_clean=args.check_clean)
    if args.report:
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print("Release hard gate")
            print(f"repo: {report['repo_root']}")
            print(f"python: {report['python']}")
            print(f"working tree clean: {report['working_tree_clean']}")
            for step in report["required_steps"]:
                print(
                    f"- {step['name']}: {' '.join(step['command'])} [{step['scope']}]"
                )

    if not args.run:
        return 0 if report["ready"] else 1

    if args.check_clean and not report["working_tree_clean"] and not args.allow_dirty:
        print(
            "[release-gate] working tree is dirty; commit/stash changes or pass --allow-dirty",
            file=sys.stderr,
        )
        return 1

    for step in HARD_GATE_STEPS:
        run_step(step)
    print("[release-gate] all hard gates passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
