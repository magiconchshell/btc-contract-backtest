from btc_contract_backtest.config.models import (
    AccountConfig,
    ContractSpec,
    ExecutionConfig,
    RiskConfig,
)
from btc_contract_backtest.live.paper_trading import PaperTradingSession
from btc_contract_backtest.strategies.base import BaseStrategy


class FixedSignalStrategy(BaseStrategy):
    def name(self) -> str:
        return "fixed"

    def generate_signals(self, df):
        out = df.copy()
        out["signal"] = 1
        out["atr"] = 1.0
        return out


class FakeExchange:
    def fetch_ohlcv(self, symbol, timeframe="1h", limit=300):
        return [[1, 100, 101, 99, 100, 10], [2, 100, 102, 99, 101, 12]]

    def fetch_ticker(self, symbol):
        return {"last": 101.0, "bid": 100.95, "ask": 101.05}

    def fetch_positions(self, symbols):
        return []

    def fetch_open_orders(self, symbol):
        return []


def test_paper_backtest_parity(monkeypatch, tmp_path):
    strategy = FixedSignalStrategy()
    paper = PaperTradingSession(
        contract=ContractSpec(symbol="BTC/USDT", leverage=3),
        account=AccountConfig(initial_capital=1000.0),
        risk=RiskConfig(stop_loss_pct=0.05, take_profit_pct=0.05),
        strategy=strategy,
        execution=ExecutionConfig(allow_partial_fills=False),
        timeframe="1h",
        state_file=str(tmp_path / "paper_state.json"),
        exchange=FakeExchange(),
    )

    [strategy.generate_signals for _ in range(1)]
    base = paper.fetch_recent_data(limit=300)
    monkeypatch.setattr(paper, "fetch_recent_data", lambda limit=300: base)
    monkeypatch.setattr(paper, "mark_price", lambda: float(base.iloc[-1]["close"]))

    for i in range(len(base)):
        snap = base.iloc[: i + 1].copy()
        monkeypatch.setattr(
            paper, "fetch_recent_data", lambda limit=300, snap=snap: snap
        )
        paper.step()
