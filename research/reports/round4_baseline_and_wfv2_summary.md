# Round 4 BTC Bias + Baselines + Extended Walk-Forward Summary

## What changed

### BTC bias strategies added
- `long_only_regime`
- `short_lite_regime`
- `extreme_downtrend_short`

### Baselines added
- `buy_and_hold_long`
- `ema_trend`

### Validation upgraded
- walk-forward expanded to 8 folds
- train window: 120 days
- test window: 30 days

## Test status
- unit tests passed: 22/22

## Baseline comparison result
Top performers over the comparison window:
1. `extreme_downtrend_short`: `+11.46%`, DD `-6.72%`
2. `short_lite_regime`: `+5.61%`, DD `-2.52%`
3. `regime_asymmetric`: `+4.68%`, DD `-2.64%`
4. `regime_filtered`: `+2.06%`, DD `-3.64%`

Important takeaway:
- `long_only_regime` did **not** beat the short-aware variants
- fully symmetric shorting still looks suboptimal
- **selective / extreme shorting** appears materially more promising for BTC than either symmetric shorting or disabling shorts entirely

## Extended walk-forward result
- avg test return: `+0.05%`
- avg test drawdown: `-0.62%`
- profitable folds: `2/8`
- overfit warning: `True`

## Interpretation
This longer validation is more trustworthy than the earlier 4-fold run.

It suggests:
- the system is still stable and low-drawdown
- but the edge is weak and inconsistent across time
- once tested over longer rolling windows, the apparent strength largely disappears

So the updated conclusion is:
- not catastrophic
- not reckless
- but still **not robust enough** to claim durable trading edge

## Strategic conclusion
The most interesting current direction is **BTC downside-selective logic**, especially:
- short only during extreme downtrend breakdowns
- or short-lite filters rather than symmetric long/short design

## Recommended next move
1. isolate and optimize `extreme_downtrend_short`
2. test portfolio-style combination:
   - long-only regime module
   - extreme-downtrend short overlay
3. benchmark against a regime-switching meta-policy instead of single-model trading
