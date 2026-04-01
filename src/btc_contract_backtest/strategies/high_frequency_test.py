from __future__ import annotations
import pandas as pd
from btc_contract_backtest.strategies.base import BaseStrategy


class HighFrequencyTestStrategy(BaseStrategy):
    """
    EXTREME NOISE STRATEGY for testing purposes.
    Designed to flip positions and enter/exit as much as possible.
    """

    def __init__(
        self, rsi_period: int = 2, overbought: float = 55, oversold: float = 45
    ):
        super().__init__()
        self.rsi_period = rsi_period
        self.overbought = overbought
        self.oversold = oversold

    def name(self) -> str:
        return "high_frequency_test"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if len(df) < 2:
            df["signal"] = 0
            return df

        # EXTREME AGGRESSIVE TICK LOGIC:
        # Designed to force position flips constantly during Live Paper Trading.
        # We compare the current tick 'close' to the current 'open' or immediate micro-MA
        # to guarantee the signal flips wildly as the live price fluctuates within the candle.

        # EXTREME AGGRESSIVE TICK LOGIC:
        # Designed to force position flips constantly during Live Paper Trading.
        # We use a combination of price and volume. Binance updates the running 1m
        # candle's volume every microsecond, so combining it guarantees a constantly
        # flickering pseudo-random walk that evaluates to 1 or -1.

        seed_value = (
            (df["close"] * 10 + df.get("volume", 0) * 1000).fillna(0).astype(int)
        )
        seed_is_even = seed_value % 2 == 0

        df.loc[seed_is_even, "signal"] = 1
        df.loc[~seed_is_even, "signal"] = -1

        return df
