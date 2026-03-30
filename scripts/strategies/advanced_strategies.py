#!/usr/bin/env python3
"""
Advanced trading strategies for leveraged futures/perpetual backtesting.
Signals are contract-oriented: 1 = long, -1 = short, 0 = flat/hold.
"""

import pandas as pd
from .strategy_base import BaseStrategy


class SMACrossStrategy(BaseStrategy):
    def __init__(self, short_window=10, long_window=30, **kwargs):
        super().__init__(kwargs)
        self.params = {"short_window": short_window, "long_window": long_window}

    def get_strategy_name(self) -> str:
        return "SMA_Crossover"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if len(df) < self.params["long_window"]:
            df["signal"] = 0
            return df
        df["sma_short"] = df["close"].rolling(self.params["short_window"]).mean()
        df["sma_long"] = df["close"].rolling(self.params["long_window"]).mean()
        df["signal"] = 0
        bullish = (df["sma_short"] > df["sma_long"]) & (df["sma_short"].shift(1) <= df["sma_long"].shift(1))
        bearish = (df["sma_short"] < df["sma_long"]) & (df["sma_short"].shift(1) >= df["sma_long"].shift(1))
        df.loc[bullish, "signal"] = 1
        df.loc[bearish, "signal"] = -1
        return df


class RSIStrategy(BaseStrategy):
    def __init__(self, rsi_period=14, threshold_low=30, threshold_high=70, **kwargs):
        super().__init__(kwargs)
        self.params = {
            "rsi_period": rsi_period,
            "threshold_low": threshold_low,
            "threshold_high": threshold_high,
        }

    def get_strategy_name(self) -> str:
        return "RSI_Reversal"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if len(df) < self.params["rsi_period"]:
            df["signal"] = 0
            return df
        delta = df["close"].diff()
        gain = delta.clip(lower=0).rolling(self.params["rsi_period"]).mean()
        loss = (-delta.clip(upper=0)).rolling(self.params["rsi_period"]).mean()
        rs = gain / loss.replace(0, 1e-9)
        df["rsi"] = 100 - (100 / (1 + rs))
        df["signal"] = 0
        df.loc[df["rsi"] <= self.params["threshold_low"], "signal"] = 1
        df.loc[df["rsi"] >= self.params["threshold_high"], "signal"] = -1
        return df


class MACDCrossStrategy(BaseStrategy):
    def __init__(self, fast_ema=12, slow_ema=26, signal_smooth=9, **kwargs):
        super().__init__(kwargs)
        self.params = {"fast_ema": fast_ema, "slow_ema": slow_ema, "signal_smooth": signal_smooth}

    def get_strategy_name(self) -> str:
        return "MACD_Crossover"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if len(df) < self.params["slow_ema"]:
            df["signal"] = 0
            return df
        ema_fast = df["close"].ewm(span=self.params["fast_ema"], adjust=False).mean()
        ema_slow = df["close"].ewm(span=self.params["slow_ema"], adjust=False).mean()
        df["macd"] = ema_fast - ema_slow
        df["signal_line"] = df["macd"].ewm(span=self.params["signal_smooth"], adjust=False).mean()
        df["signal"] = 0
        bullish = (df["macd"] > df["signal_line"]) & (df["macd"].shift(1) <= df["signal_line"].shift(1))
        bearish = (df["macd"] < df["signal_line"]) & (df["macd"].shift(1) >= df["signal_line"].shift(1))
        df.loc[bullish, "signal"] = 1
        df.loc[bearish, "signal"] = -1
        return df


class BollingerBandsStrategy(BaseStrategy):
    def __init__(self, bb_period=20, bb_std=2, **kwargs):
        super().__init__(kwargs)
        self.params = {"bb_period": bb_period, "bb_std": bb_std}

    def get_strategy_name(self) -> str:
        return "Bollinger_Bands"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if len(df) < self.params["bb_period"]:
            df["signal"] = 0
            return df
        df["sma"] = df["close"].rolling(self.params["bb_period"]).mean()
        df["std"] = df["close"].rolling(self.params["bb_period"]).std()
        df["upper_band"] = df["sma"] + self.params["bb_std"] * df["std"]
        df["lower_band"] = df["sma"] - self.params["bb_std"] * df["std"]
        df["signal"] = 0
        df.loc[df["close"] <= df["lower_band"], "signal"] = 1
        df.loc[df["close"] >= df["upper_band"], "signal"] = -1
        return df
