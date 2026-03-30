# T3 — Order State Machine Convergence Plan

## Goal
Establish a canonical, restart-safe, idempotent order lifecycle that can be shared by backtest, paper, shadow, and governed live modes.

## T3.1 — Canonical Order Record Model
Define a shared order record with:
- order_id
- client_order_id
- exchange_order_id
- intent_id
- symbol
- side
- order_type
- quantity
- filled_quantity
- avg_fill_price
- reduce_only
- submission_mode
- state
- created_at
- acked_at
- final_at
- last_error
- local_events[]
- remote_events[]
- tags{}

## T3.2 — Transition Core
Implement:
- canonical states: NEW, ACKED, PARTIAL, FILLED, CANCELED, REJECTED, EXPIRED
- idempotent transition application
- illegal transition rejection
- local/remote event append semantics
- terminal state detection

## T3.3 — Local / Remote Event Merge
Merge:
- local submit intent
- local cancel intent
- remote ack
- remote partial / fill / cancel / reject / expire
- reconcile-derived status correction

## T3.4 — Mode Integration
Adopt order state machine across:
- paper
- shadow
- governed live
- backtest runtime

## T3.5 — Stability + Recovery Tests
Add tests for:
- duplicate remote updates
- restart after pending ack
- partial fill replay
- cancel-replace path
- reconcile-based correction

## Execution Sequence
1. Build canonical schema + transition kernel
2. Add EngineStateStore canonical order upsert API
3. Route live/paper order writes through state machine
4. Add remote reconcile/event merge path
5. Add restart/idempotency regression tests
