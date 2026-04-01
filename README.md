# BTC Contract Backtest (Production Live Engine)

A professional-grade framework for **backtesting, paper trading, and executing live quantitative strategies** on **Binance Futures** (Perpetual contracts). 

This project bridges the historical gap between backtesting environments and live execution architectures. By implementing a **100% shared logical simulation layer**, it ensures that a strategy yielding specific executions, partial fills, or trailing stops in backtesting will perform *identically* in production under the same market constraints.

---

## 🎯 What This Project Is For

- **Leveraged Quantitative Trading**: Focused explicitly on Perpetual/Futures contracts (Long/Short), integrating real-world fee/funding structures and isolated margin simulations.
- **Production Event-Driven Execution**: Connects to Binance via real-time WebSocket feeds with robust disconnected-state handling, rate-limit backoffs, and strict `kill_switch` protections.
- **Flawless Strategy Simulation**: Strategies are coded once. The exact same PnL evaluations, exchange constraints (Lot/Tick precision), and stop-loss logic evaluate identically in both the fastest vectorized backtests and the live tick-by-tick websocket feeds.
- **Gradual Go-Live Workflow**: Transition seamlessly through operating modes:
  - `BACKTEST`: Validate theories over historical data.
  - `PAPER`: Connect to live data feeds, simulating executions.
  - `APPROVAL_REQUIRED`: Evaluate signals entirely via live data, but hold for manual operator confirmation before executing on Binance.
  - `GUARDED_LIVE`: Execute on Binance Mainnet but with strict architectural maximum position limits.
  - `MAINTENANCE`: Suspend logic without killing background connectivity.

This is **not** a basic daily-spot portfolio tracker—it is a robust event-driven futures engine designed to sit on remote servers unharmed for months.

---

## 🛠 Core Technical Features

### 1. Unified Exit Logic Environment
Instead of duplicated logic mapping strategies to live execution versus historical runs, this engine utilizes a pure, shared functional layer (`exit_logic.py`). PnL mapping, Trailing Stop calculation, Break-Even triggers, and ATR Stop computations execute deterministically exactly the same in both the Backtest Engine and the Live Session.

### 2. Native WebSocket Tolerance & Reconnection
The `BinanceFuturesUserDataEventSource` continuously ingests streams via `websocket-client`. It integrates directly into the runtime `RunLoop` with native Exponential Backoff policies. If Binance connections drop, rate limits trigger, or ListenKeys expire:
- The `ws_transport` spins down cleanly.
- Exponential backoff is calculated avoiding rate bans.
- Connection reinstates seamlessly in the background without throwing exceptions into the trading logic loop.
- **REST State Reconciliation** is immediately triggered to ensure blind-spots during the downtime didn't miss partial fills or exchange liquidations.

### 3. Strict Risk Governance Watchdogs
Live Trading is wrapped in a `HeartbeatWatchdog` & `ExchangeConstraintChecker`.
- **Pre-execution Filtering:** Before your strategy's signal ever touches the Exchange Adapter (via `ccxt`), the constraints engine evaluates tick sizes, lot boundaries, and precision filters ensuring rejecting logic is handled locally.
- **Emergency Stop Protocol:** The `LiveRiskConfig` manages API failures. If continuous network errors block logic loops from completing their steps out-of-bounds of the predefined consecutive failure policy, the system triggers `emergency_stop`—pausing execution and triggering an immediate `cancel_all_orders` command to protect liquid capital.

---

## 🚀 Environment Setup

This project uses modern `pyproject.toml` specs and utilizes `uv` for ultra-fast deterministic dependencies. 
Requires **Python 3.12**.

```bash
# 1. Setup python environment
uv venv --python 3.12 .venv
source .venv/bin/activate

# 2. Install dependencies (Production & Runtime)
uv pip install -r requirements-runtime.txt

# 3. Setup Secrets
# Create a .env file and add your keys
export BINANCE_FUTURES_TESTNET_API_KEY="your_api_key_here"
export BINANCE_FUTURES_TESTNET_API_SECRET="your_secret_here"
```

*For Development/CI builds, see `requirements-dev.txt` for `ruff`, `pytest`, and `mypy` integrations.*

---

## 💻 Operations & Example Usage

### 1. Robust Engine Backtesting
Run historical tests directly via the CLI against binance market models.

```bash
python -m btc_contract_backtest.cli.main \
  --symbol BTC/USDT \
  --timeframe 1h \
  --days 180 \
  --leverage 3 \
  --capital 1000 \
  --strategy sparse_portfolio \
  --risk-config \
    max_position_notional_pct=0.8 \
    stop_loss_pct=0.04 \
    take_profit_pct=0.1
```

### 2. Connecting To Testnet / Test Environments
Easily run Live Socket Testing without executing true orders. Start an event-soak test to monitor connection elasticity, runtime step iterations, and API health metrics without financial risk.
*Note: Binance Futures Testnet data synchronization is officially deprecated in `ccxt`. To validate actual trades, execute in `TradingMode.GUARDED_LIVE` utilizing Mainnet with micro-capital ($15 sizes).*

```bash
python scripts/run_soak_test.py
```

### 3. Real-Time Status Monitoring
The `live_session.py` architecture exports telemetry continuously via a background API. Start your live bot, and simply query its metrics externally for dashboard mapping:
```json
{
  "trading_mode": "approval_required",
  "symbol": "BTC/USDT",
  "heartbeat": "2026-03-31T17:35:49.3331Z",
  "watchdog": {
     "halted": false,
     "consecutive_failures": 0 
  }
}
```

## Code Quality & CI
- Validated under stringent static checks using `ruff` and `mypy`.
- Automatic CI `release_gate.py` prohibits structurally broken releases. You can inspect the pipeline locally running `python scripts/release_gate.py --report --json`.
- Developers must execute the release validation gate locally using `python scripts/release_gate.py --run --check-clean` prior to merging logic. 
- Native `pytest` suite enforcing testing coverage specifically over the `ws_transport` retry architectures and mock `SimulatorCore` execution loops.
