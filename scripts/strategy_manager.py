#!/usr/bin/env python3
"""
Strategy Manager - Central hub for managing multiple trading strategies.
Handles strategy selection, execution, comparison, and optimization.
Phase 3: Now includes hybrid strategies and automated optimization!
"""

import pandas as pd
from typing import List, Dict, Optional, Union
from scripts.strategies import get_strategy, BaseStrategy, HybridStrategy, TrendFilterStrategy


class StrategyManager:
    """
    Manages trading strategies for backtesting.
    
    Phase 3 Features:
    - Support for multiple strategies
    - Hybrid multi-strategy combinations
    - Trend filtering
    - Parameter optimization
    - Strategy comparison
    - Easy strategy switching
    """
    
    def __init__(self):
        self.current_strategy: Optional[BaseStrategy] = None
        self.available_strategies = {
            'sma_cross': {'name': 'SMA Crossover', 'description': 'Moving average crossover'},
            'rsi': {'name': 'RSI Reversal', 'description': 'RSI mean reversion'},
            'macd': {'name': 'MACD Crossover', 'description': 'MACD signal line cross'},
            'bollinger': {'name': 'Bollinger Bands', 'description': 'BB mean reversion'},
            'hybrid': {'name': 'Hybrid Multi-Indicator', 'description': 'Combined signals with voting'},
            'trend_filter': {'name': 'Trend Filter', 'description': 'Filter signals by trend direction'}
        }
    
    def set_strategy(self, strategy_name: str, config: dict = None) -> BaseStrategy:
        """
        Set the active trading strategy.
        
        Args:
            strategy_name: Name from available_strategies
            config: Strategy parameters dictionary
            
        Returns:
            Active strategy instance
        """
        if config is None:
            config = {}
            
        try:
            # Handle special cases
            if strategy_name == 'trend_filter':
                # Requires a base strategy
                base_name = config.get('base_strategy', 'rsi')
                base_config = config.get('config', {})
                base_strat = get_strategy(base_name, base_config)
                
                trend_sma = config.get('trend_sma_period', 200)
                self.current_strategy = TrendFilterStrategy(
                    base_strategy=base_strat,
                    trend_sma_period=trend_sma
                )
            else:
                self.current_strategy = get_strategy(strategy_name, config)
            
            print(f"✅ Loaded strategy: {self.current_strategy.get_strategy_name()}")
            return self.current_strategy
            
        except Exception as e:
            print(f"❌ Error loading strategy: {e}")
            raise
    
    def run_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Run current strategy on price data.
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            DataFrame with added signals
        """
        if self.current_strategy is None:
            raise ValueError("No strategy set! Call set_strategy() first.")
        
        print(f"🤖 Running {self.current_strategy.get_strategy_name()}...")
        
        try:
            result_df = self.current_strategy.generate_signals(df.copy())
            n_signals = len(result_df[result_df['signal'] != 0])
            print(f"   Generated {n_signals} signals")
            return result_df
            
        except Exception as e:
            print(f"❌ Strategy execution error: {e}")
            raise
    
    def create_hybrid(self, strategies_config: list, required_votes: int = 2) -> HybridStrategy:
        """
        Create a hybrid strategy from multiple base strategies.
        
        Args:
            strategies_config: List of dicts with 'name' and 'config' keys
            required_votes: Minimum votes needed to enter trade
            
        Returns:
            Configured HybridStrategy instance
        """
        strategy_instances = []
        
        for strat_cfg in strategies_config:
            name = strat_cfg['name']
            config = strat_cfg.get('config', {})
            strategy = get_strategy(name, config)
            strategy_instances.append(strategy)
        
        hybrid = HybridStrategy(
            base_strategies=strategies_config,
            required_votes=required_votes
        )
        
        # Replace internal instances
        hybrid.strategy_instances = strategy_instances
        
        self.current_strategy = hybrid
        print(f"✅ Created hybrid with {len(strategies_config)} strategies")
        print(f"   Required votes: {required_votes}")
        
        return hybrid
    
    def optimize_parameters(self, df: pd.DataFrame, param_grid: dict, 
                           metric='sharpe', k_folds=5) -> Dict:
        """
        Optimize strategy parameters using grid search.
        
        Args:
            df: Historical data
            param_grid: Dict of params and value lists to test
            metric: Optimization target ('sharpe', 'return', 'winrate')
            k_folds: Cross-validation folds
            
        Returns:
            Best params dict and their score
        """
        if self.current_strategy is None:
            raise ValueError("No strategy set!")
        
        print(f"🔍 Optimizing {self.current_strategy.get_strategy_name()}...")
        
        from scripts.optimization import optimize_parameters
        
        best_params, best_score = optimize_parameters(
            self.current_strategy, df, param_grid, metric, k_folds
        )
        
        print(f"✅ Best params: {best_params}")
        print(f"   Score: {best_score:.4f}")
        
        # Update strategy with best params
        self.current_strategy.params.update(best_params)
        
        return {
            'parameters': best_params,
            'score': best_score,
            'metric': metric
        }
    
    def run_hybrid_optimization(self, df: pd.DataFrame,
                               metrics=['sharpe', 'return', 'winrate'],
                               max_votes=3):
        """
        Run optimization across different vote requirements for hybrid.
        
        Args:
            df: Historical data
            metrics: Metrics to evaluate
            max_votes: Maximum votes to test (1 to len(strategies))
            
        Returns:
            Results for each vote configuration
        """
        if not isinstance(self.current_strategy, HybridStrategy):
            raise ValueError("Must be a hybrid strategy to optimize votes")
        
        results = []
        
        for votes in range(1, min(max_votes + 1, len(self.current_strategy.strategy_instances) + 1)):
            old_votes = self.current_strategy.required_votes
            self.current_strategy.required_votes = votes
            
            result_df = self.run_strategy(df.copy())
            
            for metric in metrics:
                score = self.current_strategy._calculate_metric(result_df, metric)
                results.append({
                    'votes': votes,
                    'metric': metric,
                    'score': score
                })
            
            self.current_strategy.required_votes = old_votes
        
        # Find best configuration
        best = max(results, key=lambda x: x['score'])
        
        print(f"\n✅ Hybrid optimization complete!")
        print(f"   Best votes: {best['votes']}")
        print(f"   Best metric ({best['metric']}): {best['score']:.4f}")
        
        return results
