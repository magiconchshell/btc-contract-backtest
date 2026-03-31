#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timedelta
from itertools import product
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, RiskConfig
from btc_contract_backtest.engine.futures_engine import FuturesBacktestEngine
from btc_contract_backtest.strategies import build_strategy

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "reports"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def score_row(row: dict) -> float:
    return (
        row["final_capital"]
        + row["total_return"] * 2.0
        + row["win_rate"] * 0.5
        + row["sharpe_ratio"] * 50.0
        - abs(row["max_drawdown"]) * 1.2
        - row["liquidation_events"] * 100.0
    )


def main():
    contract = ContractSpec(symbol="BTC/USDT", leverage=3)
    account = AccountConfig(initial_capital=1000.0)
    base_engine = FuturesBacktestEngine(contract, account, RiskConfig(), timeframe="1h")
    start = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")
    df = base_engine.fetch_historical_data(start, end)

    strategy_configs = [
        ("hybrid", {}),
        ("regime_filtered", {}),
        (
            "regime_filtered",
            {"adx_threshold": 20.0, "min_atr_pct": 0.004, "max_atr_pct": 0.03},
        ),
        (
            "regime_filtered",
            {
                "fast_trend_window": 30,
                "slow_trend_window": 120,
                "adx_threshold": 22.0,
                "rsi_long_threshold": 40.0,
                "rsi_short_threshold": 60.0,
            },
        ),
    ]

    exit_grid = list(
        product(
            [0.02, 0.03],
            [0.03, 0.05],
            [24, 48],
            [1.5, 2.0],
            [0.015, 0.02],
            [0.02, None],
            [0.015, None],
        )
    )

    rows = []
    for strategy_name, strategy_config in strategy_configs:
        strategy = build_strategy(strategy_name, strategy_config)
        signal_df = strategy.generate_signals(df)
        signal_count = int((signal_df["signal"] != 0).sum())
        for (
            stop_loss,
            take_profit,
            max_holding,
            atr_mult,
            break_even,
            partial_tp,
            stepped_trail,
        ) in exit_grid:
            risk = RiskConfig(
                max_position_notional_pct=0.45,
                stop_loss_pct=stop_loss,
                take_profit_pct=take_profit,
                max_holding_bars=max_holding,
                atr_stop_mult=atr_mult,
                break_even_trigger_pct=break_even,
                partial_take_profit_pct=partial_tp,
                partial_close_ratio=0.5,
                stepped_trailing_stop_pct=stepped_trail,
                maintenance_margin_ratio=0.005,
            )
            engine = FuturesBacktestEngine(contract, account, risk, timeframe="1h")
            results = engine.simulate(signal_df)
            metrics = engine.calculate_metrics(results)
            row = {
                "strategy": strategy_name,
                "strategy_config": strategy_config,
                "signal_count": signal_count,
                "stop_loss_pct": stop_loss,
                "take_profit_pct": take_profit,
                "max_holding_bars": max_holding,
                "atr_stop_mult": atr_mult,
                "break_even_trigger_pct": break_even,
                "partial_take_profit_pct": partial_tp,
                "stepped_trailing_stop_pct": stepped_trail,
                **metrics,
            }
            row["score"] = score_row(row)
            rows.append(row)

    rows.sort(key=lambda x: x["score"], reverse=True)
    top_rows = rows[:20]

    (OUT_DIR / "systematic_exit_search.json").write_text(
        json.dumps(
            {"generated_at": datetime.utcnow().isoformat(), "top": top_rows},
            indent=2,
            ensure_ascii=False,
        )
    )

    lines = [
        "# Systematic Exit Search Results",
        "",
        "| rank | strategy | return | dd | win rate | trades | final capital | score | stop | tp | max bars | atr | breakeven | partial tp | stepped trail |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for i, row in enumerate(top_rows, start=1):
        lines.append(
            f"| {i} | {row['strategy']} | {row['total_return']:.2f}% | {row['max_drawdown']:.2f}% | {row['win_rate']:.2f}% | {row['total_trades']} | {row['final_capital']:.2f} | {row['score']:.2f} | {row['stop_loss_pct']} | {row['take_profit_pct']} | {row['max_holding_bars']} | {row['atr_stop_mult']} | {row['break_even_trigger_pct']} | {row['partial_take_profit_pct']} | {row['stepped_trailing_stop_pct']} |"
        )

    (OUT_DIR / "systematic_exit_search.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )
    print("\n".join(lines[:15]))


if __name__ == "__main__":
    main()
