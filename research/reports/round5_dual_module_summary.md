# Round 5 Dual-Module + Regime Switcher Summary

## What changed

### New strategy architecture
Added `regime_switcher` with three meta states:
- bull -> route to long module
- neutral -> mostly flat
- crash -> route to extreme-downtrend short module

### New research outputs
- baseline comparison v2
- walk-forward validation v3
- module attribution

## Test status
- unit tests passed: 24/24

## Baseline result
`regime_switcher` improved versus several prior full strategies:
- total return: `+5.27%`
- max drawdown: `-3.51%`

But it still did **not** beat:
- `extreme_downtrend_short` (`+11.46%`)
- `short_lite_regime` (`+5.61%`)

## Module attribution result
This was the most important finding.

- long module trades: `15`
- long module pnl: `-2.72`
- short module trades: `9`
- short module pnl: `+55.44`

Interpretation:
- the current dual-module architecture is **not being carried by both legs**
- almost all realized value came from the crash short overlay
- the long module is currently weak / possibly dilutive

## Regime state distribution
- neutral bars: `4526`
- bull bars: `4135`
- crash bars: `100`

So crash states are rare, but economically important.

## Extended walk-forward result
- avg test return: `+0.05%`
- avg test drawdown: `-0.62%`
- profitable folds: `2/8`
- overfit warning: `True`

## Strategic conclusion
The regime-switcher architecture is conceptually better aligned with BTC than symmetric long/short trading.

However, the current implementation shows:
- crash short module has real signal potential
- long module still lacks edge
- combined architecture looks better in single-window comparison than in extended rolling validation

## Best interpretation right now
Most likely:
- there is a real but narrow edge in selective BTC downside trading
- there is not yet a robust long-side edge in the current regime module

## Recommended next move
1. isolate short overlay as its own primary strategy track
2. redesign long module separately instead of forcing parity
3. test a meta-policy where long exposure is benchmark-driven or disabled unless strong bull confirmation exists
