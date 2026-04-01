from __future__ import annotations
import pandas as pd
import numpy as np
from btc_contract_backtest.strategies.base import BaseStrategy

class HighFrequencyTestStrategy(BaseStrategy):
    """
    EXTREME NOISE STRATEGY for testing purposes.
    Designed to flip positions and enter/exit as much as possible.
    """
    def __init__(self, rsi_period: int = 2, overbought: float = 55, oversold: float = 45):
        super().__init__()
        self.rsi_period = rsi_period
        self.overbought = overbought
        self.oversold = oversold

    def name(self) -> str:
        return "high_frequency_test"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if len(df) < 2:
            df['signal'] = 0
            return df

        # EXTREME AGGRESSIVE TICK LOGIC:
        # Designed to force position flips constantly during Live Paper Trading.
        # We compare the current tick 'close' to the current 'open' or immediate micro-MA
        # to guarantee the signal flips wildly as the live price fluctuates within the candle.
        
        # If the live incomplete candle is currently Green (Price > Open), go LONG
        df.loc[df['close'] > df['open'], 'signal'] = 1
        
        # If the live incomplete candle is currently Red (Price < Open), go SHORT
        df.loc[df['close'] <= df['open'], 'signal'] = -1
        
        return df
