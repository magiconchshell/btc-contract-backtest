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
    )
    engine = FuturesBacktestEngine(contract, account, risk, timeframe="1h")
    end_dt = datetime.now(UTC).replace(tzinfo=None)
    start_dt = end_dt - timedelta(days=365)
    df = engine.fetch_historical_data(start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"))

    candidates = [
        ("buy_and_hold_long", {}),
        ("ema_trend", {"fast_window": 50, "slow_window": 200}),
        ("long_only_regime", {}),
        ("short_lite_regime", {}),
        ("extreme_downtrend_short", {}),
        ("regime_filtered", {}),
        ("regime_asymmetric", {}),
    ]

    rows = []
    for name, config in candidates:
        strategy = build_strategy(name, config)
        signal_df = strategy.generate_signals(df.copy())
        results = engine.simulate(signal_df)
        metrics = engine.calculate_metrics(results)
        rows.append({
            "strategy": name,
            "signal_count": int((signal_df["signal"] != 0).sum()),
            **metrics,
        })

    rows.sort(key=lambda x: x["final_capital"], reverse=True)
    payload = {"generated_at": datetime.now(UTC).isoformat(), "rows": rows}
    (OUT_DIR / "baseline_comparison.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    lines = [
        "# Baseline Comparison",
        "",
        "| strategy | return | dd | win rate | trades | final capital | signals |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['strategy']} | {row['total_return']:.2f}% | {row['max_drawdown']:.2f}% | {row['win_rate']:.2f}% | {row['total_trades']} | {row['final_capital']:.2f} | {row['signal_count']} |"
        )
    (OUT_DIR / "baseline_comparison.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
