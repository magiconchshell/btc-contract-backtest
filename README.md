# 💰 Bitcoin Contract Trading Backtest System

Professional-grade cryptocurrency trading backtesting platform with advanced strategy support, risk management, and comprehensive analytics.

![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Version](https://img.shields.io/badge/Version-4.0.0-yellow.svg)

## 🚀 Features

- **6 Advanced Strategies**: SMA Crossover, RSI Reversal, MACD, Bollinger Bands, Hybrid Voting, Trend Filtering
- **Transaction Cost Modeling**: Realistic fees, slippage, and funding rate simulation
- **Risk Management**: Position sizing, stop-loss/take-profit, trailing stops, portfolio limits
- **Performance Analytics**: Sharpe ratio, Sortino ratio, win rate, profit factor, max drawdown
- **Visual Reports**: Multi-page PNG reports with equity curves, drawdown charts, trade analysis
- **Parameter Optimization**: Automatic grid search for optimal strategy parameters

## 📦 Installation

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/btc-contract-backtest.git
cd btc-contract-backtest

# Install dependencies
uv pip install ccxt pandas numpy matplotlib seaborn

# Run a quick test
uv run python scripts/main.py --days 30 --strategy rsi
```

## 🎯 Quick Start

```bash
# Test different strategies
uv run python scripts/main.py --days 60 --strategy rsi
uv run python scripts/main.py --days 90 --strategy macd --timeframe 4h
uv run python scripts/main.py --strategy hybrid \
    --config '{"base_strategies": [{"name":"rsi"}, {"name":"macd"}], "required_votes": 1}'

# With cost modeling and risk management
uv run python scripts/main.py --days 60 --include-costs --risk conservative
```

## 📊 Example Output

```
======================================================================
🎰 BITCOIN CONTRACT BACKTEST SYSTEM (PHASE 4)
======================================================================
📅 Date Range: 2025-01-01 to 2026-03-29
🪙 Symbol: BTC/USDT | Leverage: 5x | Capital: $100
----------------------------------------------------------------------
✅ Loaded 458 daily candles
🤖 Running RSI_Reversal...
   Generated 50 signals
💸 Transaction costs enabled
💹 Simulating trades...

📊 RESULTS:
   Total Return:    +18.45%
   Annualized:      +26.18%
   Sharpe Ratio:    1.51
   Win Rate:        59.26%
   Max Drawdown:    -6.82%
   Final Capital:   $118.45
======================================================================
```

## 🛠️ Development Status

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | Core Engine | ✅ Complete |
| 2 | Advanced Strategies | ✅ Complete |
| 3 | Optimization & Hybrids | ✅ Complete |
| 4 | Risk Management | ✅ Complete |

## 📁 Project Structure

```
btc-contract-backtest/
├── scripts/
│   ├── main.py                 # CLI entry point
│   ├── backtest_engine.py      # Core backtest engine
│   ├── strategy_manager.py     # Strategy hub
│   ├── transaction_costs.py    # Cost modeling
│   ├── risk_management.py      # Risk controls
│   ├── optimization.py         # Auto-optimization
│   └── strategies/             # Strategy implementations
│       ├── strategy_base.py
│       ├── advanced_strategies.py
│       └── hybrid_strategy.py
├── tests/                      # Unit tests (coming soon)
├── docs/                       # Documentation
│   ├── SKILL.md
│   ├── API_REFERENCE.md
│   └── USAGE_GUIDE.md
├── requirements.txt            # Python dependencies
├── setup.py                    # Package installation
├── LICENSE                     # MIT License
└── README.md                   # This file
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👨‍💻 Author

Created by Magic Conch Shell Team

## 📞 Contact

- Website: [YourWebsite.com](https://yourwebsite.com)
- Email: your.email@example.com
- Discord: YourServer#1234

---

*Built with ❤️ for crypto traders worldwide!* 📈💰

**Tags:** #cryptocurrency #bitcoin #trading #backtest #python #algorithmic-trading #quantitative-finance #binance #futures-trading
