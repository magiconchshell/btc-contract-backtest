import pandas as pd

from btc_contract_backtest.strategies.sparse_portfolio import SparseMetaPortfolioStrategy


def sample_df():
    closes = [100 + i * 0.25 for i in range(420)]
    highs = [c + 1.0 for c in closes]
    lows = [c - 1.0 for c in closes]
    opens = [c - 0.1 for c in closes]
    vols = [10 + (i % 7) for i in range(420)]
    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes, "volume": vols})


def test_sparse_portfolio_has_signal_column():
    out = SparseMetaPortfolioStrategy().generate_signals(sample_df())
    assert "signal" in out.columns


def test_sparse_portfolio_has_module_source():
    out = SparseMetaPortfolioStrategy().generate_signals(sample_df())
    assert "module_source" in out.columns
    assert "regime_state" in out.columns
