from __future__ import annotations

import pandas as pd

from .base import BaseStrategy
from .btc_bias import ExtremeDowntrendShortStrategy, LongOnlyRegimeStrategy


class RegimeSwitcherStrategy(BaseStrategy):
    def __init__(
        self,
        fast_ema: int = 50,
        slow_ema: int = 200,
        crash_lookback: int = 20,
        crash_threshold_pct: float = 0.06,
        bull_adx_threshold: float = 16.0,
        crash_adx_threshold: float = 28.0,
        neutral_allows_position: bool = False,
    ):
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.crash_lookback = crash_lookback
        self.crash_threshold_pct = crash_threshold_pct
        self.bull_adx_threshold = bull_adx_threshold
        self.crash_adx_threshold = crash_adx_threshold
        self.neutral_allows_position = neutral_allows_position
        self.long_module = LongOnlyRegimeStrategy()
        self.short_module = ExtremeDowntrendShortStrategy(ema_fast=fast_ema, ema_slow=slow_ema, breakdown_lookback=crash_lookback, adx_threshold=crash_adx_threshold)

    def name(self) -> str:
        return "regime_switcher"

    def _compute_adx(self, df: pd.DataFrame, window: int = 14) -> pd.Series:
        high = df["high"]
        low = df["low"]
        close = df["close"]
        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window).mean().replace(0, 1e-9)
        plus_di = 100 * (plus_dm.rolling(window).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window).mean() / atr)
        dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)) * 100
        return dx.rolling(window).mean()

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ema_fast"] = df["close"].ewm(span=self.fast_ema, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.slow_ema, adjust=False).mean()
        df["rolling_max"] = df["close"].rolling(self.crash_lookback).max().shift(1)
        df["drawdown_from_recent_high"] = (df["close"] / df["rolling_max"]) - 1.0
        df["adx"] = self._compute_adx(df)

        bull_regime = (df["ema_fast"] > df["ema_slow"]) & (df["adx"] >= self.bull_adx_threshold)
        crash_regime = (df["ema_fast"] < df["ema_slow"]) & (df["drawdown_from_recent_high"] <= -self.crash_threshold_pct) & (df["adx"] >= self.crash_adx_threshold)
        neutral_regime = ~(bull_regime | crash_regime)

        long_df = self.long_module.generate_signals(df.copy())
        short_df = self.short_module.generate_signals(df.copy())

        df["regime_state"] = "neutral"
        df.loc[bull_regime, "regime_state"] = "bull"
        df.loc[crash_regime, "regime_state"] = "crash"
        df["long_signal_raw"] = long_df["signal"]
        df["short_signal_raw"] = short_df["signal"]
        df["signal"] = 0
        df.loc[bull_regime & (long_df["signal"] > 0), "signal"] = 1
        df.loc[crash_regime & (short_df["signal"] < 0), "signal"] = -1

        if self.neutral_allows_position:
            df.loc[neutral_regime & (long_df["signal"] > 0), "signal"] = 1

        df["module_source"] = "flat"
        df.loc[df["signal"] == 1, "module_source"] = "long_module"
        df.loc[df["signal"] == -1, "module_source"] = "short_module"
        return df
