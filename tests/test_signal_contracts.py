from btc_contract_backtest.strategies.indicators import (
    MACDCrossStrategy,
    RSIReversalStrategy,
    SMACrossStrategy,
)
import pandas as pd


def sample_df():
    prices = [100 + i for i in range(60)]
    return pd.DataFrame(
        {
            "close": prices,
            "open": prices,
            "high": prices,
            "low": prices,
            "volume": [1] * 60,
        }
    )


def test_rsi_has_signal_column():
    out = RSIReversalStrategy().generate_signals(sample_df())
    assert "signal" in out.columns


def test_macd_has_signal_column():
    out = MACDCrossStrategy().generate_signals(sample_df())
    assert "signal" in out.columns


def test_sma_has_signal_column():
    out = SMACrossStrategy().generate_signals(sample_df())
    assert "signal" in out.columns
