# Architecture

## Goal

This project is a **futures / perpetual contract trading toolkit** for BTCUSDT-style leveraged trading.
It is explicitly designed for:
- long / short trading
- leverage-aware simulation
- fees + funding
- liquidation-aware backtesting
- paper trading integration

## Package layout

```text
src/btc_contract_backtest/
├── cli/        # command-line entrypoints
├── config/     # config dataclasses for contract/account/risk
├── engine/     # futures backtest engine
├── live/       # paper trading / live loop integration
├── reporting/  # metrics and summaries
└── strategies/ # signal generation logic
```

## Core domain model

### ContractSpec
Defines the market being tested:
- symbol
- market type
- quote currency
- leverage

### AccountConfig
Defines account-level assumptions:
- initial capital
- taker / maker fee
- annualized funding approximation

### RiskConfig
Defines risk model assumptions:
- max position notional
- stop loss / take profit
- maintenance margin ratio

## Futures engine flow

1. Fetch historical futures candles from Binance
2. Generate contract signals (`1 long`, `-1 short`, `0 flat`)
3. Simulate position lifecycle
   - open long
   - close long
   - open short
   - close short
   - reverse
4. Apply leverage-aware PnL
5. Apply fees + funding
6. Check liquidation against maintenance margin
7. Produce equity curve + trades + metrics

## Paper trading flow

1. Pull recent market data
2. Generate latest strategy signal
3. Compare against current paper position
4. Trigger one of:
   - open
   - close
   - reverse
   - liquidation
   - hold
5. Persist state to `paper_state.json`
6. Print / report session summary

## Why this is not spot-only

This system intentionally models futures semantics:
- short exposure is first-class
- leverage is explicit
- liquidation is modeled
- funding is included
- margin usage matters

That is materially different from a spot portfolio tracker.

## Current execution architecture

The engine is now split into a shared simulation/execution core:
- `engine/execution_models.py` → order / fill / market snapshot / reconcile models
- `engine/simulator_core.py` → shared position, fill, risk, sizing, stale-data checks
- `engine/futures_engine.py` → backtest runner using the shared core
- `live/paper_trading.py` → paper/live-sim runner using the same core
- `live/exchange_adapter.py` → exchange order / cancel / fetch / reconcile adapter skeleton
- `live/session_recovery.py` → state restore / order restore / duplicate client id detection
- `live/watchdog.py` → heartbeat timeout and failure halt logic

## Current limitations

Still simplified compared with exchange-grade execution:
- orderbook depth remains approximated rather than replayed tick-by-tick
- queue priority is still coarse / probabilistic
- funding mostly remains modeled unless real exchange funding snapshots are injected
- no full cancel-replace state machine yet
- no full restart reconciliation with remote order replay yet
- no production-grade idempotent live execution loop yet

## Current Phase 3 simulation quality upgrades

The engine now also supports a more detailed execution-cost and market-consistency layer:
- depth-aware slippage / impact approximation
- probabilistic queue-based limit fill ratio
- realistic funding snapshots when available in the data stream
- mark-vs-bid/ask consistency checks to block stale or broken market states
- spread / slippage / funding behavior shared by backtest and paper trading

## Current Phase 4 shadow-live layer

A shadow-live orchestration layer now exists:
- `live/shadow_session.py` runs signal generation against live market data without placing exchange orders
- `live/audit_logger.py` records shadow decisions, reconcile outputs, and blocked states as an audit trail
- shadow mode compares local intended execution against live exchange state via the adapter
- watchdog and reconcile hooks remain active to surface unsafe market/runtime states

## Current Phase 4.5 shadow hardening layer

Shadow mode now also includes:
- shadow state persistence and restart recovery
- audit summarization tooling for blocked / reconcile / decision events
- explicit unsafe-market event analytics from shadow audit logs
- persistent last-payload tracking for restart-safe shadow inspection

## Current Phase 5 shadow operations layer

Shadow operations now also includes:
- audit log rotation
- audit summary generation
- operator review report generation
- blocked-event and reconcile-mismatch counting
- persistent shadow state with latest payload inspection

## Current Phase 6 governance layer

A first governance layer now exists for future real-order submission:
- trading modes (`disabled`, `shadow`, `paper`, `approval_required`, `guarded_live`, `maintenance`)
- hard pre-submit governance policy evaluation
- operator approval request queue
- alert sink for governance blocks / submit failures
- guarded live executor that prevents direct adapter bypass in intended order flow

## Current Phase 7 real governance loop

The governance stack now includes a first end-to-end real-order governance loop:
- approval request / approve / reject / consume lifecycle
- governance state storage for mode, maintenance, and emergency stop
- governed live session skeleton
- controlled handoff from intended order to guarded submit
- emergency stop and maintenance propagation into the live session loop

## Current Phase 8 governed live hardening layer

Governed live mode now also includes:
- live session state persistence and restart recovery
- operator CLI for governance mode / maintenance / emergency stop / approval actions
- governed live session audit persistence
- approval consumption and command-driven state transitions

## Current Phase 9 post-submit control layer

Governed live mode now also includes first-pass post-submit controls:
- order lifecycle monitor for stuck / partial / reconciled states
- governed cancel-replace path
- live incident summary tooling
- stronger audit and alert coverage after submit attempts

## Current Phase 10 controlled live readiness layer

The governed live stack now also includes:
- post-submit policy decisions for stuck / partial order outcomes
- readiness checklist tooling
- basic live experimentation runbook
- file-based alert transport scaffold

## Next evolution

- deeper orderbook replay / calibration
- remote reconciliation and restart-safe recovery hardening for live order flow
- exchange shadow-live analytics dashboarding
- richer real-time operator surfaces and notifications
- richer liquidation tiers
- multi-asset portfolio layer
