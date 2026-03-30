import pandas as pd

from btc_contract_backtest.strategies.regime_switcher import RegimeSwitcherStrategy


def sample_df():
    closes = [100 + i * 0.35 for i in range(360)]
    highs = [c + 0.9 for c in closes]
    lows = [c - 0.9 for c in closes]
    opens = [c - 0.1 for c in closes]
    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes, "volume": [10] * len(closes)})


def test_regime_switcher_has_signal_column():
    out = RegimeSwitcherStrategy().generate_signals(sample_df())
    assert "signal" in out.columns


def test_regime_switcher_has_regime_columns():
    out = RegimeSwitcherStrategy().generate_signals(sample_df())
    for col in ["regime_state", "module_source", "long_signal_raw", "short_signal_raw"]:
        assert col in out.columns
