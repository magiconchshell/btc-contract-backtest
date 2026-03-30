from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, RiskConfig
from btc_contract_backtest.engine.futures_engine import FuturesBacktestEngine
from btc_contract_backtest.reporting.html_report import build_report_html
from btc_contract_backtest.strategies import build_strategy
from btc_contract_backtest.strategies.hybrid import VotingHybridStrategy

app = FastAPI(title="BTC Contract Backtest Report")
CACHE = {"html": None, "payload": None}


def _run_backtests():
    contract = ContractSpec(symbol="BTC/USDT", leverage=5)
    account = AccountConfig(initial_capital=100.0)
    risk = RiskConfig(max_position_notional_pct=0.95)
    engine = FuturesBacktestEngine(contract, account, risk, timeframe="1d")
    df = engine.fetch_historical_data("2025-01-01", datetime.now().strftime("%Y-%m-%d"))

    candidates = [
        ("RSI Reversal", build_strategy("rsi", {"rsi_period": 14, "threshold_low": 30, "threshold_high": 70})),
        ("MACD Cross", build_strategy("macd", {"fast_ema": 12, "slow_ema": 26, "signal_smooth": 9})),
        ("Hybrid RSI + MACD", VotingHybridStrategy([build_strategy("rsi"), build_strategy("macd")], required_votes=1)),
    ]

    strategies = []
    for name, strategy in candidates:
        signal_df = strategy.generate_signals(df)
        results = engine.simulate(signal_df)
        metrics = engine.calculate_metrics(results)
        strategies.append(
            {
                "name": name,
                "metrics": metrics,
                "equity_curve": [
                    {"timestamp": str(r["timestamp"]), "equity": float(r["equity"])}
                    for _, r in results["equity_curve"].iterrows()
                ],
            }
        )
    return {"generated_at": datetime.utcnow().isoformat(), "strategies": strategies}


@app.get("/", response_class=HTMLResponse)
def index():
    if CACHE["html"] is None:
        payload = _run_backtests()
        CACHE["payload"] = payload
        CACHE["html"] = build_report_html(payload)
    return CACHE["html"]


@app.get("/refresh", response_class=HTMLResponse)
def refresh():
    payload = _run_backtests()
    CACHE["payload"] = payload
    CACHE["html"] = build_report_html(payload)
    return CACHE["html"]
