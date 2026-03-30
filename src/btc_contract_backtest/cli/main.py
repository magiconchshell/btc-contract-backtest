import argparse
from datetime import datetime, timedelta

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, RiskConfig
from btc_contract_backtest.engine.futures_engine import FuturesBacktestEngine
from btc_contract_backtest.reporting.metrics import summarize_results
from btc_contract_backtest.strategies import build_strategy
from btc_contract_backtest.strategies.hybrid import VotingHybridStrategy
from btc_contract_backtest.live.paper_trading import PaperTradingSession


def parse_args():
    p = argparse.ArgumentParser(description="Futures/perpetual contract backtest and paper trading toolkit")
    p.add_argument("--symbol", default="BTC/USDT")
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--days", type=int, default=180)
    p.add_argument("--leverage", type=int, default=5)
    p.add_argument("--capital", type=float, default=1000.0)
    p.add_argument("--strategy", default="rsi", choices=["rsi", "sma_cross", "macd", "hybrid"])
    p.add_argument("--paper-summary", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    contract = ContractSpec(symbol=args.symbol, leverage=args.leverage)
    account = AccountConfig(initial_capital=args.capital)
    risk = RiskConfig()

    if args.paper_summary:
        paper = PaperTradingSession(contract, account, timeframe=args.timeframe)
        print(paper.summary())
        return

    engine = FuturesBacktestEngine(contract, account, risk, timeframe=args.timeframe)
    start = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")
    df = engine.fetch_historical_data(start, end)

    if args.strategy == "hybrid":
        strategy = VotingHybridStrategy([build_strategy("rsi"), build_strategy("macd")], required_votes=1)
    else:
        strategy = build_strategy(args.strategy)
    signal_df = strategy.generate_signals(df)
    results = engine.simulate(signal_df)
    metrics = engine.calculate_metrics(results)
    print(summarize_results(results, metrics))


if __name__ == "__main__":
    main()
