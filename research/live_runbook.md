# Controlled Live Experimentation Runbook

## Goal
Use the governed live framework only for very small-size, guarded experimentation.

## Preconditions
- Governance mode is set intentionally (`approval_required` or `guarded_live`)
- Emergency stop is OFF
- Maintenance mode is OFF
- Shadow / audit review has been checked recently
- Approval queue path is known
- Alerts sink path is known

## Recommended sequence
1. Run shadow mode first and inspect audit / review outputs.
2. Confirm the active repo gate is still green (`python scripts/release_gate.py --run --check-clean`).
3. Run `live_readiness_check.py` and review the report before changing anything.
4. Set governance mode deliberately via `governance_cli.py`.
5. Keep emergency stop available at all times.
6. Start governed live session with tiny-size, single-symbol assumptions.
7. Watch audit, alerts, reconcile, and recovery outputs continuously.
8. If any reconcile mismatch, duplicate submit, stale market issue, or unexpected lifecycle behavior appears, stop immediately.

## Supervised testnet progression notes

- Prefer one controlled run over several casual retries.
- Record the exact commit hash, exchange/symbol, mode, and operator present.
- If a restart is part of the drill, capture the before/after reconcile report and the recovery report together.
- Do not promote the session from shadow to live in the same run unless the preflight and operator notes explicitly allow it.

## Operator commands
- set mode
- enable / disable maintenance
- enable / disable emergency stop
- approve / reject queued requests

## Immediate stop conditions
- reconcile mismatches recur
- stale / unsafe market blocks recur unexpectedly
- repeated submit failures
- stuck or partial order behavior outside policy expectations
- operator uncertainty
