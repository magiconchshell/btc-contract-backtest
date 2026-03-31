from __future__ import annotations

import pandas as pd

from .base import BaseStrategy
from .short_overlay_switcher import ShortOverlaySwitcherStrategy
from .strong_bull_long import StrongBullLongStrategy


class SparseMetaPortfolioStrategy(BaseStrategy):
    def __init__(
        self,
        fast_ema: int = 50,
        slow_ema: int = 200,
        crash_lookback: int = 16,
        crash_threshold_pct: float = 0.05,
        crash_adx_threshold: float = 24.0,
        bull_trend_gap_pct: float = 0.03,
        bull_adx_threshold: float = 24.0,
        neutral_mode: str = "flat",
    ):
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.crash_lookback = crash_lookback
        self.crash_threshold_pct = crash_threshold_pct
        self.crash_adx_threshold = crash_adx_threshold
        self.bull_trend_gap_pct = bull_trend_gap_pct
        self.bull_adx_threshold = bull_adx_threshold
        self.neutral_mode = neutral_mode
        self.short_module = ShortOverlaySwitcherStrategy(
            fast_ema=fast_ema,
            slow_ema=slow_ema,
            crash_lookback=crash_lookback,
            crash_threshold_pct=crash_threshold_pct,
            crash_adx_threshold=crash_adx_threshold,
            allow_bull_long=False,
        )
        self.long_module = StrongBullLongStrategy(
            fast_ema=fast_ema,
            slow_ema=slow_ema,
            trend_gap_pct=bull_trend_gap_pct,
            adx_threshold=bull_adx_threshold,
        )

    def name(self) -> str:
        return "sparse_meta_portfolio"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        short_df = self.short_module.generate_signals(df.copy())
        long_df = self.long_module.generate_signals(df.copy())

        df["signal"] = 0
        df["regime_state"] = short_df.get("regime_state", "neutral")
        df["short_signal_raw"] = short_df["signal"]
        df["long_signal_raw"] = long_df["signal"]
        df["module_source"] = "flat"

        crash_mask = short_df["signal"] < 0
        bull_mask = (long_df["signal"] > 0) & (~crash_mask)

        df.loc[crash_mask, "signal"] = -1
        df.loc[crash_mask, "module_source"] = "short_overlay"

        df.loc[bull_mask, "signal"] = 1
        df.loc[bull_mask, "module_source"] = "strong_bull_long"

        if self.neutral_mode != "flat":
            df.loc[
                (df["module_source"] == "flat") & (self.neutral_mode == "bull_bias"),
                "signal",
            ] = 0

        return df
