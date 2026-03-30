import pandas as pd

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, RiskConfig
from btc_contract_backtest.engine.futures_engine import FuturesBacktestEngine


def make_engine(risk: RiskConfig):
    return FuturesBacktestEngine(
        contract=ContractSpec(symbol="BTC/USDT", leverage=5),
        account=AccountConfig(initial_capital=1000.0),
        risk=risk,
        timeframe="1h",
    )


def make_df(closes, signals, atr_values=None):
    idx = pd.date_range("2026-01-01", periods=len(closes), freq="h")
    df = pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1] * len(closes),
            "signal": signals,
        },
        index=idx,
    )
    if atr_values is not None:
        df["atr"] = atr_values
    return df


def test_stop_loss_exit_reason():
    engine = make_engine(RiskConfig(max_position_notional_pct=0.5, stop_loss_pct=0.02))
    df = make_df([100, 100, 97], [1, 1, 1])
    results = engine.simulate(df)
    assert not results["trades"].empty
    assert results["trades"].iloc[0]["reason"] == "stop_loss"


def test_take_profit_exit_reason():
    engine = make_engine(RiskConfig(max_position_notional_pct=0.5, take_profit_pct=0.03))
    df = make_df([100, 100, 104], [1, 1, 1])
    results = engine.simulate(df)
    assert not results["trades"].empty
    assert results["trades"].iloc[0]["reason"] == "take_profit"


def test_trailing_stop_exit_reason():
    engine = make_engine(RiskConfig(max_position_notional_pct=0.5, trailing_stop_pct=0.02))
    df = make_df([100, 103, 100.5], [1, 1, 1])
    results = engine.simulate(df)
    assert not results["trades"].empty
    assert results["trades"].iloc[0]["reason"] == "trailing_stop"


def test_time_exit_reason():
    engine = make_engine(RiskConfig(max_position_notional_pct=0.5, max_holding_bars=2))
    df = make_df([100, 101, 102, 103], [1, 1, 1, 1])
    results = engine.simulate(df)
    assert not results["trades"].empty
    assert results["trades"].iloc[0]["reason"] == "time_exit"


def test_atr_stop_exit_reason():
    engine = make_engine(RiskConfig(max_position_notional_pct=0.5, atr_stop_mult=2.0))
    df = make_df([100, 100, 97], [1, 1, 1], atr_values=[1.0, 1.0, 1.0])
    results = engine.simulate(df)
    assert not results["trades"].empty
    assert results["trades"].iloc[0]["reason"] == "atr_stop"


def test_partial_take_profit_and_final_exit():
    engine = make_engine(RiskConfig(max_position_notional_pct=0.5, partial_take_profit_pct=0.02, partial_close_ratio=0.5, take_profit_pct=0.04))
    df = make_df([100, 102, 104], [1, 1, 1], atr_values=[1.0, 1.0, 1.0])
    results = engine.simulate(df)
    assert len(results["trades"]) >= 2
    assert results["trades"].iloc[0]["reason"] == "partial_take_profit"
    assert bool(results["trades"].iloc[0]["is_partial"]) is True


def test_break_even_stop_exit_reason():
    engine = make_engine(RiskConfig(max_position_notional_pct=0.5, break_even_trigger_pct=0.02))
    df = make_df([100, 103, 100], [1, 1, 1], atr_values=[1.0, 1.0, 1.0])
    results = engine.simulate(df)
    assert not results["trades"].empty
    assert results["trades"].iloc[-1]["reason"] == "break_even_stop"


def test_stepped_trailing_stop_exit_reason():
    engine = make_engine(RiskConfig(max_position_notional_pct=0.5, stepped_trailing_stop_pct=0.02))
    df = make_df([100, 104, 101.5], [1, 1, 1], atr_values=[1.0, 1.0, 1.0])
    results = engine.simulate(df)
    assert not results["trades"].empty
    assert results["trades"].iloc[-1]["reason"] == "stepped_trailing_stop"
