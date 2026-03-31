from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from btc_contract_backtest.config.models import (
    AccountConfig,
    ContractSpec,
    ExecutionConfig,
    LiveRiskConfig,
    RiskConfig,
)
from btc_contract_backtest.engine.futures_engine import FuturesBacktestEngine
from btc_contract_backtest.reporting.html_report import write_report
from btc_contract_backtest.strategies import build_strategy


def main():
    symbol = "BTC/USDT"
    timeframe = "1h"
    start = "2025-01-01"
    end = datetime.now().strftime("%Y-%m-%d")

    contract = ContractSpec(symbol=symbol, leverage=5)
    account = AccountConfig(initial_capital=100.0)
    execution = ExecutionConfig(
        allow_partial_fills=True,
        queue_priority_model="probabilistic",
        use_realistic_funding=True,
        calibration_mode="calibrated",
        calibration_version="t4-v1",
    )
    live_risk = LiveRiskConfig()

    engine_base = FuturesBacktestEngine(
        contract,
        account,
        RiskConfig(),
        timeframe=timeframe,
        execution=execution,
        live_risk=live_risk,
    )
    df = engine_base.fetch_historical_data(start, end)

    candidates = [
        {
            "name": "short_overlay_switcher_best",
            "strategy": build_strategy(
                "short_overlay_switcher",
                {
                    "fast_ema": 50,
                    "slow_ema": 200,
                    "crash_lookback": 16,
                    "crash_threshold_pct": 0.05,
                    "crash_adx_threshold": 28.0,
                    "allow_bull_long": False,
                },
            ),
            "risk": RiskConfig(
                max_position_notional_pct=0.45,
                stop_loss_pct=0.015,
                take_profit_pct=0.03,
                max_holding_bars=48,
                atr_stop_mult=1.5,
                break_even_trigger_pct=0.015,
                risk_per_trade_pct=0.01,
                atr_position_sizing_mult=0.02,
                drawdown_position_scale=True,
                max_drawdown_scale_start_pct=8.0,
                max_drawdown_scale_floor=0.5,
                max_daily_loss_pct=8.0,
                max_symbol_exposure_pct=0.45,
            ),
        },
        {
            "name": "extreme_downtrend_short_best",
            "strategy": build_strategy(
                "extreme_downtrend_short",
                {
                    "ema_fast": 50,
                    "ema_slow": 200,
                    "breakdown_lookback": 16,
                    "adx_threshold": 28.0,
                },
            ),
            "risk": RiskConfig(
                max_position_notional_pct=0.45,
                stop_loss_pct=0.015,
                take_profit_pct=0.03,
                max_holding_bars=48,
                atr_stop_mult=1.5,
                break_even_trigger_pct=0.015,
                risk_per_trade_pct=0.01,
                atr_position_sizing_mult=0.02,
                drawdown_position_scale=True,
                max_drawdown_scale_start_pct=8.0,
                max_drawdown_scale_floor=0.5,
                max_daily_loss_pct=8.0,
                max_symbol_exposure_pct=0.45,
            ),
        },
    ]

    strategies_payload = []
    raw_dir = ROOT / "reports" / "best_strategy_run"
    raw_dir.mkdir(parents=True, exist_ok=True)

    for item in candidates:
        engine = FuturesBacktestEngine(
            contract,
            account,
            item["risk"],
            timeframe=timeframe,
            execution=execution,
            live_risk=live_risk,
        )
        signal_df = item["strategy"].generate_signals(df.copy())
        results = engine.simulate(signal_df)
        metrics = engine.calculate_metrics(results)
        eq = results["equity_curve"].copy()
        eq["timestamp"] = eq["timestamp"].astype(str)
        strategies_payload.append(
            {
                "name": item["name"],
                "metrics": metrics,
                "equity_curve": eq[["timestamp", "equity"]].to_dict(orient="records"),
            }
        )
        (raw_dir / f"{item['name']}_metrics.json").write_text(
            json.dumps(metrics, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        results["trades"].to_csv(raw_dir / f"{item['name']}_trades.csv", index=False)
        eq.to_csv(raw_dir / f"{item['name']}_equity.csv", index=False)

    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "strategies": strategies_payload,
        "meta": {
            "symbol": symbol,
            "timeframe": timeframe,
            "start": start,
            "end": end,
            "initial_capital": 100.0,
            "leverage": 5,
            "calibration_mode": execution.calibration_mode,
            "calibration_version": execution.calibration_version,
        },
    }

    out_html = raw_dir / "index.html"
    write_report(out_html, payload)
    print(
        json.dumps({"report": str(out_html), "dir": str(raw_dir)}, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
