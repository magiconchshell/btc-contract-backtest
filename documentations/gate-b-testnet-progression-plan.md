# Gate B Testnet Progression Plan

Date: 2026-03-30
Project: `github-btc-backtest`

---

## Current Status

Gate B is the current progression gate for this repo. It is intended to keep
restart-convergence, event-continuity, and cancel/replace residual-risk checks
green before any broader testnet movement.

Gate C is not yet a live-go-live gate. It remains blocked on the supervised
pilot evidence package described in the Gate C plan: race-hardening coverage,
partial-fill continuity across restart, and reviewed soak/drill artifacts.

Operators should treat this as a **progression gate**, not a profitability gate.

---

## Purpose

Gate B should be the **last controlled checkpoint before broader testnet progression** after the restart-convergence and event-state work lands.

This gate is not about profitability. It is about proving that the engine:

- replays the right execution corpus after restart,
- classifies convergence failures consistently,
- detects event-stream continuity problems,
- and surfaces cancel/fill/replace residual-risk cases before they become silent exposure.

---

## What Gate B Should Require Now

A Gate B pass should require all of the following.

### 1. Hard repo gate still passes
- `python scripts/release_gate.py --run --check-clean`

### 2. Restart convergence corpus passes
A maintained replay corpus must prove at least these classes:
- clean restart with matching position and no unresolved intents
- ambiguous submit with no remote order visible -> `submit_ack_ambiguous`
- unresolved intent without `client_order_id` -> `missing_client_order_id`
- remote open order discovered by `client_order_id` -> `remote_open_order_present`
- position entry-basis-only drift -> warning, not critical halt
- side/quantity divergence -> critical halt
- poll-fallback startup when websocket boundary is unavailable -> warning action only

### 3. Replay hook expectations are explicit
For each corpus scenario, the startup convergence report should preserve:
- replayable event count
- replay order event count
- replay fill event count
- last order update sequence
- last fill sequence

Non-replayable events must not inflate replay-derived counts.

### 4. Event continuity checks are green on deterministic soak coverage
Fault/soak coverage must validate:
- monotonic external sequence acceptance
- gap detection
- duplicate/reorder detection
- symbol/source partition isolation
- non-numeric external sequence handling
- restart replay preserving the last boundary watermark

### 5. Cancel/replace residual-risk checks are covered
At minimum, CI must exercise:
- both old and replacement order open -> `double_open_risk`
- old order fills while replacement is live -> `residual_exposure_risk`
- replacement pending without overlap -> non-fatal `replace_pending`

### 6. Startup convergence failure semantics are stable
A Gate B candidate should fail progression if startup convergence emits any critical action for:
- position side mismatch
- position quantity mismatch
- unresolved ambiguous submit intents
- remote-only exchange orders

Warnings are allowed for:
- entry basis drift only
- local-only orders requiring expiry/cleanup
- poll fallback required during catch-up

---

## Suggested Gate B CI Focus

These tests should be treated as Gate B-critical:

- `tests/test_restart_convergence_v2.py`
- `tests/test_fault_injection_soak.py`
- `tests/test_recovery_orchestrator.py`
- `tests/test_live_failure_harness.py`
- `tests/test_event_stream.py`

---

## Exit Criteria To Move Beyond Gate B

Only progress beyond Gate B when all of the following are true:

- replay corpus expectations are versioned and passing
- convergence reports distinguish warnings from blockers correctly
- restart replay preserves fill/order hooks needed for post-crash reconciliation
- event-stream continuity checks prove the engine will force reconnect/catch-up on gaps
- residual cancel/replace risk cases are detectable in deterministic tests
- no known critical startup divergence path lacks a regression test

---

## Current Assessment

The repo is close to a sensible Gate B shape, but not fully there yet.

### Strong now
- restart convergence report structure exists
- replay hooks and watermark reporting exist
- fault-injection helpers already cover gaps and residual exposure cases
- recovery orchestrator already connects submit-ledger recovery into startup convergence

### Still required for confidence
- a maintained Gate B replay corpus, not just ad-hoc unit scenarios
- sharper distinction between warning-only drift and must-halt divergence in release planning
- broader restart/event-state coverage once the next landing work is merged

In short: **the primitives are mostly present; Gate B now needs explicit expectations and mandatory regression coverage.**
