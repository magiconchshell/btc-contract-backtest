# Engine Refactor Phase 6 Summary

## Scope
Phase 6 introduced the first live governance layer for future real-order submission.

## Completed

### Governance primitives
Added `live/governance.py`:
- trading mode enum
- governance decision model
- operator approval queue
- alert sink
- governance policy evaluator

### Guarded live executor
Added `live/guarded_live.py`:
- controlled submit path for intended orders
- blocks direct execution when governance disallows it
- supports approval-required mode
- supports guarded-live mode
- emits governance audit records and alerts

### Tests
Added governance tests verifying:
- stale market blocks submission
- approval-required mode creates approval requests
- guarded-live mode allows controlled submit

## Status
The engine now has the first explicit governance gate between strategy intent and exchange submission.

## Remaining gap before real trading
- operator command/control surface
- approval consumption workflow
- emergency stop orchestration across all live components
- production alert delivery
- full live-mode session runner integrating governance with exchange execution
