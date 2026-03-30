import pandas as pd

from btc_contract_backtest.strategies.strong_bull_long import StrongBullLongStrategy


def sample_df():
    closes = [100 + i * 0.5 for i in range(420)]
    highs = [c + 1.2 for c in closes]
    lows = [c - 1.0 for c in closes]
    opens = [c - 0.1 for c in closes]
    vols = [12 + (i % 5) for i in range(420)]
    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols})


def test_strong_bull_long_has_signal_column():
    out = StrongBullLongStrategy().generate_signals(sample_df())
    assert "signal" in out.columns


def test_strong_bull_long_only_non_negative_signals():
    out = StrongBullLongStrategy().generate_signals(sample_df())
    assert (out["signal"] >= 0).all()
