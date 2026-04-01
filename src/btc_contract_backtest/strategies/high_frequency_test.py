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
        return "HighFrequencyTest"

    def execute(self, df: pd.DataFrame) -> pd.Series:
        if len(df) < self.rsi_period + 1:
            return pd.Series(0, index=df.index)

        # Calculate 2-period RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        signals = pd.Series(0, index=df.index)
        
        # Simple Logic: 
        # RSI < 30 -> LONG (1)
        # RSI > 70 -> SHORT (-1)
        # Otherwise -> Hold previous
        
        current_signal = 0
        for i in range(len(df)):
            val = rsi.iloc[i]
            if pd.isna(val):
                signals.iloc[i] = 0
                continue
                
            if val < self.oversold:
                current_signal = 1
            elif val > self.overbought:
                current_signal = -1
            
            signals.iloc[i] = current_signal
            
        return signals
