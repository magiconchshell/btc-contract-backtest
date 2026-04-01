# Gate C Supervised Mainnet Pilot Plan

Date: 2026-03-30
Project: `github-btc-backtest`
Depends on: race-hardening landing, partial-fill merge landing, Gate B replay/event-state coverage remaining green

---

## Current Status

Gate C is the first supervised mainnet pilot gate, but it is still **blocked**
until Gate B stays green and the supervised evidence package is reviewed.

In practice, that means the operator needs three things before calling a Gate C
run ready:

- Gate B replay, restart, and event-state checks still passing
- reviewed pilot fixtures / drill records for the required scenarios
- a tiny-size, single-symbol, approval-required supervised runbook

---

## Purpose

Gate C should be the **first supervised mainnet pilot gate**, not a paper-only quality gate.

By the time this gate is evaluated, the engine should already have:

- deterministic restart convergence coverage,
- residual cancel/fill/replace risk detection,
- partial-fill state merge behavior wired through restart/recovery paths,
- and race-hardening for out-of-order remote lifecycle events.

Gate C is where the repo proves that those primitives survive **multi-step operator drills** and a **small supervised mainnet runbook**, not just isolated unit tests.

---

## What Gate C Should Require Now

A Gate C candidate should require all of the following.

### 1. Gate B remains green
- `python scripts/release_gate.py --run --check-clean`
- Gate B replay corpus still passes
- Gate B deterministic fault/soak coverage still passes

### 2. Versioned Gate C evidence fixtures exist and are reviewed
The following versioned fixtures should exist and be treated as acceptance inputs:
- `tests/fixtures/gate_c_fault_injection_matrix.json`
- `tests/fixtures/gate_c_soak_requirements.json`
- `tests/fixtures/gate_c_restart_recovery_drills.json`
- `tests/fixtures/gate_c_supervised_mainnet_pilot.json`

These fixtures should define the required scenarios, thresholds, and pass/fail semantics so the gate is reproducible.

### 3. Fault injection includes race + partial-fill cases
Gate C fault coverage should explicitly require scenarios for:
- websocket gap followed by catch-up replay
- duplicate or out-of-order remote order updates
- partial fill before restart and completion after restart
- fill arriving while cancel/replace is still in flight
- stale local open order with no remote peer after restart
- ambiguous submit that resolves to remote open order after recovery

A Gate C candidate should not pass if any of the above lacks a regression path.

### 4. Soak evidence goes beyond CI-sized deterministic checks
Gate C should require at least one supervised soak campaign in a non-production environment with evidence for:
- uninterrupted runtime window long enough to exercise reconnect/recovery paths
- zero unresolved critical incidents at end of run
- zero duplicate submit actions for the same intent
- zero unreconciled remote-only exposure at end of run
- bounded warning volume with human review notes

CI should keep deterministic short-run soak tests, but Gate C should additionally require operator-reviewed soak evidence captured outside the narrow unit-test loop.

### 5. Restart and recovery drills are run as operator playbooks
A Gate C pass should require explicit drill records for at least:
- clean restart with no open exposure drift
- restart during partial fill
- restart after ambiguous submit acknowledgement timeout
- restart with poll fallback because websocket boundary is unavailable
- restart with remote-only open order requiring adopt/cancel decision
- restart after critical divergence proving the session halts instead of resuming silently

Each drill should record:
- setup conditions
- expected blocking vs warning semantics
- operator decision taken
- reconcile/recovery outcome
- whether live enablement remained blocked or was allowed to resume

### 6. Supervised mainnet pilot preflight must be explicit
Before any Gate C pilot run, operator preflight should verify:
- governance mode is `approval_required`
- emergency stop is off and maintenance is off intentionally
- readiness score is at or above the configured minimum
- risk envelope is tiny-size and single-symbol
- post-submit monitoring path is enabled
- reconcile, submit-ledger, and recovery report paths are known to the operator
- restart drill evidence has been reviewed recently

### 7. Supervised mainnet pilot exit criteria must be explicit
A Gate C supervised pilot should only be considered passed when all of the following are true:
- every live intent was operator-approved
- no duplicate submit was observed
- no unresolved ambiguous intent remained at session end
- no critical reconcile mismatch remained at session end
- any partial-fill episode preserved correct cumulative quantity across restart boundaries
- incident log is empty or only contains reviewed non-critical noise
- pilot dossier and post-run evaluation recommend `go` or at least do not force `rollback`

---

## Practical Operator Runbook

Use this sequence when preparing a supervised Gate C pilot:

1. Confirm Gate B is still green on the current commit.
2. Review the four versioned fixtures listed above and make sure they match the run you are about to perform.
3. Run the governed live preflight and verify:
   - `approval_required` mode
   - emergency stop off
   - maintenance off
   - tiny-size, single-symbol limits
4. Start in shadow or dry-run mode first if anything about the exchange state is uncertain.
5. Run the supervised mainnet pilot with one operator watching reconcile, recovery, and incident output in real time.
6. Stop immediately on any critical reconcile mismatch, duplicate submit, or unresolved ambiguous intent.
7. Save the pilot dossier and post-run notes before any resume or retry.

---

## Suggested Gate C CI Focus

These tests should be treated as Gate C-critical once the race-hardening and partial-fill merge work lands:

- `tests/test_fault_injection_soak.py`
- `tests/test_restart_convergence_v2.py`
- `tests/test_restart_reconcile_stability.py`
- `tests/test_recovery_convergence.py`
- `tests/test_pilot_controls.py`
- `tests/test_pilot_reporting.py`
- `tests/test_gate_c_progression_contract.py`

---

## What Gate C Should Still Not Claim

Passing Gate C should **not** be treated as permission for unattended real-capital trading.

Even after a Gate C pass, the system should still be considered:
- supervised only,
- tiny-size only,
- restart/recovery sensitive,
- and dependent on explicit operator review of reconcile, recovery, and incident outputs.

---

## Current Assessment

The repo looks close to a credible Gate C planning state, but not yet to a true Gate C pass.

### Strong now
- deterministic fault-injection primitives already exist
- restart convergence and recovery reporting already exist
- operator preflight/readiness and pilot dossier plumbing already exist
- versioned Gate B replay fixture precedent already exists

### Still required before Gate C can be honestly claimed
- merged race-hardening coverage for out-of-order cancel/fill/replace paths
- merged partial-fill continuity assertions across restart/recovery boundaries
- operator-reviewed soak evidence, not just CI-sized synthetic runs
- explicit supervised mainnet pilot evidence package with pass/fail thresholds

In short: **Gate C should become the first evidence-backed supervised mainnet gate, not merely another unit-test milestone.**
