# Round 3 Walk-Forward + Position Sizing Summary

## What changed

### 1. Walk-forward validation
Added a rolling train/test evaluation script:
- train window: 90 days
- test window: 30 days
- folds: 4

### 2. Long/short asymmetry
Added `regime_asymmetric` strategy with:
- looser long thresholds
- stricter short thresholds
- separate ATR and ADX gates for long vs short

### 3. Position sizing upgrade
Added to the engine:
- risk-per-trade sizing
- ATR-based position sizing
- drawdown-adaptive position scaling

## Test status
- unit tests passed: 17/17

## Walk-forward result
- average test return: `+0.84%`
- average test drawdown: `-0.77%`
- profitable test folds: `2/4`
- overfit warning flag: `False`

## Interpretation
This is **not strong proof of robust edge**, but it is also **not the pattern of obvious overfitting**.

Why:
- The strategy stayed near flat-to-positive out of sample.
- Drawdown remained very small.
- One fold had no trades, which means the filter is selective rather than constantly forcing exposure.
- The chosen model across folds stayed stable: the base `regime_filtered` setup won each time.

## Important read
The upgraded position sizing and risk controls appear to be helping more with **damage containment and stability** than with boosting raw return.

That is good for survivability, but the return stream is still too weak to declare success.

## Practical conclusion
Current status is:
- not obviously overfit
- materially safer than earlier versions
- still weak on total edge generation

## Recommended next move
1. Extend walk-forward to more folds / longer history
2. Add market regime labelling to explain the no-trade fold
3. Try long-only / short-lite variants for BTC
4. Add benchmark comparison vs passive BTC or simple trend-following baseline
