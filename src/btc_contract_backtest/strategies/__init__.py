from .base import BaseStrategy
from .indicators import RSIReversalStrategy, SMACrossStrategy, MACDCrossStrategy
from .hybrid import VotingHybridStrategy
from .regime_filtered import RegimeFilteredStrategy
from .regime_asymmetric import RegimeAsymmetricStrategy


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
    raise ValueError(f"Unknown strategy: {name}")
