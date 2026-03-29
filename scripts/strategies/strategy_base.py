#!/usr/bin/env python3
"""
Base strategy class for cryptocurrency trading strategies.
All custom strategies should inherit from this class.
"""

from abc import ABC, abstractmethod
import pandas as pd
import numpy as np


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    
    Subclasses must implement:
    - generate_signals(): Main signal generation logic
    - get_strategy_name(): Return strategy identifier
    
    Optional:
    - optimize_parameters(): Hyperparameter optimization
    """
    
    def __init__(self, config=None):
        """
        Initialize strategy with configuration.
        
        Args:
            config: Dictionary of strategy parameters
        """
        self.config = config or {}
        self.params = {}
        
    @abstractmethod
    def get_strategy_name(self) -> str:
        """Return unique strategy name."""
        pass
    
    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate trading signals based on price data.
        
        Args:
            df: DataFrame with OHLCV data and technical indicators
            
        Returns:
            DataFrame with added 'signal' column (1=long, -1=short, 0=no position)
        """
        pass
    
    def optimize_parameters(self, df: pd.DataFrame, param_grid: dict, 
                           metric='sharpe', k_folds=5):
        """
        Basic parameter optimization using cross-validation.
        
        Args:
            df: Historical price data
            param_grid: Dict of parameter names and value lists to test
            metric: Optimization metric ('sharpe', 'return', 'winrate')
            k_folds: Number of CV folds
            
        Returns:
            Best parameters dict and their performance score
        """
        from itertools import product
        
        best_params = None
        best_score = -np.inf
        
        # Generate all combinations
        key_lists = list(param_grid.keys())
        val_lists = list(param_grid.values())
        
        for combination in product(*val_lists):
            params = dict(zip(key_lists, combination))
            
            # Temporarily update params
            old_params = self.params.copy()
            self.params.update(params)
            
            # Test on this parameter set
            df_test = self.generate_signals(df.copy())
            score = self._calculate_metric(df_test, metric)
            
            # Restore old params
            self.params = old_params
            
            if score > best_score:
                best_score = score
                best_params = params
        
        return best_params, best_score
    
    def _calculate_metric(self, df: pd.DataFrame, metric: str) -> float:
        """Calculate performance metric from signals."""
        if df is None or 'signal' not in df.columns:
            return -np.inf
        
        returns = df['close'].pct_change().dropna()
        signals = df['signal'].dropna()
        
        # Align signals with returns
        aligned_returns = returns.iloc[1:].values
        aligned_signals = signals.values[:len(aligned_returns)]
        
        strategy_returns = aligned_returns * aligned_signals
        
        if metric == 'sharpe':
            if len(strategy_returns) < 2:
                return -np.inf
            sharpe = np.sqrt(252) * strategy_returns.mean() / strategy_returns.std()
            return sharpe if not np.isnan(sharpe) else -np.inf
        
        elif metric == 'return':
            return strategy_returns.sum()
        
        elif metric == 'winrate':
            if len(strategy_returns) == 0:
                return 0
            wins = len(strategy_returns[strategy_returns > 0])
            return wins / len(strategy_returns)
        
        return 0
