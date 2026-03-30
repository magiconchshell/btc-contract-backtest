from .base import BaseStrategy
from .indicators import RSIReversalStrategy, SMACrossStrategy, MACDCrossStrategy
from .hybrid import VotingHybridStrategy


def build_strategy(name: str, config: dict | None = None):
    config = config or {}
    if name == "rsi":
        return RSIReversalStrategy(**config)
    if name == "sma_cross":
        return SMACrossStrategy(**config)
    if name == "macd":
        return MACDCrossStrategy(**config)
    raise ValueError(f"Unknown strategy: {name}")
