import pandas as pd

from btc_contract_backtest.strategies.short_overlay_switcher import ShortOverlaySwitcherStrategy


def sample_df():
    closes = [100 + i * 0.3 for i in range(360)]
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]
    opens = [c - 0.1 for c in closes]
    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes, "volume": [10] * len(closes)})


def test_short_overlay_switcher_has_signal_column():
    out = ShortOverlaySwitcherStrategy().generate_signals(sample_df())
    assert "signal" in out.columns


def test_short_overlay_switcher_has_state_columns():
    out = ShortOverlaySwitcherStrategy().generate_signals(sample_df())
    for col in ["regime_state", "module_source", "short_signal_raw"]:
        assert col in out.columns
