---
name: btc-contract-backtest
description: Professional Bitcoin/cryptocurrency contract trading backtest system with advanced hybrid strategies and automated parameter optimization. Use when you need to test multiple trading strategies (SMA, RSI, MACD, Bollinger Bands) or combine them into voting-based hybrid systems on historical Binance data. Features customizable parameters, timeframe flexibility (1m-7d), leverage simulation, and comprehensive visualized results perfect for validating crypto trading strategies before live deployment.
---

# 💰 Bitcoin Contract Trading Backtest System - Phase 3

Professional-grade backtesting engine for cryptocurrency futures/contracts trading with **hybrid strategies**, **automated optimization**, and **trend filtering**. Test any strategy on historical Binance data with full customization.

## 🆕 What's New in Phase 3?

✅ **Hybrid Strategies** - Combine multiple indicators with voting system  
✅ **Trend Filtering** - Only take signals aligned with major trend  
✅ **Automated Parameter Optimization** - Grid search for best params  
✅ **Advanced Configuration** - JSON-style complex configs  
✅ **Robust Error Handling** - Graceful failures during execution  

## Quick Start

### Basic Backtest (default SMA Crossover)

```bash
cd /Users/magiconch/.openclaw/workspace/skills/public/btc-contract-backtest

# Install dependencies
uv pip install ccxt pandas numpy matplotlib seaborn

# Run basic backtest
uv run python scripts/main.py --days 30 --timeframe 1h
```

### Hybrid Strategy (Multi-Indicator Voting)

```bash
# 2-strategy hybrid (RSI + MACD), needs 1 vote to enter
uv run python scripts/main.py --strategy hybrid \
    --config '{"base_strategies": [{"name":"rsi"}, {"name":"macd"}], "required_votes": 1}'

# 3-strategy hybrid (needs 2 votes = majority)
uv run python scripts/main.py --strategy hybrid \
    --config '{"base_strategies": [{"name":"sma_cross"}, {"name":"rsi"}, {"name":"macd"}], "required_votes": 2}'
```

### Trend-Filtered Strategy

```bash
# Only take RSI signals that align with 200-period trend
uv run python scripts/main.py --strategy trend_filter \
    --config '{"base_strategy": "rsi", "trend_sma_period": 200}'
```

### Parameter Optimization

```bash
# Auto-tune RSI parameters
uv run python scripts/main.py --optimize rsi \
    --param-grid 'rsi_period=[10,14,20]' \
    --metric sharpe

# Optimize SMA crossover windows
uv run python scripts/main.py --optimize sma_cross \
    --param-grid 'short_window=[5,10,15],long_window=[20,30,50]' \
    --metric return
```

## Available Strategies (Phase 3)

| Strategy | Description | Best For |
|----------|-------------|----------|
| `sma_cross` | Simple Moving Average Crossover | Trend following |
| `rsi` | RSI Mean Reversion | Range-bound markets |
| `macd` | MACD Signal Line Crossover | Momentum trading |
| `bollinger` | Bollinger Bands Reversion | Volatility trading |
| `hybrid` | Multi-indicator voting system | Reduced false signals |
| `trend_filter` | Filter by major trend | Trend confirmation |

## Command Line Options

```
--symbol SYMBOL        Trading pair (default: BTC/USDT)
--days DAYS            Historical days to analyze (default: 30)
--timeframe TIMEFRAME  Candle timeframe
                       Options: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 7d
--leverage LEVEL       Leverage multiplier (default: 10)
--strategy STRATEGY    Strategy to use
                       Choices: sma_cross, rsi, macd, bollinger, hybrid, trend_filter
--config JSON          Strategy configuration (JSON format)
--optimize STRATEGY    Run parameter optimization
--param-grid GRID      Parameter ranges: key=[val1,val2]
--metric METRIC        Optimization target (sharpe, return, winrate)
--output DIRECTORY     Output folder for reports
--no-plot              Skip generating plots (faster execution)
```

## Hybrid Strategy Configuration

Create powerful multi-strategy combinations:

### 2-Strategy Hybrid (Majority Vote = 2)

```bash
uv run python scripts/main.py --strategy hybrid \
    --config '{"base_strategies": [{"name":"sma_cross"}, {"name":"rsi"}], "required_votes": 2}'
```

Only enters when BOTH SMA and RSI agree → More conservative

### 3-Strategy Hybrid (Majority Vote = 2 of 3)

```bash
uv run python scripts/main.py --strategy hybrid \
    --config '{"base_strategies": [{"name":"sma_cross"}, {"name":"rsi"}, {"name":"macd"}], "required_votes": 2}'
```

Requires 2 out of 3 to agree → Balanced approach

### Loose Hybrid (Any One Vote)

```bash
uv run python scripts/main.py --strategy hybrid \
    --config '{"base_strategies": [{"name":"rsi"}, {"name":"macd"}], "required_votes": 1}'
```

Enters if ANY strategy signals → More aggressive

## Trend Filtering

Filter signals based on long-term trend direction:

```bash
# Only go LONG when price is above 200 EMA
# Only go SHORT when price is below 200 EMA
uv run python scripts/main.py --strategy trend_filter \
    --config '{"base_strategy": "rsi", "trend_sma_period": 200}'
```

## Parameter Optimization

Auto-find optimal parameters using grid search:

```bash
# Optimize RSI period
uv run python scripts/main.py --optimize rsi \
    --param-grid 'rsi_period=[7,10,14,21,30]' \
    --metric sharpe

# Optimize SMA windows
uv run python scripts/main.py --optimize sma_cross \
    --param-grid 'short_window=[5,10,15],long_window=[20,30,50]' \
    --metric return

# Multiple metrics
for metric in sharpe return winrate; do
    uv run python scripts/main.py --optimize rsi \
        --param-grid 'threshold_low=[20,25,30]' \
        --metric $metric
done
```

## Usage Patterns

### Daily Strategy Check-in
```bash
uv run python scripts/main.py --days 1 --timeframe 1h --strategy rsi
```

### Comprehensive Weekly Analysis
```bash
for strat in sma_cross rsi macd bollinger; do
    echo "=== Testing $strat ==="
    uv run python scripts/main.py --days 7 --strategy $strat --output ./weekly/$strat
done
```

### Find Best Hybrid Configuration
```bash
for votes in 1 2; do
    uv run python scripts/main.py --strategy hybrid \
        --config '{"base_strategies": [{"name":"rsi"}, {"name":"macd"}], "required_votes": '$votes'}' \
        --output ./hybrid_test/votes_$votes
done
```

### Optimal Parameter Search
```bash
# Try different RSI thresholds
for low in 20 25 30 35; do
    uv run python scripts/main.py --strategy rsi \
        --config threshold_low=$low \
        --output ./opt_search/rsi_low_$low
done
```

## Supported Trading Pairs

All Binance Futures pairs supported:
- **BTC/USDT** ⭐ Most popular
- **ETH/USDT**
- **SOL/USDT**
- **BNB/USDT**
- 100+ more!

## Backtest Results

Each backtest generates:

### Performance Metrics
- Total Return (%)
- Sharpe Ratio
- Maximum Drawdown (%)
- Win Rate (%)
- Total Trades Executed
- Final Capital

### Visualizations
- Equity Curve vs Initial Capital
- Drawdown Analysis (peak-to-trough)
- Trade P&L Distribution
- Entry/Exit Signals Overlay

### Files Saved
```
backtest_reports/
├── BTC_USDT_hybrid_20260329_145048_1.png  # Equity curve
├── BTC_USDT_hybrid_20260329_145048_2.png  # Drawdown
├── BTC_USDT_hybrid_20260329_145048_3.png  # Trade P&L
└── BTC_USDT_hybrid_20260329_145048_4.png  # Signals overlay
```

## Security Notes

- Uses CCXT library (community-maintained)
- Only reads public market data
- No API keys required for historical data
- All calculations done locally
- Optional: Real-time API testing requires separate setup

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Rate limit exceeded" | Use longer timeframes or smaller date range |
| "No data found" | Increase `--days` or change timeframe |
| "Config parse error" | Use valid JSON format for complex configs |
| "Hybrid gives no signals" | Lower `required_votes` or use looser config |
| "Matplotlib display error" | Add `--no-plot` flag if running headless |

## Current Implementation (Phase 3)

**Base Strategies:**
- ✅ SMA Crossover
- ✅ RSI Mean Reversal
- ✅ MACD Crossover
- ✅ Bollinger Bands Reversion

**Advanced Features:**
- ✅ Hybrid voting system
- ✅ Trend filtering
- ✅ Parameter optimization
- ✅ Cross-validation support

## Example Outputs

### Hybrid Strategy Result

```
============================================================
🎯 BACKTEST SUMMARY - BTC/USDT_hybrid
============================================================

Metric                    Value                         
----------------------------------------------------------------------
Total Return              8.45%
Sharpe Ratio              0.72
Max Drawdown              -9.85%
Win Rate                  55.56%
Total Trades              18
Final Capital             $10845.00 (+8.45%)
======================================================================
```

### Optimized Parameters

```
🔍 Starting parameter optimization...
   Tested 27 combinations
✅ Optimization completed!
   Best params: {'rsi_period': 14, 'threshold_low': 30}
   Score (sharpe): 1.2345
```

---

*Ready to trade smarter, not harder! 🚀📈*
