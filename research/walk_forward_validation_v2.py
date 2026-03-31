#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, RiskConfig
from btc_contract_backtest.engine.futures_engine import FuturesBacktestEngine
from btc_contract_backtest.strategies import build_strategy

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TRAIN_DAYS = 120
TEST_DAYS = 30
FOLDS = 8

STRATEGY_CANDIDATES: list[tuple[str, dict[str, object]]] = [
    ("regime_filtered", {}),
    ("regime_asymmetric", {}),
    ("long_only_regime", {}),
    ("short_lite_regime", {}),
]

RISK_CANDIDATES = [
    RiskConfig(
        max_position_notional_pct=0.45,
        stop_loss_pct=0.02,
        take_profit_pct=0.03,
        max_holding_bars=48,
        atr_stop_mult=1.5,
        break_even_trigger_pct=0.015,
        risk_per_trade_pct=0.01,
        atr_position_sizing_mult=0.02,
        drawdown_position_scale=True,
        max_drawdown_scale_start_pct=8.0,
        max_drawdown_scale_floor=0.5,
    ),
    RiskConfig(
        max_position_notional_pct=0.40,
        stop_loss_pct=0.02,
        take_profit_pct=0.04,
        max_holding_bars=72,
        atr_stop_mult=1.5,
        break_even_trigger_pct=0.015,
        risk_per_trade_pct=0.008,
        atr_position_sizing_mult=0.018,
        drawdown_position_scale=True,
        max_drawdown_scale_start_pct=6.0,
        max_drawdown_scale_floor=0.45,
    ),
]


def score(metrics: dict) -> float:
    return (
        metrics["total_return"]
        + metrics["sharpe_ratio"] * 12
        - abs(metrics["max_drawdown"]) * 0.6
        + metrics["win_rate"] * 0.08
    )


def evaluate(df, strategy_name, strategy_config, risk, contract, account):
    strategy = build_strategy(strategy_name, strategy_config)
    signal_df = strategy.generate_signals(df.copy())
    engine = FuturesBacktestEngine(contract, account, risk, timeframe="1h")
    results = engine.simulate(signal_df)
    metrics = engine.calculate_metrics(results)
    return metrics


def main():
    import pandas as pd

    contract = ContractSpec(symbol="BTC/USDT", leverage=3)
    account = AccountConfig(initial_capital=1000.0)
    engine = FuturesBacktestEngine(contract, account, RiskConfig(), timeframe="1h")
    end_dt = datetime.now(UTC).replace(tzinfo=None)
    start_dt = end_dt - timedelta(days=(TRAIN_DAYS + TEST_DAYS) * FOLDS + 30)
    df = engine.fetch_historical_data(
        start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")
    )

    folds = []
    fold_start = start_dt
    for i in range(FOLDS):
        train_start = fold_start
        train_end = train_start + timedelta(days=TRAIN_DAYS)
        test_end = train_end + timedelta(days=TEST_DAYS)
        train_df = df[
            (df.index >= pd.Timestamp(train_start))
            & (df.index < pd.Timestamp(train_end))
        ]
        test_df = df[
            (df.index >= pd.Timestamp(train_end)) & (df.index < pd.Timestamp(test_end))
        ]

        best = None
        best_score = None
        for strategy_name, strategy_config in STRATEGY_CANDIDATES:
            for risk in RISK_CANDIDATES:
                train_metrics = evaluate(
                    train_df, strategy_name, strategy_config, risk, contract, account
                )
                train_score = score(train_metrics)
                if best is None or train_score > best_score:
                    best = (strategy_name, strategy_config, risk, train_metrics)
                    best_score = train_score

        strategy_name, strategy_config, risk, train_metrics = best
        test_metrics = evaluate(
            test_df, strategy_name, strategy_config, risk, contract, account
        )
        folds.append(
            {
                "fold": i + 1,
                "train_window": [train_start.isoformat(), train_end.isoformat()],
                "test_window": [train_end.isoformat(), test_end.isoformat()],
                "selected_strategy": strategy_name,
                "selected_strategy_config": strategy_config,
                "selected_risk": asdict(risk),
                "train_metrics": train_metrics,
                "test_metrics": test_metrics,
            }
        )
        fold_start = fold_start + timedelta(days=TEST_DAYS)

    avg_test_return = sum(f["test_metrics"]["total_return"] for f in folds) / len(folds)
    avg_test_dd = sum(f["test_metrics"]["max_drawdown"] for f in folds) / len(folds)
    profitable_tests = sum(1 for f in folds if f["test_metrics"]["total_return"] > 0)
    strategy_counts = {}
    for f in folds:
        strategy_counts[f["selected_strategy"]] = (
            strategy_counts.get(f["selected_strategy"], 0) + 1
        )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "folds": len(folds),
            "avg_test_return": avg_test_return,
            "avg_test_drawdown": avg_test_dd,
            "profitable_test_folds": profitable_tests,
            "overfit_warning": profitable_tests < max(3, len(folds) // 2),
            "strategy_selection_counts": strategy_counts,
        },
        "folds": folds,
    }

    (OUT_DIR / "walk_forward_validation_v2.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False)
    )

    lines = [
        "# Walk-Forward Validation v2",
        "",
        f"- folds: {payload['summary']['folds']}",
        f"- avg test return: {payload['summary']['avg_test_return']:.2f}%",
        f"- avg test drawdown: {payload['summary']['avg_test_drawdown']:.2f}%",
        f"- profitable test folds: {payload['summary']['profitable_test_folds']}/{payload['summary']['folds']}",
        f"- overfit warning: {payload['summary']['overfit_warning']}",
        f"- strategy selection counts: {payload['summary']['strategy_selection_counts']}",
        "",
        "| fold | strategy | test return | test dd | test win rate | trades |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for f in folds:
        tm = f["test_metrics"]
        lines.append(
            f"| {f['fold']} | {f['selected_strategy']} | {tm['total_return']:.2f}% | {tm['max_drawdown']:.2f}% | {tm['win_rate']:.2f}% | {tm['total_trades']} |"
        )

    (OUT_DIR / "walk_forward_validation_v2.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print("\n".join(lines))


if __name__ == "__main__":
    main()
