from __future__ import annotations

import pandas as pd

from .base import BaseStrategy
from .indicators import MACDCrossStrategy, RSIReversalStrategy


class RegimeAsymmetricStrategy(BaseStrategy):
    def __init__(
        self,
        fast_trend_window: int = 50,
        slow_trend_window: int = 200,
        adx_window: int = 14,
        long_adx_threshold: float = 16.0,
        short_adx_threshold: float = 22.0,
        atr_window: int = 14,
        long_min_atr_pct: float = 0.003,
        long_max_atr_pct: float = 0.04,
        short_min_atr_pct: float = 0.004,
        short_max_atr_pct: float = 0.03,
        rsi_period: int = 14,
        long_rsi_threshold: float = 40.0,
        short_rsi_threshold: float = 64.0,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
    ):
        self.fast_trend_window = fast_trend_window
        self.slow_trend_window = slow_trend_window
        self.adx_window = adx_window
        self.long_adx_threshold = long_adx_threshold
        self.short_adx_threshold = short_adx_threshold
        self.atr_window = atr_window
        self.long_min_atr_pct = long_min_atr_pct
        self.long_max_atr_pct = long_max_atr_pct
        self.short_min_atr_pct = short_min_atr_pct
        self.short_max_atr_pct = short_max_atr_pct
        self.rsi_period = rsi_period
        self.long_rsi_threshold = long_rsi_threshold
        self.short_rsi_threshold = short_rsi_threshold
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal

    def name(self) -> str:
        return "regime_asymmetric"

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
        df["ema_fast_trend"] = (
            df["close"].ewm(span=self.fast_trend_window, adjust=False).mean()
        )
        df["ema_slow_trend"] = (
            df["close"].ewm(span=self.slow_trend_window, adjust=False).mean()
        )
        df["trend_up"] = df["ema_fast_trend"] > df["ema_slow_trend"]
        df["trend_down"] = df["ema_fast_trend"] < df["ema_slow_trend"]

        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - df["close"].shift(1)).abs()
        tr3 = (df["low"] - df["close"].shift(1)).abs()
        df["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df["atr"] = df["tr"].rolling(self.atr_window).mean()
        df["atr_pct"] = df["atr"] / df["close"]
        df["adx"] = self._compute_adx(df)

        long_rsi = RSIReversalStrategy(
            rsi_period=self.rsi_period,
            threshold_low=self.long_rsi_threshold,
            threshold_high=100,
        ).generate_signals(df.copy())
        short_rsi = RSIReversalStrategy(
            rsi_period=self.rsi_period,
            threshold_low=0,
            threshold_high=self.short_rsi_threshold,
        ).generate_signals(df.copy())
        macd_df = MACDCrossStrategy(
            fast_ema=self.macd_fast,
            slow_ema=self.macd_slow,
            signal_smooth=self.macd_signal,
        ).generate_signals(df.copy())

        long_ok = (
            df["trend_up"]
            & (df["adx"] >= self.long_adx_threshold)
            & (df["atr_pct"] >= self.long_min_atr_pct)
            & (df["atr_pct"] <= self.long_max_atr_pct)
            & (long_rsi["signal"] == 1)
            & (macd_df["signal"] == 1)
        )
        short_ok = (
            df["trend_down"]
            & (df["adx"] >= self.short_adx_threshold)
            & (df["atr_pct"] >= self.short_min_atr_pct)
            & (df["atr_pct"] <= self.short_max_atr_pct)
            & (short_rsi["signal"] == -1)
            & (macd_df["signal"] == -1)
        )

        df["signal"] = 0
        df.loc[long_ok, "signal"] = 1
        df.loc[short_ok, "signal"] = -1
        return df
