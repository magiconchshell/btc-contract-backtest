import pandas as pd

from btc_contract_backtest.config.models import (
    AccountConfig,
    ContractSpec,
    ExecutionConfig,
    RiskConfig,
)
from btc_contract_backtest.runtime.backtest_runtime import BacktestRuntime
from btc_contract_backtest.runtime.runtime_persistence import InMemoryRuntimePersistence
from btc_contract_backtest.strategies.base import BaseStrategy


class SequenceStrategy(BaseStrategy):
    def __init__(self, signals):
        self.signals = signals

    def name(self) -> str:
        return "sequence"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        out["signal"] = self.signals[: len(out)]
        out["atr"] = 1.0
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
        },
        index=idx,
    )


def test_backtest_runtime_runs_shared_lifecycle_and_records_steps():
    persistence = InMemoryRuntimePersistence()
    runtime = BacktestRuntime(
        market_data=make_df([100, 101, 102, 100]),
        contract=ContractSpec(symbol="BTC/USDT", leverage=3),
        account=AccountConfig(initial_capital=1000.0),
        risk=RiskConfig(stop_loss_pct=0.05, take_profit_pct=0.05),
        strategy=SequenceStrategy([1, 1, -1, 0]),
        timeframe="1h",
        execution=ExecutionConfig(allow_partial_fills=False),
    )
    runtime.persistence = persistence

    result = runtime.run()

    assert not result["equity_curve"].empty
    assert len(persistence.steps) >= len(runtime.market_data)
    events = {step.event for step in persistence.steps}
    assert events & {"decision", "open", "reverse", "hold"}
    assert result["final_capital"] > 0


def test_backtest_runtime_records_risk_events_through_shared_persistence():
    persistence = InMemoryRuntimePersistence()
    df = make_df([100, 100])
    df["stale"] = True
    runtime = BacktestRuntime(
        market_data=df,
        contract=ContractSpec(symbol="BTC/USDT", leverage=3),
        account=AccountConfig(initial_capital=1000.0),
        risk=RiskConfig(kill_on_stale_data=True),
        strategy=SequenceStrategy([1, 1]),
        timeframe="1h",
        execution=ExecutionConfig(allow_partial_fills=False),
    )
    runtime.persistence = persistence

    runtime.step()

    assert persistence.risk_events
    assert persistence.risk_events[-1]["event_type"] == "stale_data"
