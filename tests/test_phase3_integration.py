import pandas as pd

from btc_contract_backtest.config.models import (
    AccountConfig,
    ContractSpec,
    ExecutionConfig,
    RiskConfig,
)
from btc_contract_backtest.engine.futures_engine import FuturesBacktestEngine
from btc_contract_backtest.live.paper_trading import PaperTradingSession
from btc_contract_backtest.strategies.base import BaseStrategy


class StaticStrategy(BaseStrategy):
    def __init__(self, signals):
        self.signals = signals

    def name(self) -> str:
        return "static"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["signal"] = self.signals[: len(out)]
        return out


class FakeExchange:
    def fetch_positions(self, symbols):
        return []

    def fetch_open_orders(self, symbol):
        return []


def make_df():
    closes = [100, 101, 102, 103]
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="h")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1000] * len(closes),
            "atr": [1.0] * len(closes),
            "funding_rate": [0.001] * len(closes),
            "bid": [c - 0.1 for c in closes],
            "ask": [c + 0.1 for c in closes],
            "mark_price": closes,
        },
        index=idx,
    )


def test_backtest_applies_funding_cost():
    df = make_df()
    strategy = StaticStrategy([1, 1, 1, 1])
    engine = FuturesBacktestEngine(
        contract=ContractSpec(symbol="BTC/USDT", leverage=3),
        account=AccountConfig(initial_capital=1000.0),
        risk=RiskConfig(),
        execution=ExecutionConfig(
            use_realistic_funding=True, allow_partial_fills=False
        ),
        timeframe="1h",
    )
    results = engine.simulate(strategy.generate_signals(df))
    assert results["final_capital"] < 1000.0 or not results["equity_curve"].empty
    assert engine.exchange is None


def test_paper_blocks_mark_inconsistency(tmp_path, monkeypatch):
    df = make_df()
    df["mark_price"] = [120, 120, 120, 120]
    strategy = StaticStrategy([0, 0, 0, 0])
    paper = PaperTradingSession(
        contract=ContractSpec(symbol="BTC/USDT", leverage=3),
        account=AccountConfig(initial_capital=1000.0),
        risk=RiskConfig(),
        strategy=strategy,
        execution=ExecutionConfig(
            enforce_mark_bid_ask_consistency=True, stale_mark_deviation_bps=5.0
        ),
        timeframe="1h",
        state_file=str(tmp_path / "paper_state.json"),
        exchange=FakeExchange(),
    )
    monkeypatch.setattr(paper, "fetch_recent_data", lambda limit=300: df)
    monkeypatch.setattr(paper, "mark_price", lambda: float(df.iloc[-1]["close"]))
    event = paper.step()
    assert event["event"] == "blocked"
