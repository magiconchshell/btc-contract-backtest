import pandas as pd
from .base import BaseStrategy


class RSIReversalStrategy(BaseStrategy):
    def __init__(self, rsi_period=14, threshold_low=30, threshold_high=70):
        self.rsi_period = rsi_period
        self.threshold_low = threshold_low
        self.threshold_high = threshold_high

    def name(self) -> str:
        return "rsi_reversal"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        delta = df["close"].diff()
        gain = delta.clip(lower=0).rolling(self.rsi_period).mean()
        loss = (-delta.clip(upper=0)).rolling(self.rsi_period).mean().replace(0, 1e-9)
        rs = gain / loss
        df["rsi"] = 100 - 100 / (1 + rs)
        df["signal"] = 0
        df.loc[df["rsi"] <= self.threshold_low, "signal"] = 1
        df.loc[df["rsi"] >= self.threshold_high, "signal"] = -1
        return df


class SMACrossStrategy(BaseStrategy):
    def __init__(self, short_window=10, long_window=30):
        self.short_window = short_window
        self.long_window = long_window

    def name(self) -> str:
        return "sma_cross"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["sma_short"] = df["close"].rolling(self.short_window).mean()
        df["sma_long"] = df["close"].rolling(self.long_window).mean()
        df["signal"] = 0
        bullish = (df["sma_short"] > df["sma_long"]) & (
            df["sma_short"].shift(1) <= df["sma_long"].shift(1)
        )
        bearish = (df["sma_short"] < df["sma_long"]) & (
            df["sma_short"].shift(1) >= df["sma_long"].shift(1)
        )
        df.loc[bullish, "signal"] = 1
        df.loc[bearish, "signal"] = -1
        return df


class MACDCrossStrategy(BaseStrategy):
    def __init__(self, fast_ema=12, slow_ema=26, signal_smooth=9):
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.signal_smooth = signal_smooth

    def name(self) -> str:
        return "macd_cross"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        ema_fast = df["close"].ewm(span=self.fast_ema, adjust=False).mean()
        ema_slow = df["close"].ewm(span=self.slow_ema, adjust=False).mean()
        df["macd"] = ema_fast - ema_slow
        df["signal_line"] = df["macd"].ewm(span=self.signal_smooth, adjust=False).mean()
        df["signal"] = 0
        bullish = (df["macd"] > df["signal_line"]) & (
            df["macd"].shift(1) <= df["signal_line"].shift(1)
        )
        bearish = (df["macd"] < df["signal_line"]) & (
            df["macd"].shift(1) >= df["signal_line"].shift(1)
        )
        df.loc[bullish, "signal"] = 1
        df.loc[bearish, "signal"] = -1
        return df
