from __future__ import annotations

import pandas as pd

from .base import BaseStrategy
from .regime_filtered import RegimeFilteredStrategy
from .regime_asymmetric import RegimeAsymmetricStrategy


class LongOnlyRegimeStrategy(BaseStrategy):
    def __init__(self, **kwargs):
        self.inner = RegimeFilteredStrategy(**kwargs)

    def name(self) -> str:
        return "long_only_regime"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        out = self.inner.generate_signals(df.copy())
        out.loc[out["signal"] < 0, "signal"] = 0
        return out


class ShortLiteRegimeStrategy(BaseStrategy):
    def __init__(self, short_adx_threshold: float = 28.0, short_max_atr_pct: float = 0.02, **kwargs):
        cfg = dict(kwargs)
        cfg.setdefault("short_adx_threshold", short_adx_threshold)
        cfg.setdefault("short_max_atr_pct", short_max_atr_pct)
        self.inner = RegimeAsymmetricStrategy(**cfg)

    def name(self) -> str:
        return "short_lite_regime"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        return self.inner.generate_signals(df.copy())


class ExtremeDowntrendShortStrategy(BaseStrategy):
    def __init__(self, ema_fast: int = 50, ema_slow: int = 200, breakdown_lookback: int = 20, adx_window: int = 14, adx_threshold: float = 28.0):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.breakdown_lookback = breakdown_lookback
        self.adx_window = adx_window
        self.adx_threshold = adx_threshold

    def name(self) -> str:
        return "extreme_downtrend_short"

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
        df["ema_fast"] = df["close"].ewm(span=self.ema_fast, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=self.ema_slow, adjust=False).mean()
        df["rolling_low"] = df["low"].rolling(self.breakdown_lookback).min().shift(1)
        df["adx"] = self._compute_adx(df)
        df["signal"] = 0
        short_cond = (df["ema_fast"] < df["ema_slow"]) & (df["close"] < df["rolling_low"]) & (df["adx"] >= self.adx_threshold)
        df.loc[short_cond, "signal"] = -1
        return df
