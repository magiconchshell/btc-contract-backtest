#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2] / 'research' / 'strategy_lab'
REPO_ROOT = ROOT.parents[1]
SRC = REPO_ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, RiskConfig
from btc_contract_backtest.engine.futures_engine import FuturesBacktestEngine

ROOT = Path(__file__).resolve().parent


def load_strategy(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name in dir(mod):
        if name.startswith('V'):
            return getattr(mod, name)()
    raise RuntimeError('No strategy class found')


def main():
    version = 'v4'
    strategy = load_strategy(ROOT / 'strategies' / 'v4_breakout_pullback.py')

    contract = ContractSpec(symbol='BTC/USDT', leverage=2)
    account = AccountConfig(initial_capital=100.0)
    risk = RiskConfig(max_position_notional_pct=0.50, maintenance_margin_ratio=0.005)
    engine = FuturesBacktestEngine(contract, account, risk, timeframe='1h')
    df = engine.fetch_historical_data('2025-01-01', datetime.now().strftime('%Y-%m-%d'))
    signal_df = strategy.generate_signals(df)
    results = engine.simulate(signal_df)
    metrics = engine.calculate_metrics(results)

    success = (abs(metrics['max_drawdown']) <= 50 and metrics['total_return'] > 17.332897885674697)

    payload = {
        'version': version,
        'strategy': strategy.name,
        'goal': {
            'beat_v3_return': 17.332897885674697,
            'max_drawdown_lte': 50,
            'capital': 100,
            'leverage': 2,
            'start_date': '2025-01-01',
            'timeframe': '1h',
        },
        'metrics': metrics,
        'passed': success,
        'signal_count': int((signal_df['signal'] != 0).sum()),
    }

    (ROOT / 'reports' / 'v4_result.json').write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    (ROOT / 'reports' / 'v4_summary.md').write_text(
        f"# v4 summary\n\n"
        f"- strategy: {strategy.name}\n"
        f"- timeframe: 1h\n"
        f"- total return: {metrics['total_return']:.2f}%\n"
        f"- sharpe: {metrics['sharpe_ratio']:.2f}\n"
        f"- max drawdown: {metrics['max_drawdown']:.2f}%\n"
        f"- win rate: {metrics['win_rate']:.2f}%\n"
        f"- total trades: {metrics['total_trades']}\n"
        f"- final capital: {metrics['final_capital']:.2f}\n"
        f"- passed: {success}\n"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
