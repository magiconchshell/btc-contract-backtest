# 💰 Bitcoin Contract Trading Backtest System - Phase 2

Professional cryptocurrency futures backtesting platform with **advanced strategy support**. Built for serious traders who want to validate strategies before going live.

## 🚀 Quick Start

### 1. Navigate to Skill Directory

```bash
cd /Users/magiconch/.openclaw/workspace/skills/public/btc-contract-backtest
```

### 2. Install Dependencies

```bash
uv pip install ccxt pandas numpy matplotlib seaborn
```

### 3. Run Your First Backtest

```bash
# Basic test (default SMA crossover)
uv run python scripts/main.py --days 30 --timeframe 1h

# Try RSI strategy
uv run python scripts/main.py --days 30 --strategy rsi

# MACD on daily candles
uv run python scripts/main.py --days 90 --strategy macd --timeframe 1d

# Custom parameters
uv run python scripts/main.py --strategy rsi \
    --config rsi_period=14 threshold_low=25 threshold_high=75
```

## 🎯 Available Strategies (Phase 2)

| Strategy | Type | Use Case | Parameters |
|----------|------|----------|------------|
| `sma_cross` | Trend Following | Strong trends | short_window, long_window |
| `rsi` | Mean Reversion | Choppy markets | rsi_period, threshold_low, threshold_high |
| `macd` | Momentum | Trend changes | fast_ema, slow_ema, signal_smooth |
| `bollinger` | Volatility | Breakouts/reversions | bb_period, bb_std |
| `hybrid` | Combined | Advanced filtering | multiple indicators |

## 📋 Command Examples

### Test All Strategies Quickly

```bash
for strat in sma_cross rsi macd bollinger; do
    echo "=== Testing $strat ==="
    uv run python scripts/main.py --days 30 --strategy $strat --no-plot
done
```

### Optimal Parameter Search

```bash
# Find best RSI thresholds
for low in 20 25 30; do
    uv run python scripts/main.py --strategy rsi \
        --config threshold_low=$low \
        --output ./optimization/rsi_$low
done
```

### Compare Timeframes

```bash
for tf in 1h 4h 1d; do
    uv run python scripts/main.py --strategy macd \
        --timeframe $tf --days 60 \
        --output ./comparison/$tf
done
```

## 🔧 Configuration Guide

### RSI Strategy Parameters

| Param | Default | Range | Description |
|-------|---------|-------|-------------|
| `rsi_period` | 14 | 7-30 | Lookback period for RSI |
| `threshold_low` | 30 | 20-40 | Oversold level (long trigger) |
| `threshold_high` | 70 | 60-80 | Overbought level (short trigger) |

**Example:** Conservative RSI settings
```bash
--config rsi_period=14 threshold_low=20 threshold_high=80
```

### SMA Crossover Parameters

| Param | Default | Range | Description |
|-------|---------|-------|-------------|
| `short_window` | 10 | 5-20 | Fast MA period |
| `long_window` | 30 | 20-60 | Slow MA period |

**Example:** Faster trading
```bash
--config short_window=5 long_window=15
```

### MACD Parameters

| Param | Default | Description |
|-------|---------|-------------|
| `fast_ema` | 12 | Fast EMA span |
| `slow_ema` | 26 | Slow EMA span |
| `signal_smooth` | 9 | Signal line smoothing |

### Bollinger Bands Parameters

| Param | Default | Description |
|-------|---------|-------------|
| `bb_period` | 20 | Moving average period |
| `bb_std` | 2 | Standard deviations |

## 📊 Output Features

Each backtest generates:

### Performance Metrics
- Total Return (%)
- Sharpe Ratio  
- Maximum Drawdown (%)
- Win Rate (%)
- Number of Trades
- Final Capital

### Visualizations
- 📈 Equity Curve vs Initial Capital
- 📉 Drawdown Analysis
- 💵 Trade P&L Distribution
- 🎯 Entry/Exit Signals Overlay

### Files Saved
```
backtest_reports/
├── BTC_USDT_rsi_20260329_144501_1.png  # Equity curve
├── BTC_USDT_rsi_20260329_144501_2.png  # Drawdown
├── BTC_USDT_rsi_20260329_144501_3.png  # Trade P&L
└── BTC_USDT_rsi_20260329_144501_4.png  # Signals overlay
```

## 💡 Usage Tips

### Daily Check-in
```bash
uv run python scripts/main.py --days 1 --timeframe 1h --strategy rsi
```

### Weekly Strategy Review
```bash
uv run python scripts/main.py --days 7 --timeframe 1d --strategy macd
```

### Long-term Trend Analysis
```bash
uv run python scripts/main.py --days 180 --timeframe 1d --strategy sma_cross
```

### High-Frequency Testing
```bash
uv run python scripts/main.py --days 3 --timeframe 5m --strategy bollinger
```

## ⚠️ Important Notes

1. **Past ≠ Future**: Historical performance doesn't guarantee results
2. **Simulation Reality**: Slippage and fees not fully modeled
3. **Risk Warning**: Crypto trading involves significant risk
4. **Data Quality**: Uses Binance public data (reliable but tick-level)

## 🐛 Troubleshooting

### Common Issues

**"Rate limit exceeded"**
```bash
# Solution: Use longer timeframes or smaller date range
uv run python scripts/main.py --days 30 --timeframe 1d
```

**"Config parse error"**
```bash
# Make sure format is: key=value,key2=value2
uv run python scripts/main.py --strategy rsi \
    --config rsi_period=14,threshold_low=30,threshold_high=70
```

**"Matplotlib display error"**
```bash
# Skip plots if no display available
uv run python scripts/main.py --days 30 --no-plot
```

## 📁 File Structure

```
btc-contract-backtest/
├── SKILL.md                 # Main documentation
├── README.md                # This file
├── dist/
│   └── btc-contract-backtest.skill  # Packaged skill
└── scripts/
    ├── main.py              # CLI entry point
    ├── backtest_engine.py   # Core simulation
    ├── visualize_results.py # Chart generation
    ├── strategy_manager.py  # Strategy hub
    └── strategies/
        ├── __init__.py
        ├── strategy_base.py     # Abstract base class
        └── advanced_strategies.py # RSI, MACD, BB, etc.
```

## 🚦 What's Next?

Ready for **Phase 3**? We'll add:
- ✅ Hybrid multi-strategy system
- ✅ Parameter optimization automation
- ✅ Walk-forward analysis
- ✅ Risk management tools

Let me know when you're ready to continue! 🎯

---

Happy backtesting! 📈💰

*Last Updated: Phase 2 (Advanced Strategies)*
