from __future__ import annotations

import pandas as pd

from .base import BaseStrategy


class StrongBullLongStrategy(BaseStrategy):
    def __init__(
        self,
        fast_ema: int = 50,
        slow_ema: int = 200,
        trend_gap_pct: float = 0.03,
        adx_window: int = 14,
        adx_threshold: float = 24.0,
        breakout_lookback: int = 30,
        volume_window: int = 20,
        volume_multiplier: float = 1.05,
        atr_window: int = 14,
        min_atr_pct: float = 0.004,
        max_atr_pct: float = 0.03,
    ):
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.trend_gap_pct = trend_gap_pct
        self.adx_window = adx_window
        self.adx_threshold = adx_threshold
        self.breakout_lookback = breakout_lookback
        self.volume_window = volume_window
        self.volume_multiplier = volume_multiplier
        self.atr_window = atr_window
        self.min_atr_pct = min_atr_pct
        self.max_atr_pct = max_atr_pct

    def name(self) -> str:
        return "strong_bull_long"

    def _compute_adx(self, df: pd.DataFrame) -> pd.Series:
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
        atr = tr.rolling(self.adx_window).mean().replace(0, 1e-9)
        plus_di = 100 * (plus_dm.rolling(self.adx_window).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(self.adx_window).mean() / atr)
        dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)) * 100
        return dx.rolling(self.adx_window).mean()

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ema_fast"] = df["close"].ewm(span=self.fast_ema, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.slow_ema, adjust=False).mean()
        df["trend_gap_pct"] = (df["ema_fast"] / df["ema_slow"]) - 1.0
        df["rolling_high"] = df["high"].rolling(self.breakout_lookback).max().shift(1)
        df["volume_ma"] = df["volume"].rolling(self.volume_window).mean()
        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - df["close"].shift(1)).abs()
        tr3 = (df["low"] - df["close"].shift(1)).abs()
        df["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["atr"] = df["tr"].rolling(self.atr_window).mean()
        df["atr_pct"] = df["atr"] / df["close"]
        df["adx"] = self._compute_adx(df)
        df["signal"] = 0

        cond = (
            (df["ema_fast"] > df["ema_slow"])
            & (df["trend_gap_pct"] >= self.trend_gap_pct)
            & (df["adx"] >= self.adx_threshold)
            & (df["close"] > df["rolling_high"])
            & (df["volume"] >= df["volume_ma"] * self.volume_multiplier)
            & (df["atr_pct"] >= self.min_atr_pct)
            & (df["atr_pct"] <= self.max_atr_pct)
        )
        df.loc[cond, "signal"] = 1
        return df
