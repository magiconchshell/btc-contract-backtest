# Round 7 Sparse Portfolio Summary

## What changed

### New architecture
A flat-first sparse portfolio stack was added:
1. default = flat
2. crisis overlay = `short_overlay_switcher`
3. long module = `strong_bull_long`
4. combined portfolio = `sparse_meta_portfolio`

### New research outputs
- sparse portfolio backtest
- sparse portfolio attribution
- sparse portfolio walk-forward

## Test status
- unit tests passed: 30/30

## Backtest result
Comparison over the test window:
- `flat_baseline`: `0.00%`
- `short_overlay_switcher`: `+12.08%`, DD `-3.86%`
- `strong_bull_long`: `-3.34%`, DD `-4.20%`
- `sparse_meta_portfolio`: `+8.34%`, DD `-4.20%`

Interpretation:
- sparse portfolio is better than flat
- but still worse than just running the short crisis overlay alone
- the new long module remains a drag

## Attribution result
Sparse portfolio contribution:
- short overlay pnl: `+117.98`
- strong bull long pnl: `-34.58`

Occupancy:
- flat: `8724`
- short overlay: `29`
- strong bull long: `8`

Interpretation:
- the architecture is truly sparse, which is good
- but almost all economic value still comes from the crisis short overlay
- the new long module did not validate

## Walk-forward result
- avg test return: `+0.17%`
- avg test drawdown: `-0.56%`
- profitable folds: `1/8`
- overfit warning: `True`
- selection counts: `{'strong_bull_long': 4, 'flat_baseline': 4}`

Interpretation:
- in rolling OOS, the system often prefers doing nothing
- this is actually useful information: **flat is a strong benchmark**
- current long logic is not yet good enough to justify activation

## Strategic conclusion
This round confirms three things:
1. flat-first design is directionally correct
2. crisis short overlay is still the only convincingly valuable module
3. long-side edge remains unresolved

## Best practical conclusion right now
If forced to deploy the current research stack conservatively:
- default to flat
- use crisis-gated short overlay selectively
- do not enable the current strong bull long module yet

## Recommended next move
1. pause long-module optimization unless a new hypothesis appears
2. treat flat as the true baseline, not as an absence of strategy
3. refine short overlay only as a crisis hedge / overlay, not as an always-on engine
4. if pursuing longs again, start from a fundamentally different hypothesis rather than incrementally tightening the current one
