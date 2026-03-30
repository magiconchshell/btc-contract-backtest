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
1. Run shadow mode first and inspect audit / review outputs
2. Run `live_readiness_check.py`
3. Set governance mode deliberately via `governance_cli.py`
4. Keep emergency stop available at all times
5. Start governed live session with tiny size assumptions
6. Watch audit, alerts, and reconcile outputs continuously
7. If any reconcile mismatch, stale market issue, or unexpected lifecycle behavior appears, stop immediately

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
