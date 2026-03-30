#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
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


def score(row: dict) -> float:
    return row["final_capital"] + row["total_return"] * 2 - abs(row["max_drawdown"]) + row["win_rate"] * 0.25


def main():
    contract = ContractSpec(symbol="BTC/USDT", leverage=3)
    account = AccountConfig(initial_capital=1000.0)
    base_engine = FuturesBacktestEngine(contract, account, RiskConfig(), timeframe="1h")
    end_dt = datetime.now(UTC).replace(tzinfo=None)
    start_dt = end_dt - timedelta(days=365)
    df = base_engine.fetch_historical_data(start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"))

    rows = []
    for breakdown_lookback, adx_threshold, stop_loss, take_profit, max_bars, atr_mult in product(
        [12, 16, 20],
        [20.0, 24.0, 28.0],
        [0.015, 0.02],
        [0.02, 0.03],
        [24, 48],
        [1.2, 1.5],
    ):
        strategy = build_strategy("extreme_downtrend_short", {
            "breakdown_lookback": breakdown_lookback,
            "adx_threshold": adx_threshold,
        })
        signal_df = strategy.generate_signals(df.copy())
        risk = RiskConfig(
            max_position_notional_pct=0.45,
            stop_loss_pct=stop_loss,
            take_profit_pct=take_profit,
            max_holding_bars=max_bars,
            atr_stop_mult=atr_mult,
            break_even_trigger_pct=0.015,
            risk_per_trade_pct=0.01,
            atr_position_sizing_mult=0.02,
            drawdown_position_scale=True,
            max_drawdown_scale_start_pct=8.0,
            max_drawdown_scale_floor=0.5,
        )
        engine = FuturesBacktestEngine(contract, account, risk, timeframe="1h")
        results = engine.simulate(signal_df)
        metrics = engine.calculate_metrics(results)
        row = {
            "strategy": "extreme_downtrend_short",
            "breakdown_lookback": breakdown_lookback,
            "adx_threshold": adx_threshold,
            "stop_loss_pct": stop_loss,
            "take_profit_pct": take_profit,
            "max_holding_bars": max_bars,
            "atr_stop_mult": atr_mult,
            "signal_count": int((signal_df["signal"] != 0).sum()),
            **metrics,
        }
        row["score"] = score(row)
        rows.append(row)

    rows.sort(key=lambda x: x["score"], reverse=True)
    top = rows[:20]
    payload = {"generated_at": datetime.now(UTC).isoformat(), "top": top}
    (OUT_DIR / "short_overlay_search.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    lines = [
        "# Short Overlay Search",
        "",
        "| rank | return | dd | win rate | trades | final capital | lookback | adx | stop | tp | max bars | atr | signals |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for i, row in enumerate(top, start=1):
        lines.append(
            f"| {i} | {row['total_return']:.2f}% | {row['max_drawdown']:.2f}% | {row['win_rate']:.2f}% | {row['total_trades']} | {row['final_capital']:.2f} | {row['breakdown_lookback']} | {row['adx_threshold']} | {row['stop_loss_pct']} | {row['take_profit_pct']} | {row['max_holding_bars']} | {row['atr_stop_mult']} | {row['signal_count']} |"
        )
    (OUT_DIR / "short_overlay_search.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:15]))


if __name__ == "__main__":
    main()
