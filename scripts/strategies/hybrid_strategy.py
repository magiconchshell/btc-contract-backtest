#!/usr/bin/env python3
"""
Advanced Hybrid Strategy combining multiple indicators with voting system.
"""

import pandas as pd
import numpy as np
from .strategy_base import BaseStrategy
from .advanced_strategies import RSIStrategy, SMACrossStrategy, MACDCrossStrategy


class HybridStrategy(BaseStrategy):
    """
    Multi-strategy hybrid with vote-based entry signals.
    
    Combines multiple strategies and requires N confirmations
    before entering a position to reduce false signals.
    
    Configurable parameters:
    - base_strategies: List of strategy names to combine
    - required_votes: Minimum votes needed to enter (default: 2)
    - vote_weights: Optional weights for different strategies
    """
    
    def __init__(self, 
                 base_strategies=None,
                 required_votes=2,
                 vote_weights=None,
                 **kwargs):
        super().__init__(kwargs)
        
        # Default strategies if none specified
        self.base_strategies = base_strategies or [
            {'name': 'sma_cross', 'config': {}},
            {'name': 'rsi', 'config': {}}
        ]
        
        self.required_votes = required_votes
        self.vote_weights = vote_weights or {}
        
        # Initialize strategy instances
        self.strategy_instances = []
        for strat_cfg in self.base_strategies:
            name = strat_cfg['name']
            config = strat_cfg.get('config', {})
            
            if name == 'sma_cross':
                self.strategy_instances.append(SMACrossStrategy(**config))
            elif name == 'rsi':
                self.strategy_instances.append(RSIStrategy(**config))
            elif name == 'macd':
                from .advanced_strategies import MACDCrossStrategy
                self.strategy_instances.append(MACDCrossStrategy(**config))
        
        self.params = {
            'base_strategies': [s.get_strategy_name() for s in self.strategy_instances],
            'required_votes': required_votes,
            'vote_weights': vote_weights
        }
    
    def get_strategy_name(self) -> str:
        votes_str = f"{len(self.strategy_instances)}Strat_{self.required_votes}Votes"
        return f"Hybrid_{votes_str}"
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.strategy_instances:
            df['signal'] = 0
            return df
        
        df = df.copy()
        df['total_votes'] = 0
        df['long_votes'] = 0
        df['short_votes'] = 0
        
        # Run all base strategies
        for strategy in self.strategy_instances:
            try:
                strat_df = strategy.generate_signals(df.copy())
                
                # Count signals only if 'signal' column exists
                if 'signal' in strat_df.columns:
                    # Count positive signals
                    long_mask = strat_df['signal'] == 1
                    short_mask = strat_df['signal'] == -1
                    
                    df.loc[long_mask, 'long_votes'] += 1
                    df.loc[short_mask, 'short_votes'] += 1
            except Exception as e:
                print(f"⚠️ Strategy execution warning: {e}")
                continue
        
        # Generate final signal based on vote threshold
        df['signal'] = 0
        
        # Enter long if enough bullish votes and no bearish override
        long_condition = (df['long_votes'] >= self.required_votes) & \
                        (df['short_votes'] < (self.required_votes // 2 + 1))
        df.loc[long_condition, 'signal'] = 1
        
        # Enter short if enough bearish votes and no bullish override  
        short_condition = (df['short_votes'] >= self.required_votes) & \
                         (df['long_votes'] < (self.required_votes // 2 + 1))
        df.loc[short_condition, 'signal'] = -1
        
        return df
    
    def optimize_for_strategy(self, df: pd.DataFrame, param_grid: dict, 
                             metric='sharpe', k_folds=5):
        """
        Optimize hybrid strategy by testing different vote thresholds.
        """
        best_votes = self.required_votes
        best_score = -np.inf
        
        # Test different vote requirements
        test_values = range(1, min(len(self.strategy_instances) + 1, 6))
        
        for votes in test_values:
            old_votes = self.required_votes
            self.required_votes = votes
            
            result_df = self.generate_signals(df.copy())
            score = self._calculate_metric(result_df, metric)
            
            if score > best_score:
                best_score = score
                best_votes = votes
            
            self.required_votes = old_votes
        
        return {'required_votes': best_votes}, best_score


class TrendFilterStrategy(BaseStrategy):
    """
    Adds trend filter to any strategy.
    Only take signals that align with the overall trend.
    """
    
    def __init__(self, base_strategy, trend_sma_period=200, **kwargs):
        super().__init__(kwargs)
        self.base_strategy = base_strategy
        self.trend_sma_period = trend_sma_period
        self.params = {
            'base_strategy': base_strategy.get_strategy_name(),
            'trend_sma_period': trend_sma_period
        }
    
    def get_strategy_name(self) -> str:
        return f"TrendFiltered_{self.base_strategy.get_strategy_name()}"
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < self.trend_sma_period:
            df['signal'] = 0
            return df
        
        # Calculate trend indicator
        df['trend_sma'] = df['close'].rolling(window=self.trend_sma_period).mean()
        df['above_trend'] = df['close'] > df['trend_sma']
        
        # Get base strategy signals
        df_filtered = self.base_strategy.generate_signals(df.copy())
        
        # Apply trend filter
        df['signal'] = 0
        
        # Only allow longs when above trend
        long_signal = (df_filtered['signal'] == 1) & (df['above_trend'])
        df.loc[long_signal, 'signal'] = 1
        
        # Only allow shorts when below trend
        short_signal = (df_filtered['signal'] == -1) & (~df['above_trend'])
        df.loc[short_signal, 'signal'] = -1
        
        # No filter on exit (when signal goes to 0)
        df.loc[df_filtered['signal'] == 0, 'signal'] = 0
        
        return df
