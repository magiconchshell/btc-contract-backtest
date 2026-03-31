# System Correctness and Live Readiness Report

Date: 2026-03-30
Project: `github-btc-backtest`
Scope: system correctness, system completeness, live trading readiness
Out of scope: strategy alpha, profitability, parameter quality

---

## Executive Summary

This review evaluates the current codebase strictly as a **trading/backtesting engine**, not as a strategy research project.

### Bottom line

- **Backtest engine:** usable
- **Paper trading engine:** usable
- **Shadow / governed pilot engine:** usable for supervised experimentation
- **Formal live trading engine:** **not yet ready for production deployment**

The reason is not strategy quality. The reason is that several **production-critical correctness loops are still incomplete**:

1. Fine-grained exchange reconciliation is not complete
2. Submission idempotency is not closed end-to-end
3. Live order lifecycle orchestration is only partially implemented
4. Restart recovery is stateful, but not yet exchange-grade
5. Exchange hard constraints are not fully enforced pre-submit
6. The live data plane is still too polling-oriented for production correctness

---

## Review Method

This report is based on the **current code**, not old architecture notes.

Primary areas reviewed:

- `src/btc_contract_backtest/engine/*`
- `src/btc_contract_backtest/runtime/*`
- `src/btc_contract_backtest/live/*`
- relevant tests under `tests/*`

The evaluation criterion is:

> Can this engine, as written, be trusted to run real-time trading correctly and completely under live conditions, including failure, partial fill, restart, and reconciliation scenarios?

---

## What Is Already Strong

### 1. Shared execution core exists

The project has a real shared execution layer centered around:

- `engine/simulator_core.py`
- `engine/execution_models.py`
- `runtime/trading_runtime.py`

This is a major strength. Backtest, paper, and live-oriented flows are not completely separate ad-hoc systems.

### 2. Runtime boundary is reasonably well structured

`runtime/trading_runtime.py` gives the system a stable step lifecycle:

- ingest market data
- generate/evaluate signal
- check risk
- build intended order
- persist runtime payload
- dispatch per-mode behavior

This is good engine design and supports observability and persistence.

### 3. Canonical order state work is real

The project includes:

- `runtime/order_state_machine.py`
- `runtime/order_state_bridge.py`

This provides:

- canonical order states
- legal transition rules
- event deduplication
- terminal state handling

That is a meaningful foundation for execution correctness.

### 4. Governance / control-plane primitives exist

The codebase already has:

- governance modes
- approval queue
- emergency stop
- maintenance mode
- audit logging
- alert sink
- watchdog
- incident store

These are not cosmetic features. They are necessary components of any serious live engine.

### 5. Persistent runtime state exists

The project includes a normalized state store:

- `runtime/runtime_state_store.py`
- schema normalization helpers
- per-mode state persistence hooks

This is important because live correctness depends heavily on restart behavior and state continuity.

---

## Why It Is Still Not Ready For Formal Live Trading

## 1. Reconciliation is too coarse

Current reconciliation in `live/exchange_adapter.py` mainly compares:

- local position side vs remote position side
- local open order count vs remote open order count

That is not enough for production correctness.

A live engine needs reconciliation at least at the level of:

- order identity
- `client_order_id`
- `exchange_order_id`
- side
- type
- quantity
- filled quantity
- average fill price
- reduce-only semantics
- per-order status
- position quantity and entry basis

With the current implementation, the system can miss serious mismatches while still appearing “reconciled”.

### Impact

This is a production blocker.

---

## 2. Submission idempotency is not closed end-to-end

`live/guarded_live.py` and `live/live_session.py` provide controlled submission flow, but the code does not yet establish a full production-grade idempotent submit model.

Missing or incomplete pieces include:

- durable submit intent ledger
- explicit pending-submit state machine
- timeout/unknown-submit recovery path
- restart-safe de-duplication of exchange-side accepts
- end-to-end proof against accidental duplicate opening after ambiguous submit outcomes

This matters because real exchanges frequently create ambiguous states:

- request timeout but exchange accepted order
- local crash after send but before local persistence completes
- retry after partial network failure

### Impact

Without a closed idempotency loop, duplicate live execution remains a real risk.

---

## 3. Order lifecycle orchestration is only partial

The codebase has order lifecycle components, but they do not yet form a fully closed live orchestration layer.

Present:

- canonical order record model
- transition rules
- remote status bridge
- lifecycle monitor
- post-submit policy helper

Still incomplete as a production system:

- full ack/working/partial/filled/canceled/rejected/expired orchestration loop
- cancel-pending / replace-pending handling
- out-of-order remote event handling
- full replay merge after restart
- robust partial-fill residual management
- authoritative exchange-event-driven lifecycle progression

### Impact

The engine can represent order state, but it cannot yet guarantee correct orchestration in all practical live scenarios.

---

## 4. Restart recovery is not yet exchange-grade

The project does have restart-aware persistence and recovery helpers, which is good.

However, a production live system must be able to restart and safely determine:

- which local orders are still open remotely
- whether any fills occurred while offline
- whether a submit outcome was unknown but actually accepted
- whether any local order is now orphaned
- whether position quantity and average entry still match exchange truth

Current recovery is primarily local-state restoration plus partial normalization. It is not yet a full remote-truth restart convergence engine.

### Impact

This is another production blocker.

---

## 5. Exchange adapter is still too thin

`live/exchange_adapter.py` is a useful integration layer, but it is still a thin CCXT wrapper from a production correctness perspective.

Still missing or incomplete:

- exchange-specific precision enforcement
- min quantity / min notional validation
- leverage and margin mode sanity checks
- reduce-only legality checks
- normalized rejection/error taxonomy
- websocket/user-stream integration
- stronger remote event normalization

### Impact

The adapter can place orders, but it is not yet strong enough to serve as a production execution boundary.

---

## 6. Live data plane is not yet strong enough for production correctness

Current live flows rely mainly on polling-based calls such as:

- `fetch_ohlcv`
- `fetch_ticker`
- `fetch_positions`
- `fetch_open_orders`
- `fetch_order`

This is acceptable for:

- backtest
- paper
- shadow
- guarded experimentation

It is not sufficient for high-confidence production live correctness because it lacks:

- user stream / execution stream truth source
- event sequencing guarantees
- feed lag/heartbeat supervision beyond basic watchdog behavior
- event-driven order/fill state progression

### Impact

Polling-only execution awareness is too weak for formal deployment.

---

## 7. Pre-submit hard constraints are incomplete

The governance layer does block several unsafe conditions, which is good.

However, a production live system also needs consistent enforcement of exchange and account constraints before submission, including:

- tick-size rounding
- lot-size rounding
- minimum notional checks
- available margin checks
- leverage/mode consistency checks
- reduce-only validity checks
- position-mode consistency checks

These are not yet implemented as a complete live hard gate set.

### Impact

A real exchange may reject or reinterpret orders in ways the engine is not yet fully defending against.

---

## Readiness By Mode

## Backtest

### Assessment
Usable.

### Reason
The shared simulation core already covers core execution semantics:

- fills
- slippage approximation
- funding
- stale data blocking
- mark/bid/ask consistency checks
- position state transitions

This is sufficient for a serious backtesting engine, even though it is not a perfect exchange replay simulator.

---

## Paper Trading

### Assessment
Usable.

### Reason
`live/paper_trading.py` already integrates:

- shared runtime
- shared execution core
- persistence
- startup reconciliation hooks
- order state recording
- calibration sample capture

This is strong enough for paper mode.

---

## Shadow Trading

### Assessment
Usable.

### Reason
`live/shadow_session.py` includes:

- live market fetch
- reconcile callout
- audit log
- state persistence
- restart continuity

This is sufficient for shadow validation work.

---

## Guarded Pilot / Tiny Supervised Live Experimentation

### Assessment
Usable with caution.

### Reason
The system already supports:

- governance modes
- operator approvals
- audit and alert artifacts
- pilot reporting helpers
- post-submit observation helpers

This is enough for supervised, tiny-size, human-watched experimentation.

### Important caveat
This should still be treated as **pilot execution**, not production deployment.

---

## Formal Production Live Trading

### Assessment
Not ready.

### Core blockers

1. coarse reconciliation
2. incomplete idempotent submission guarantees
3. incomplete live order lifecycle orchestration
4. incomplete restart-safe remote convergence
5. incomplete exchange hard constraint enforcement
6. insufficiently event-driven live data/execution plane

---

## Required Work Before Production Go-Live

## Priority 1 — Detailed reconciliation engine

Implement a richer reconciliation model covering:

- per-order comparison
- per-position comparison
- fill/state mismatch classification
- orphan local/remote order detection
- explicit reconcile severity levels

This should replace the current side/count-only reconciliation model.

---

## Priority 2 — Durable idempotent submission ledger

Implement:

- persistent submit intent journal
- submit lifecycle states
- timeout/unknown-result recovery
- restart-safe request replay resolution
- duplicate prevention guarantees

---

## Priority 3 — Full order lifecycle orchestration

Expand the current order-state foundation into a full live engine loop with:

- pending ack states
- partial fill continuation logic
- cancel-pending/replace-pending paths
- remote event precedence rules
- out-of-order event handling
- replay merge rules

---

## Priority 4 — Exchange-grade recovery

Implement startup convergence against exchange truth, including:

- remote open order snapshot import
- remote fill replay
- position basis convergence
- orphan resolution
- submit-in-flight resolution

---

## Priority 5 — Exchange hard constraints and account checks

Before submission, enforce:

- lot size
- tick size
- min quantity
- min notional
- available margin
- leverage/mode consistency
- reduce-only semantics

---

## Priority 6 — Event-driven live data plane

Move toward:

- user stream integration
- event-driven execution state
- stronger data heartbeat/lag monitoring
- event recording for later replay and calibration

---

## Final Assessment

This codebase already has a strong and serious foundation as a:

- contract backtest engine
- paper trading engine
- shadow execution engine
- governed pilot experimentation engine

However, it is **not yet complete enough in correctness guarantees** for formal production live trading.

The gap is no longer “basic architecture”.
The gap is specifically the last set of production-grade correctness closures:

- reconciliation
- idempotency
- lifecycle orchestration
- recovery
- exchange constraints
- live execution data truth

Once those are closed, the system can be reevaluated for formal live readiness.
