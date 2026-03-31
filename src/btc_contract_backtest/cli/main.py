import argparse
from datetime import datetime, timedelta

from btc_contract_backtest.config.models import (
    AccountConfig,
    ContractSpec,
    ExecutionConfig,
    LiveRiskConfig,
    RiskConfig,
)
from btc_contract_backtest.engine.futures_engine import FuturesBacktestEngine
from btc_contract_backtest.live.paper_trading import PaperTradingSession
from btc_contract_backtest.live.shadow_session import ShadowTradingSession
from btc_contract_backtest.reporting.metrics import summarize_results
from btc_contract_backtest.strategies import build_strategy
from btc_contract_backtest.strategies.hybrid import VotingHybridStrategy


def parse_args():
    p = argparse.ArgumentParser(
        description="Futures/perpetual contract backtest and paper trading toolkit"
    )
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--days", type=int, default=180)
    p.add_argument("--leverage", type=int, default=5)
    p.add_argument("--capital", type=float, default=1000.0)
    p.add_argument("--strategy", default="rsi", choices=[
        "rsi", "sma_cross", "macd", "hybrid", "regime_filtered", "regime_asymmetric",
        "buy_and_hold_long", "ema_trend", "long_only_regime", "short_lite_regime",
        "extreme_downtrend_short", "regime_switcher", "short_overlay_switcher",
        "strong_bull_long", "sparse_meta_portfolio",
    ])
    p.add_argument("--paper-summary", action="store_true")
    p.add_argument("--paper-loop", action="store_true")
    p.add_argument("--shadow-loop", action="store_true")
    p.add_argument("--shadow-audit-log", default="shadow_audit.jsonl")
    p.add_argument("--shadow-state-file", default="shadow_state.json")
    p.add_argument("--shadow-summary", action="store_true")
    p.add_argument("--shadow-review", action="store_true")
    p.add_argument("--interval", type=int, default=60)
    p.add_argument("--iterations", type=int, default=None)
    p.add_argument("--stop-loss-pct", type=float, default=None)
    p.add_argument("--take-profit-pct", type=float, default=None)
    p.add_argument("--trailing-stop-pct", type=float, default=None)
    p.add_argument("--max-holding-bars", type=int, default=None)
    p.add_argument("--atr-stop-mult", type=float, default=None)
    p.add_argument("--break-even-trigger-pct", type=float, default=None)
    p.add_argument("--partial-take-profit-pct", type=float, default=None)
    p.add_argument("--partial-close-ratio", type=float, default=0.5)
    p.add_argument("--stepped-trailing-stop-pct", type=float, default=None)
    p.add_argument("--risk-per-trade-pct", type=float, default=None)
    p.add_argument("--atr-position-sizing-mult", type=float, default=None)
    p.add_argument("--drawdown-position-scale", action="store_true")
    p.add_argument("--max-drawdown-scale-start-pct", type=float, default=10.0)
    p.add_argument("--max-drawdown-scale-floor", type=float, default=0.35)
    p.add_argument("--max-daily-loss-pct", type=float, default=None)
    p.add_argument("--max-symbol-exposure-pct", type=float, default=None)
    p.add_argument("--stale-data-threshold-seconds", type=int, default=120)
    p.add_argument("--disable-kill-on-stale-data", action="store_true")
    p.add_argument("--simulated-spread-bps", type=float, default=1.5)
    p.add_argument("--simulated-slippage-bps", type=float, default=2.0)
    p.add_argument("--max-fill-ratio-per-bar", type=float, default=1.0)
    p.add_argument("--disable-partial-fills", action="store_true")
    p.add_argument("--maker-fill-probability", type=float, default=0.35)
    p.add_argument("--latency-ms", type=int, default=150)
    p.add_argument("--queue-priority-model", default="probabilistic")
    p.add_argument("--use-realistic-funding", action="store_true")
    p.add_argument("--orderbook-depth-levels", type=int, default=5)
    p.add_argument("--simulated-depth-notional", type=float, default=250000.0)
    p.add_argument("--impact-exponent", type=float, default=0.6)
    p.add_argument("--disable-mark-bid-ask-consistency", action="store_true")
    p.add_argument("--stale-mark-deviation-bps", type=float, default=15.0)
    p.add_argument("--enable-kill-switch", action="store_true")
    p.add_argument("--max-consecutive-failures", type=int, default=5)
    p.add_argument("--heartbeat-timeout-seconds", type=int, default=180)
    return p.parse_args()


def main():
    args = parse_args()

    if args.shadow_summary:
        from pathlib import Path
        from research.shadow_audit_tools import load_jsonl, summarize, write_reports

        audit_path = Path(args.shadow_audit_log)
        rows = load_jsonl(audit_path)
        summary = summarize(rows)
        md, js = write_reports(audit_path, summary)
        print({"summary": summary, "markdown": str(md), "json": str(js)})
        return

    if args.shadow_review:
        from pathlib import Path
        from research.shadow_audit_tools import load_jsonl, summarize
        from research.shadow_review_report import build_review, write_review

        audit_path = Path(args.shadow_audit_log)
        rows = load_jsonl(audit_path)
        summary = summarize(rows)
        review = build_review(rows, summary)
        md, js = write_review(audit_path, review)
        print({"review": review, "markdown": str(md), "json": str(js)})
        return

    contract = ContractSpec(symbol=args.symbol, leverage=args.leverage)
    account = AccountConfig(initial_capital=args.capital)
    risk = RiskConfig(
        stop_loss_pct=args.stop_loss_pct,
        take_profit_pct=args.take_profit_pct,
        trailing_stop_pct=args.trailing_stop_pct,
        max_holding_bars=args.max_holding_bars,
        atr_stop_mult=args.atr_stop_mult,
        break_even_trigger_pct=args.break_even_trigger_pct,
        partial_take_profit_pct=args.partial_take_profit_pct,
        partial_close_ratio=args.partial_close_ratio,
        stepped_trailing_stop_pct=args.stepped_trailing_stop_pct,
        risk_per_trade_pct=args.risk_per_trade_pct,
        atr_position_sizing_mult=args.atr_position_sizing_mult,
        drawdown_position_scale=args.drawdown_position_scale,
        max_drawdown_scale_start_pct=args.max_drawdown_scale_start_pct,
        max_drawdown_scale_floor=args.max_drawdown_scale_floor,
        max_daily_loss_pct=args.max_daily_loss_pct,
        max_symbol_exposure_pct=args.max_symbol_exposure_pct,
        kill_on_stale_data=not args.disable_kill_on_stale_data,
        stale_data_threshold_seconds=args.stale_data_threshold_seconds,
    )
    execution = ExecutionConfig(
        simulated_spread_bps=args.simulated_spread_bps,
        simulated_slippage_bps=args.simulated_slippage_bps,
        max_fill_ratio_per_bar=args.max_fill_ratio_per_bar,
        allow_partial_fills=not args.disable_partial_fills,
        maker_fill_probability=args.maker_fill_probability,
        latency_ms=args.latency_ms,
        queue_priority_model=args.queue_priority_model,
        use_realistic_funding=args.use_realistic_funding,
        orderbook_depth_levels=args.orderbook_depth_levels,
        simulated_depth_notional=args.simulated_depth_notional,
        impact_exponent=args.impact_exponent,
        enforce_mark_bid_ask_consistency=not args.disable_mark_bid_ask_consistency,
        stale_mark_deviation_bps=args.stale_mark_deviation_bps,
    )
    live_risk = LiveRiskConfig(
        enable_kill_switch=args.enable_kill_switch,
        max_consecutive_failures=args.max_consecutive_failures,
        heartbeat_timeout_seconds=args.heartbeat_timeout_seconds,
    )

    if args.strategy == "hybrid":
        strategy = VotingHybridStrategy(
            [build_strategy("rsi"), build_strategy("macd")],
            required_votes=1,
        )
    else:
        strategy = build_strategy(args.strategy)

    if args.paper_summary:
        paper = PaperTradingSession(
            contract,
            account,
            risk,
            strategy,
            timeframe=args.timeframe,
            execution=execution,
            live_risk=live_risk,
        )
        print(paper.summary())
        return

    if args.paper_loop:
        paper = PaperTradingSession(
            contract,
            account,
            risk,
            strategy,
            timeframe=args.timeframe,
            execution=execution,
            live_risk=live_risk,
        )
        paper.run_loop(
            interval_seconds=args.interval,
            iterations=args.iterations,
        )
        return

    if args.shadow_loop:
        shadow = ShadowTradingSession(
            contract,
            account,
            risk,
            strategy,
            timeframe=args.timeframe,
            execution=execution,
            live_risk=live_risk,
            audit_log=args.shadow_audit_log,
            state_file=args.shadow_state_file,
        )
        shadow.run_loop(
            interval_seconds=args.interval,
            iterations=args.iterations,
        )
        return

    engine = FuturesBacktestEngine(
        contract,
        account,
        risk,
        timeframe=args.timeframe,
        execution=execution,
        live_risk=live_risk,
    )
    start = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")
    df = engine.fetch_historical_data(start, end)
    signal_df = strategy.generate_signals(df)
    results = engine.simulate(signal_df)
    metrics = engine.calculate_metrics(results)
    print(summarize_results(results, metrics))


if __name__ == "__main__":
    main()
