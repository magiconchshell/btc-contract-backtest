import pandas as pd

from btc_contract_backtest.strategies.regime_asymmetric import RegimeAsymmetricStrategy


def sample_df():
    closes = [100 + i * 0.5 for i in range(320)]
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]
    opens = [c - 0.2 for c in closes]
    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes, "volume": [10] * len(closes)})


def test_regime_asymmetric_has_signal_column():
    out = RegimeAsymmetricStrategy().generate_signals(sample_df())
    assert "signal" in out.columns


def test_regime_asymmetric_has_filter_columns():
    out = RegimeAsymmetricStrategy().generate_signals(sample_df())
    for col in ["ema_fast_trend", "ema_slow_trend", "atr", "atr_pct", "adx"]:
        assert col in out.columns
