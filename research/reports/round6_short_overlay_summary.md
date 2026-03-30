# Round 6 Short Overlay Primary Track Summary

## What changed

### New primary-track architecture
Added `short_overlay_switcher`:
- bull: usually flat
- neutral: flat
- crash: activate short overlay
- optional bull-long passthrough exists but is disabled by default

### New research outputs
- short overlay parameter search
- short-only walk-forward
- overlay vs flat baseline

## Test status
- unit tests passed: 26/26

## Key finding #1: short overlay search has a clear sweet spot
Best search region clustered around:
- breakdown lookback: `16`
- ADX threshold: `24~28`
- stop loss: `1.5%`
- take profit: `3%`
- max holding bars: `48`
- ATR stop: `1.5`

Best in-sample result:
- total return: `+25.04%`
- max drawdown: `-6.10%`

## Key finding #2: short-only walk-forward fails
- avg test return: `-1.14%`
- avg test drawdown: `-1.37%`
- profitable folds: `0/8`
- overfit warning: `True`

Interpretation:
- pure short-as-main-strategy does **not** survive rolling OOS validation
- the edge is too episodic to carry the entire system continuously

## Key finding #3: short overlay beats staying flat when gated well
Overlay vs flat baseline:
- flat baseline: `0.00%`
- extreme_downtrend_short: `+0.02%`, DD `-13.30%`
- short_overlay_switcher: `+12.08%`, DD `-3.86%`

Interpretation:
- raw short strategy without stronger regime gating is noisy and risk-heavy
- regime-gated short overlay is materially better
- the real edge seems to be in **when to turn the short engine on**, not just the short engine itself

## Strategic conclusion
This round materially narrows the direction:
- **Do not promote pure short-only trading to the main system**
- **Do promote regime-gated short overlay as a specialized crisis module**

The strongest current evidence supports:
- flat most of the time
- short only during well-defined crash regimes
- long side still needs a separate redesign rather than being forced into the same architecture

## Recommended next move
1. treat `short_overlay_switcher` as a crisis overlay, not a standalone core strategy
2. redesign long exposure independently
3. test a sparse meta-portfolio:
   - flat default
   - optional long module only with strong confirmation
   - short overlay only in crash states
