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

## Current limitations

Still simplified compared with exchange-grade execution:
- no orderbook simulation
- no partial fills
- no tiered maintenance margin
- funding uses annualized approximation instead of exchange snapshots
- no maker/taker routing engine yet

## Next evolution

- richer liquidation tiers
- explicit order model
- walk-forward package integration
- real-time notifications
- multi-asset portfolio layer
