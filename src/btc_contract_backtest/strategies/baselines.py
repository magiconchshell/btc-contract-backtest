from __future__ import annotations

import pandas as pd

from .base import BaseStrategy


class BuyAndHoldLongStrategy(BaseStrategy):
    def name(self) -> str:
        return "buy_and_hold_long"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["signal"] = 0
        if not df.empty:
            df.iloc[0, df.columns.get_loc("signal")] = 1
        return df


class EMATrendStrategy(BaseStrategy):
    def __init__(self, fast_window: int = 50, slow_window: int = 200):
        self.fast_window = fast_window
        self.slow_window = slow_window

    def name(self) -> str:
        return "ema_trend"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ema_fast"] = df["close"].ewm(span=self.fast_window, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.slow_window, adjust=False).mean()
        df["signal"] = 0
        bullish = (df["ema_fast"] > df["ema_slow"]) & (df["ema_fast"].shift(1) <= df["ema_slow"].shift(1))
        bearish = (df["ema_fast"] < df["ema_slow"]) & (df["ema_fast"].shift(1) >= df["ema_slow"].shift(1))
        df.loc[bullish, "signal"] = 1
        df.loc[bearish, "signal"] = -1
        return df
