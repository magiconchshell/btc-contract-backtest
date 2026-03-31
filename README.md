# BTC Contract Backtest

A futures / perpetual contract backtesting and paper-trading toolkit focused on **leveraged BTCUSDT-style trading**, not spot-only simulation.

## Python version

This project now targets **Python 3.12** for local development, testing, and packaging.

## Packaging and CI

- `pyproject.toml` is now the primary packaging/tooling metadata file.
- GitHub Actions CI runs a **hard quality gate** on Python 3.12 for the production-facing code path:
  - `pytest -q`
  - `flake8 src`
  - `mypy src`
  - `python -m build`
- `research/` is intentionally outside the current quality gate scope.
- `setup.py` has been removed in favor of modern `pyproject.toml` packaging metadata.

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
- Regime / trend / volatility-filtered strategy
- Enhanced exit framework: ATR stop, break-even, partial take profit, stepped trailing stop
- Paper trading session state
- Walk-forward analysis foundation

## Environment setup

### Minimal runtime

```bash
/Users/magiconch/.local/bin/uv venv --python /usr/local/bin/python3.12 .venv
.venv/bin/python -m pip install -r requirements-runtime.txt
```

### Development / test environment

```bash
/Users/magiconch/.local/bin/uv venv --python /usr/local/bin/python3.12 .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

### Research / notebook environment

```bash
/Users/magiconch/.local/bin/uv venv --python /usr/local/bin/python3.12 .venv
.venv/bin/python -m pip install -r requirements-research.txt
```

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

### Backtest with enhanced exit logic

```bash
python -m btc_contract_backtest.cli.main \
  --symbol BTC/USDT \
  --timeframe 1h \
  --days 180 \
  --leverage 5 \
  --capital 1000 \
  --strategy regime_filtered \
  --stop-loss-pct 0.02 \
  --take-profit-pct 0.04 \
  --max-holding-bars 48 \
  --atr-stop-mult 1.5 \
  --break-even-trigger-pct 0.015 \
  --partial-take-profit-pct 0.02 \
  --partial-close-ratio 0.5 \
  --stepped-trailing-stop-pct 0.015
```

### Run systematic search

```bash
PYTHONPATH=src ../.venv/bin/python research/systematic_exit_search.py
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

## Dependency layout

- `requirements-runtime.txt` — core engine / CLI / live-session runtime dependencies
- `requirements-dev.txt` — runtime + testing/linting/docs dependencies
- `requirements-research.txt` — dev + notebooks / research / optimization extras
- `requirements.txt` — compatibility wrapper pointing to the dev/test set

`numba` is intentionally not in the default install path right now because the current `llvmlite` build chain is a poor fit for the Python 3.12 macOS x86 environment used here, and the repo does not currently import or require it.

## Status

Current focus: **Phase 5 reorg toward production-grade futures architecture**.

## License

MIT
