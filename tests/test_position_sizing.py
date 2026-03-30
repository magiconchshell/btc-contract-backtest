import pandas as pd

from btc_contract_backtest.config.models import AccountConfig, ContractSpec, RiskConfig
from btc_contract_backtest.engine.futures_engine import FuturesBacktestEngine


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


def test_risk_per_trade_position_sizing_limits_loss():
    engine = FuturesBacktestEngine(
        contract=ContractSpec(symbol="BTC/USDT", leverage=5),
        account=AccountConfig(initial_capital=1000.0),
        risk=RiskConfig(
            max_position_notional_pct=0.95,
            stop_loss_pct=0.02,
            risk_per_trade_pct=0.01,
        ),
        timeframe="1h",
    )
    df = make_df([100, 100, 97], [1, 1, 1], atr_values=[1.0, 1.0, 1.0])
    results = engine.simulate(df)
    first_trade = results["trades"].iloc[0]
    assert first_trade["notional_closed"] <= 100.1


def test_drawdown_scale_reduces_future_position_size():
    engine = FuturesBacktestEngine(
        contract=ContractSpec(symbol="BTC/USDT", leverage=5),
        account=AccountConfig(initial_capital=1000.0),
        risk=RiskConfig(
            max_position_notional_pct=0.95,
            stop_loss_pct=0.02,
            risk_per_trade_pct=0.02,
            drawdown_position_scale=True,
            max_drawdown_scale_start_pct=1.0,
            max_drawdown_scale_floor=0.5,
        ),
        timeframe="1h",
    )
    df = make_df([100, 100, 97, 97, 97, 100], [1, 1, 1, 1, -1, -1], atr_values=[1.0] * 6)
    results = engine.simulate(df)
    assert len(results["trades"]) >= 2
    first_full = results["trades"].iloc[0]["notional_closed"]
    second_full = results["trades"].iloc[-1]["notional_closed"]
    assert second_full <= first_full
