# 🐚 Magic Conch Shell Trading Engine v2.0

A professional-grade, multi-session framework for **backtesting, paper trading, and executing live quantitative strategies** on **Binance Futures** (Perpetual contracts). 

Magic Conch Shell bridges the gap between historical simulation and live execution with a **100% shared logical simulation layer**, ensuring that strategies validated in backtesting perform identically in production under the same market constraints.

---

## 🎯 Architecture & Mission

The **Architecture v2.0** introduces a complete separation between the core trading engine and the real-time monitoring dashboard, managed by a robust **Multi-Session Manager**.

- **Multi-Session Architecture**: Run multiple independent bots or historical backtests concurrently. Each session is isolated with its own UUID, state mapping, and dedicated execution thread.
- **Unified Logic Environment**: Strategies are defined once. The exact same PnL evaluations, exchange constraints, and risk governance triggers evaluate identically across all modes (`BACKTEST`, `PAPER`, `LIVE`).
- **Real-Time Visualization**: A modern, glassmorphism-inspired web dashboard built with Next.js and high-performance charting libraries.

---

## ✨ Key Features

### 1. Concurrent Strategy Execution
Run diverse alpha models simultaneously. Monitor a high-frequency scalper alongside a trend-following macro strategy without cross-talk or performance degradation.

### 2. Interactive Dashboard
- **Sidebar Session Manager**: Switch between active sessions, view historical results, or launch new ones in seconds.
- **Dynamic Charting**: Real-time price candlesticks and account equity curves with precise trade markers (Buy/Sell dots).
- **Latest Decision Panel**: Full transparency into the bot's current price polling, signal generation, and intended order quantity.
- **Performance Metrics**: Live tracking of Win Rate, Profit Factor, Total Trades, and Drawdown.

### 3. Session-Aware Logging
The integrated log viewer uses **Thread-Local Storage (TLS)** to tag every system event with the originating `session_id`. This allows the dashboard to filter and display only relevant logs for the strategy you are currently inspecting.

### 4. Strict Risk Governance
- **Built-in Watchdogs**: Pre-execution filters for lot/tick precision and tick boundaries.
- **Emergency Stop Protocol**: Automatic circuit breakers triggered by consecutive API failures or critical drawdown thresholds.
- **Exchange Reconciliation**: Native state-syncing to align local virtual positions with exchange truth.

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.12**
- **Node.js 18+**
- **Binance API Keys** (with Futures permissions enabled)

### 1. Backend Setup
We recommend using `uv` for ultra-fast, deterministic dependency management.

```bash
# 1. Setup virtual environment
uv venv --python 3.12 .venv
source .venv/bin/activate

# 2. Install dependencies
uv pip install -r requirements-runtime.txt

# 3. Configure Environment
# Create a .env file with your credentials:
# BINANCE_API_KEY=your_key
# BINANCE_API_SECRET=your_secret
```

### 2. Starting the Engine (Backend)
The backend manages the strategy loops and provides a REST/WebSocket API for the dashboard.

```bash
./run_dashboard.sh
```
*Backend is now accessible at http://localhost:8000*

### 3. Starting the Dashboard (Frontend)
The frontend provides the user interface for management and monitoring.

```bash
cd frontend
npm install
npm run dev
```
*Frontend is now live at http://localhost:3000*

---

## 🔬 Trading Modes

- **`BACKTEST`**: Validate theories against historical Binance market models. Results are instantly visualized on the dashboard.
- **`PAPER`**: Connect to live market data feeds to simulate executions without risk.
- **`LIVE` (GUARDS_ACTIVE)**: Execute on Binance Mainnet with strict architectural position limits and trade-once safety protocols.

---

## 📂 Project Layout

- `src/btc_contract_backtest`: Core strategy engine, risk modules, and indicators.
- `src/btc_contract_backtest/web`: FastAPI backend including the `BotManager` and WebSocket server.
- `frontend/`: Next.js 16 application with custom charting components and session context.
- `scripts/`: Operational utilities and release validation tools.

---

## 📈 Strategy Development

New strategies can be added to `src/btc_contract_backtest/strategies/`. Simply define the signal logic once, and it becomes available for both backtests and live sessions via the "Create New Session" view in the dashboard.

---

## Code Quality
- Validated under stringent static checks using `ruff` and `mypy`.
- Automatic CI `release_gate.py` prohibits structurally broken releases.
- Native `pytest` suite enforcing testing coverage over execution flows and WebSocket transports.

© 2026 Magic Conch Shell Engine | Multi-Session Architecture v2.0
