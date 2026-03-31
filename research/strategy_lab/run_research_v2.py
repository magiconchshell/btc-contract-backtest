#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, RiskConfig
from btc_contract_backtest.engine.futures_engine import FuturesBacktestEngine


def load_strategy(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load strategy module from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name in dir(mod):
        if name.startswith("V"):
            return getattr(mod, name)()
    raise RuntimeError("No strategy class found")


def main():
    version = "v2"
    strategy_path = ROOT / "strategies" / "v2_regime_pullback.py"
    strategy = load_strategy(strategy_path)

    contract = ContractSpec(symbol="BTC/USDT", leverage=2)
    account = AccountConfig(initial_capital=100.0)
    risk = RiskConfig(max_position_notional_pct=0.55, maintenance_margin_ratio=0.005)
    engine = FuturesBacktestEngine(contract, account, risk, timeframe="1h")
    df = engine.fetch_historical_data("2025-01-01", datetime.now().strftime("%Y-%m-%d"))
    signal_df = strategy.generate_signals(df)
    results = engine.simulate(signal_df)
    metrics = engine.calculate_metrics(results)
    print(
        json.dumps(
            {"version": version, "metrics": metrics}, indent=2, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
