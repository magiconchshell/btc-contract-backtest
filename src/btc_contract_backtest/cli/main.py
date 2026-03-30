import argparse
from datetime import datetime, timedelta

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, RiskConfig
from btc_contract_backtest.engine.futures_engine import FuturesBacktestEngine
from btc_contract_backtest.reporting.metrics import summarize_results
from btc_contract_backtest.strategies import build_strategy
from btc_contract_backtest.strategies.hybrid import VotingHybridStrategy
from btc_contract_backtest.live.paper_trading import PaperTradingSession
from btc_contract_backtest.strategies.hybrid import VotingHybridStrategy


def parse_args():
    p = argparse.ArgumentParser(description="Futures/perpetual contract backtest and paper trading toolkit")
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--days", type=int, default=180)
    p.add_argument("--leverage", type=int, default=5)
    p.add_argument("--capital", type=float, default=1000.0)
    p.add_argument("--strategy", default="rsi", choices=["rsi", "sma_cross", "macd", "hybrid"])
    p.add_argument("--paper-summary", action="store_true")
    p.add_argument("--paper-loop", action="store_true")
    p.add_argument("--interval", type=int, default=60)
    p.add_argument("--iterations", type=int, default=None)
    p.add_argument("--stop-loss-pct", type=float, default=None)
    p.add_argument("--take-profit-pct", type=float, default=None)
    p.add_argument("--trailing-stop-pct", type=float, default=None)
    p.add_argument("--max-holding-bars", type=int, default=None)
    return p.parse_args()


def main():
    args = parse_args()
    contract = ContractSpec(symbol=args.symbol, leverage=args.leverage)
    account = AccountConfig(initial_capital=args.capital)
    risk = RiskConfig(
        stop_loss_pct=args.stop_loss_pct,
        take_profit_pct=args.take_profit_pct,
        trailing_stop_pct=args.trailing_stop_pct,
        max_holding_bars=args.max_holding_bars,
    )

    if args.strategy == "hybrid":
        strategy = VotingHybridStrategy([build_strategy("rsi"), build_strategy("macd")], required_votes=1)
    else:
        strategy = build_strategy(args.strategy)

    if args.paper_summary:
        paper = PaperTradingSession(contract, account, risk, strategy, timeframe=args.timeframe)
        print(paper.summary())
        return

    if args.paper_loop:
        paper = PaperTradingSession(contract, account, risk, strategy, timeframe=args.timeframe)
        paper.run_loop(interval_seconds=args.interval, iterations=args.iterations)
        return

    engine = FuturesBacktestEngine(contract, account, risk, timeframe=args.timeframe)
    start = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")
    df = engine.fetch_historical_data(start, end)

    signal_df = strategy.generate_signals(df)
    results = engine.simulate(signal_df)
    metrics = engine.calculate_metrics(results)
    print(summarize_results(results, metrics))


if __name__ == "__main__":
    main()
