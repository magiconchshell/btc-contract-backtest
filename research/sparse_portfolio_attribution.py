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
    df = engine.fetch_historical_data(start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"))

    strategy = build_strategy("sparse_meta_portfolio")
    signal_df = strategy.generate_signals(df.copy())
    results = engine.simulate(signal_df)
    metrics = engine.calculate_metrics(results)

    occupancy = signal_df["module_source"].value_counts(dropna=False).to_dict() if "module_source" in signal_df.columns else {}
    regime_counts = signal_df["regime_state"].value_counts(dropna=False).to_dict() if "regime_state" in signal_df.columns else {}

    module_source_map = signal_df["module_source"].to_dict() if "module_source" in signal_df.columns else {}
    trade_buckets = {}
    for _, trade in results["trades"].iterrows():
        src = module_source_map.get(trade["entry_time"], "flat")
        bucket = trade_buckets.setdefault(src, {"count": 0, "pnl_after_costs": 0.0})
        bucket["count"] += 1
        bucket["pnl_after_costs"] += float(trade["pnl_after_costs"])

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "metrics": metrics,
        "occupancy": occupancy,
        "regime_counts": regime_counts,
        "trade_buckets": trade_buckets,
    }
    (OUT_DIR / "sparse_portfolio_attribution.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    lines = [
        "# Sparse Portfolio Attribution",
        "",
        f"- total return: {metrics['total_return']:.2f}%",
        f"- max drawdown: {metrics['max_drawdown']:.2f}%",
        f"- win rate: {metrics['win_rate']:.2f}%",
        f"- total trades: {metrics['total_trades']}",
        "",
        "## Occupancy",
    ]
    for k, v in occupancy.items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Regime counts")
    for k, v in regime_counts.items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Trade buckets")
    for k, v in trade_buckets.items():
        lines.append(f"- {k}: trades={v['count']}, pnl_after_costs={v['pnl_after_costs']:.2f}")

    (OUT_DIR / "sparse_portfolio_attribution.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
