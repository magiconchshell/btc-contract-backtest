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


def summarize_trades(signal_df, trades_df):
    if trades_df.empty:
        return {
            "all_trades": {"count": 0, "pnl_after_costs": 0.0},
            "long_module": {"count": 0, "pnl_after_costs": 0.0},
            "short_module": {"count": 0, "pnl_after_costs": 0.0},
            "flat": {"count": 0, "pnl_after_costs": 0.0},
        }

    source_map = signal_df["module_source"].to_dict() if "module_source" in signal_df.columns else {}
    rows = {"all_trades": [], "long_module": [], "short_module": [], "flat": []}
    for _, trade in trades_df.iterrows():
        entry_time = trade["entry_time"]
        source = source_map.get(entry_time, "flat")
        rows["all_trades"].append(trade)
        rows.setdefault(source, []).append(trade)

    out = {}
    for key, items in rows.items():
        pnl = sum(float(i["pnl_after_costs"]) for i in items) if items else 0.0
        out[key] = {"count": len(items), "pnl_after_costs": pnl}
    return out


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

    strategy = build_strategy("regime_switcher")
    signal_df = strategy.generate_signals(df.copy())
    results = engine.simulate(signal_df)
    metrics = engine.calculate_metrics(results)
    attribution = summarize_trades(signal_df, results["trades"])
    regime_counts = signal_df["regime_state"].value_counts(dropna=False).to_dict() if "regime_state" in signal_df.columns else {}

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "metrics": metrics,
        "regime_counts": regime_counts,
        "attribution": attribution,
    }
    (OUT_DIR / "module_attribution.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    lines = [
        "# Module Attribution",
        "",
        f"- total return: {metrics['total_return']:.2f}%",
        f"- max drawdown: {metrics['max_drawdown']:.2f}%",
        f"- win rate: {metrics['win_rate']:.2f}%",
        f"- total trades: {metrics['total_trades']}",
        "",
        "## Regime counts",
    ]
    for k, v in regime_counts.items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Module contribution")
    for key, val in attribution.items():
        lines.append(f"- {key}: trades={val['count']}, pnl_after_costs={val['pnl_after_costs']:.2f}")

    (OUT_DIR / "module_attribution.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
