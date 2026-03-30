# Round 2 Upgrade Summary

## What changed

### Entry logic upgrade
Added `regime_filtered` strategy with:
- trend filter via fast/slow EMA regime
- regime strength filter via ADX
- volatility filter via ATR percentage band
- confirmation by RSI + MACD alignment

### Exit framework v2
Added:
- ATR stop
- break-even stop
- partial take profit
- stepped trailing stop
- existing stop loss / take profit / time exit remain supported

## Test status
- unit tests passed: 13/13

## Systematic search conclusion
The best combinations were dominated by `regime_filtered`, not `hybrid`.

Best-performing region:
- strategy: `regime_filtered`
- stop loss: `0.02` or `0.03`
- take profit: `0.03`
- max holding bars: `48`
- ATR stop mult: `1.5`
- break-even trigger: `0.015`
- partial take profit: `None`
- stepped trailing stop: `None`

## Best observed result
- total return: `+2.62%`
- max drawdown: `-9.59%`
- win rate: `38.89%`
- trades: `18`
- final capital: `1026.25`
- liquidation events: `0`

## Interpretation
This is the first test batch where the upgraded entry+exit stack moved the system from catastrophic loss into small positive return with controlled drawdown.

The main improvement appears to come from **better trade selection**, not from more aggressive exit complexity.

## Important finding
In this search space:
- ATR stop helped
- break-even stop helped
- tighter time window at 48 bars helped
- partial take profit usually did **not** help
- stepped trailing stop usually did **not** help

## Recommended next move
1. Expand strategy search around `regime_filtered`
2. Tune leverage / notional sizing separately
3. Add walk-forward validation to avoid overfitting
4. Consider asymmetric long/short filters instead of symmetric logic
