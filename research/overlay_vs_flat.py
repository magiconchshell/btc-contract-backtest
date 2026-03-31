#!/usr/bin/env python3
from __future__ import annotations

import json
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


def main():
    contract = ContractSpec(symbol="BTC/USDT", leverage=3)
    account = AccountConfig(initial_capital=1000.0)
    risk = RiskConfig(
        max_position_notional_pct=0.45,
        stop_loss_pct=0.015,
        take_profit_pct=0.03,
        max_holding_bars=48,
        atr_stop_mult=1.2,
        break_even_trigger_pct=0.015,
        risk_per_trade_pct=0.01,
        atr_position_sizing_mult=0.02,
        drawdown_position_scale=True,
        max_drawdown_scale_start_pct=8.0,
        max_drawdown_scale_floor=0.5,
    )
    engine = FuturesBacktestEngine(contract, account, risk, timeframe="1h")
    end_dt = datetime.now(UTC).replace(tzinfo=None)
    start_dt = end_dt - timedelta(days=365)
    df = engine.fetch_historical_data(
        start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")
    )

    candidates = [
        ("flat_baseline", None),
        (
            "extreme_downtrend_short",
            build_strategy(
                "extreme_downtrend_short",
                {"breakdown_lookback": 12, "adx_threshold": 20.0},
            ),
        ),
        (
            "short_overlay_switcher",
            build_strategy(
                "short_overlay_switcher",
                {
                    "crash_lookback": 16,
                    "crash_threshold_pct": 0.05,
                    "crash_adx_threshold": 24.0,
                    "allow_bull_long": False,
                },
            ),
        ),
    ]

    rows = []
    for name, strategy in candidates:
        if strategy is None:
            signal_df = df.copy()
            signal_df["signal"] = 0
            results = engine.simulate(signal_df)
        else:
            signal_df = strategy.generate_signals(df.copy())
            results = engine.simulate(signal_df)
        metrics = engine.calculate_metrics(results)
        rows.append(
            {
                "strategy": name,
                "signal_count": int((signal_df["signal"] != 0).sum()),
                **metrics,
            }
        )

    payload = {"generated_at": datetime.now(UTC).isoformat(), "rows": rows}
    (OUT_DIR / "overlay_vs_flat.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False)
    )
    lines = [
        "# Overlay vs Flat Baseline",
        "",
        "| strategy | return | dd | win rate | trades | final capital | signals |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['strategy']} | {row['total_return']:.2f}% | {row['max_drawdown']:.2f}% | {row['win_rate']:.2f}% | {row['total_trades']} | {row['final_capital']:.2f} | {row['signal_count']} |"
        )
    (OUT_DIR / "overlay_vs_flat.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
