# BTC Contract Backtest

A futures / perpetual contract backtesting and paper-trading toolkit focused on **leveraged BTCUSDT-style trading**, not spot-only simulation.

## What this project is for

This repo is specifically designed for:
- **Perpetual / futures contracts**
- **Leverage-aware backtesting**
- **Long and short positions**
- **Funding, fees, and liquidation-aware simulation**
- **Paper trading for contract strategies**
- **Walk-forward / optimization workflow**

This repo is **not intended as a spot-only buy/sell portfolio tracker**.

## Core capabilities

- Futures/perpetual market model
- Long / short signal engine
- Leverage-aware PnL
- Basic liquidation logic
- Fee + funding integration
- RSI / SMA / MACD strategies
- Voting hybrid strategy
- Paper trading session state
- Walk-forward analysis foundation

## Repo structure

```text
src/btc_contract_backtest/
├── cli/
├── config/
├── engine/
├── live/
├── reporting/
└── strategies/

tests/
docs/
```

## Example usage

### Backtest futures strategy

```bash
python -m btc_contract_backtest.cli.main --symbol BTC/USDT --timeframe 1h --days 180 --leverage 5 --capital 1000 --strategy rsi
```

### Paper trading summary

```bash
python -m btc_contract_backtest.cli.main --paper-summary --symbol BTC/USDT --timeframe 1h --leverage 5
```

### Run visual HTML backtest report server

```bash
uvicorn btc_contract_backtest.cli.report_server:app --host 0.0.0.0 --port 8123
```

Then open:
- `http://localhost:8123`
- or expose port `8123` with ngrok

## Design requirement check

This repo now explicitly targets your original requirement:
- tested on **contracts**, not spot
- supports **leverage**
- supports **short selling**
- built around **BTCUSDT-style perpetuals**

## Status

Current focus: **Phase 5 reorg toward production-grade futures architecture**.

## License

MIT
