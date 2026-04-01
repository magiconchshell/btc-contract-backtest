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
        if len(df) < self.rsi_period + 1:
            df['signal'] = 0
            return df

        # Calculate ultra-fast RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.fillna(50)
        
        # AGGRESSIVE LOGIC:
        # We don't use ffill here. We want it to exit (0) as soon as it's not overbought/oversold.
        # This will create much more 'IN' and 'OUT' markers on the chart.
        df['signal'] = 0
        df.loc[rsi < self.oversold, 'signal'] = 1   # Long if slightly oversold
        df.loc[rsi > self.overbought, 'signal'] = -1 # Short if slightly overbought
        
        return df
