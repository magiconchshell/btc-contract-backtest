#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from btc_contract_backtest.live.governance import (
    GovernanceState,
    OperatorApprovalQueue,
    TradingMode,
)


def main():
    if len(sys.argv) < 3:
        raise SystemExit(
            "usage: governance_cli.py <state-file|approvals-file> <command> [args]"
        )

    target = sys.argv[1]
    command = sys.argv[2]

    if command in {"set-mode", "emergency-stop", "maintenance"}:
        state = GovernanceState(target)
        if command == "set-mode":
            mode = TradingMode(sys.argv[3])
            state.set_mode(mode)
        elif command == "emergency-stop":
            state.set_emergency_stop(sys.argv[3].lower() == "true")
        elif command == "maintenance":
            state.set_maintenance(sys.argv[3].lower() == "true")
        print(json.dumps(state.load(), indent=2, ensure_ascii=False))
        return

    approvals = OperatorApprovalQueue(target)
    if command == "approve":
        approvals.approve(sys.argv[3])
    elif command == "reject":
        approvals.reject(sys.argv[3])
    elif command == "show":
        pass
    else:
        raise SystemExit(f"unknown command: {command}")

    print(json.dumps(approvals.load(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
