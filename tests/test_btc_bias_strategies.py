import pandas as pd

from btc_contract_backtest.strategies.btc_bias import (
    ExtremeDowntrendShortStrategy,
    LongOnlyRegimeStrategy,
    ShortLiteRegimeStrategy,
)
from btc_contract_backtest.strategies.baselines import (
    BuyAndHoldLongStrategy,
    EMATrendStrategy,
)


def sample_df():
    closes = [100 + i * 0.4 for i in range(320)]
    highs = [c + 0.8 for c in closes]
    lows = [c - 0.8 for c in closes]
    opens = [c - 0.1 for c in closes]
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [10] * len(closes),
        }
    )


def test_long_only_regime_has_signal_column():
    out = LongOnlyRegimeStrategy().generate_signals(sample_df())
    assert "signal" in out.columns
    assert (out["signal"] >= 0).all()


def test_short_lite_regime_has_signal_column():
    out = ShortLiteRegimeStrategy().generate_signals(sample_df())
    assert "signal" in out.columns


def test_extreme_downtrend_short_has_signal_column():
    out = ExtremeDowntrendShortStrategy().generate_signals(sample_df())
    assert "signal" in out.columns


def test_buy_and_hold_long_has_signal_column():
    out = BuyAndHoldLongStrategy().generate_signals(sample_df())
    assert "signal" in out.columns
    assert int(out.iloc[0]["signal"]) == 1


def test_ema_trend_has_signal_column():
    out = EMATrendStrategy().generate_signals(sample_df())
    assert "signal" in out.columns
