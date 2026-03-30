# Engine Refactor Phase 3 Summary

## Scope
Phase 3 focused on improving simulation quality rather than strategy research.

## Completed

### Execution / microstructure
- depth-aware slippage approximation
- queue-priority-based partial fill behavior
- maker/taker-aware fill routing in the shared simulator core
- mark/bid/ask consistency validation with risk-event blocking

### Funding
- realistic funding snapshot support via `funding_rate` in the market snapshot
- fallback to annualized approximation only when no snapshot funding is present

### Shared engine behavior
- backtest and paper trading both use the same execution core for:
  - fills
  - slippage
  - funding
  - stale/invalid market-state checks

### CLI integration
Added CLI support for:
- realistic funding toggle
- depth notional
- impact exponent
- orderbook depth levels
- mark consistency enforcement
- stale mark deviation threshold

### Tests
Key integration tests passed:
- execution core
- microstructure behavior
- phase 2 live components
- phase 3 integration
- paper/backtest parity sanity

## Status
Phase 3 is now integrated into the main backtest/paper execution path.

## Remaining gap before live shadow
- remote/live funding ingestion pipeline
- live orderbook snapshot ingestion
- deeper calibration against exchange behavior
- full shadow-execution loop and exchange-state audit trail
