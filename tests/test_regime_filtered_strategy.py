import pandas as pd

from btc_contract_backtest.strategies.regime_filtered import RegimeFilteredStrategy


def sample_df():
    closes = [100 + i * 0.6 for i in range(260)]
    highs = [c + 0.8 for c in closes]
    lows = [c - 0.8 for c in closes]
    opens = [c - 0.2 for c in closes]
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [10] * len(closes),
        }
    )


def test_regime_filtered_has_signal_column():
    out = RegimeFilteredStrategy().generate_signals(sample_df())
    assert "signal" in out.columns


def test_regime_filtered_has_indicator_columns():
    out = RegimeFilteredStrategy().generate_signals(sample_df())
    for col in ["ema_fast_trend", "ema_slow_trend", "atr", "atr_pct", "adx"]:
        assert col in out.columns
