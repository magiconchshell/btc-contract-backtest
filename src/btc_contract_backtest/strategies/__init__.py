from .base import BaseStrategy
from .indicators import RSIReversalStrategy, SMACrossStrategy, MACDCrossStrategy
from .hybrid import VotingHybridStrategy
from .regime_filtered import RegimeFilteredStrategy
from .regime_asymmetric import RegimeAsymmetricStrategy
from .baselines import BuyAndHoldLongStrategy, EMATrendStrategy
from .btc_bias import LongOnlyRegimeStrategy, ShortLiteRegimeStrategy, ExtremeDowntrendShortStrategy


def build_strategy(name: str, config: dict | None = None):
    config = config or {}
    if name == "rsi":
        return RSIReversalStrategy(**config)
    if name == "sma_cross":
        return SMACrossStrategy(**config)
    if name == "macd":
        return MACDCrossStrategy(**config)
    if name == "hybrid":
        return VotingHybridStrategy([build_strategy("rsi"), build_strategy("macd")], required_votes=1)
    if name == "regime_filtered":
        return RegimeFilteredStrategy(**config)
    if name == "regime_asymmetric":
        return RegimeAsymmetricStrategy(**config)
    if name == "buy_and_hold_long":
        return BuyAndHoldLongStrategy()
    if name == "ema_trend":
        return EMATrendStrategy(**config)
    if name == "long_only_regime":
        return LongOnlyRegimeStrategy(**config)
    if name == "short_lite_regime":
        return ShortLiteRegimeStrategy(**config)
    if name == "extreme_downtrend_short":
        return ExtremeDowntrendShortStrategy(**config)
    raise ValueError(f"Unknown strategy: {name}")
