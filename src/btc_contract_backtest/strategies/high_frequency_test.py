from __future__ import annotations
import pandas as pd
import numpy as np
from btc_contract_backtest.strategies.base import BaseStrategy

class HighFrequencyTestStrategy(BaseStrategy):
    """
    A high-frequency strategy for testing engine execution, markers, and dashboard updates.
    Uses a very short-period RSI (2-period) to generate many signals on low timeframes.
    """
    def __init__(self, rsi_period: int = 2, overbought: float = 70, oversold: float = 30):
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

        # Calculate 2-period RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        
        # Avoid division by zero
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.fillna(50) # Neutral if no movement
        
        # Simple Logic: 
        # RSI < 30 -> LONG (1)
        # RSI > 70 -> SHORT (-1)
        # Otherwise -> Hold previous (using ffill)
        
        df['raw_signal'] = 0
        df.loc[rsi < self.oversold, 'raw_signal'] = 1
        df.loc[rsi > self.overbought, 'raw_signal'] = -1
        
        # Fill zeros with previous non-zero signal to simulate position holding
        # But for high frequency testing, we can also just use raw signals
        df['signal'] = df['raw_signal'].replace(0, np.nan).ffill().fillna(0)
        
        return df
