import pandas as pd

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, ExecutionConfig, RiskConfig
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


def make_df(closes):
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="h")
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1] * len(closes),
            "atr": [1.0] * len(closes),
        },
        index=idx,
    )


def test_backtest_and_paper_can_share_core_logic(tmp_path, monkeypatch):
    closes = [100, 101, 102, 103, 100]
    signals = [1, 1, 1, 1, 0]
    df = make_df(closes)
    strategy = StaticStrategy(signals)

    engine = FuturesBacktestEngine(
        contract=ContractSpec(symbol="BTC/USDT", leverage=3),
        account=AccountConfig(initial_capital=1000.0),
        risk=RiskConfig(stop_loss_pct=0.05, take_profit_pct=0.05),
        execution=ExecutionConfig(allow_partial_fills=False),
        timeframe="1h",
    )
    bt = engine.simulate(strategy.generate_signals(df))

    paper = PaperTradingSession(
        contract=ContractSpec(symbol="BTC/USDT", leverage=3),
        account=AccountConfig(initial_capital=1000.0),
        risk=RiskConfig(stop_loss_pct=0.05, take_profit_pct=0.05),
        strategy=strategy,
        execution=ExecutionConfig(allow_partial_fills=False),
        timeframe="1h",
        state_file=str(tmp_path / "paper_state.json"),
    )

    seq = [strategy.generate_signals(df.iloc[: i + 1]) for i in range(len(df))]
    base = df.copy()
    monkeypatch.setattr(paper, "fetch_recent_data", lambda limit=300: base)
    monkeypatch.setattr(paper, "mark_price", lambda: float(base.iloc[-1]["close"]))

    for i in range(len(df)):
        snap = base.iloc[: i + 1].copy()
        monkeypatch.setattr(paper, "fetch_recent_data", lambda limit=300, snap=snap: snap)
        paper.step()

    assert paper.core.position.side in {0, 1}
    assert bt["final_capital"] > 0
    assert paper.core.capital > 0
