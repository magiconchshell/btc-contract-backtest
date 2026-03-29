"""
Strategy module for Bitcoin Contract Backtest System.
Contains all available trading strategies.
"""

from .strategy_base import BaseStrategy
from .advanced_strategies import (
    SMACrossStrategy,
    RSIStrategy,
    MACDCrossStrategy,
    BollingerBandsStrategy
)
from .hybrid_strategy import HybridStrategy, TrendFilterStrategy

__all__ = [
    'BaseStrategy',
    'SMACrossStrategy',
    'RSIStrategy', 
    'MACDCrossStrategy',
    'BollingerBandsStrategy',
    'HybridStrategy',
    'TrendFilterStrategy'
]

# Default strategy factory
def get_strategy(strategy_name: str, config: dict = None):
    """
    Factory function to create strategy instances.
    
    Args:
        strategy_name: Name of strategy to create
        config: Strategy configuration dictionary
        
    Returns:
        Strategy instance
    """
    if config is None:
        config = {}
    
    strategy_map = {
        'sma_cross': lambda: SMACrossStrategy(**config),
        'rsi': lambda: RSIStrategy(**config),
        'macd': lambda: MACDCrossStrategy(**config),
        'bollinger': lambda: BollingerBandsStrategy(**config),
        'hybrid': lambda: HybridStrategy(**config),
        'trend_filter': lambda: None  # Special case - see manager
    }
    
    if strategy_name not in strategy_map:
        raise ValueError(f"Unknown strategy: {strategy_name}. "
                        f"Available: {list(strategy_map.keys())}")
    
    return strategy_map[strategy_name]()
