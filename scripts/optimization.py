#!/usr/bin/env python3
"""
Parameter Optimization Module for Backtest Strategies.
Automates finding the best parameter combinations.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from itertools import product
import time


def optimize_parameters(strategy, df: pd.DataFrame, 
                       param_grid: Dict[str, List],
                       metric='sharpe',
                       k_folds=5,
                       verbose=True):
    """
    Grid search optimization for strategy parameters.
    
    Args:
        strategy: Strategy instance to optimize
        df: Historical price data with OHLCV
        param_grid: Dict of parameter names and value lists to test
        metric: Optimization target ('sharpe', 'return', 'winrate')
        k_folds: Number of cross-validation folds
        verbose: Print progress
        
    Returns:
        Best params dict and their performance score
    """
    if verbose:
        print(f"🔍 Starting parameter optimization...")
        print(f"   Testing {len(product(*param_grid.values()))} combinations")
    
    start_time = time.time()
    
    # Generate all combinations
    key_lists = list(param_grid.keys())
    val_lists = list(param_grid.values())
    combinations = list(product(*val_lists))
    
    best_params = None
    best_score = -np.inf
    
    for i, combination in enumerate(combinations):
        params = dict(zip(key_lists, combination))
        
        if verbose and (i + 1) % 10 == 0:
            print(f"   Tested {i + 1}/{len(combinations)} combinations...")
        
        # Temporarily update params
        old_params = strategy.params.copy()
        strategy.params.update(params)
        
        # Generate signals
        try:
            result_df = strategy.generate_signals(df.copy())
            
            # Calculate metric
            score = _calculate_crossvalidated_score(result_df, metric, k_folds)
            
            # Restore old params
            strategy.params = old_params
            
            if score > best_score:
                best_score = score
                best_params = params.copy()
                
        except Exception as e:
            # Restore params on error
            strategy.params = old_params
            continue
    
    elapsed = time.time() - start_time
    
    if verbose:
        print(f"\n✅ Optimization completed!")
        print(f"   Best params: {best_params}")
        print(f"   Best score: {best_score:.4f}")
        print(f"   Time: {elapsed:.2f}s")
        print(f"   Total tested: {len(combinations)} combinations")
    
    return best_params, best_score


def _calculate_crossvalidated_score(df: pd.DataFrame, metric: str, 
                                   k_folds: int) -> float:
    """Calculate metric using simple time-series CV."""
    if len(df) < 100 or 'signal' not in df.columns:
        return -np.inf
    
    # Split into K folds
    fold_size = len(df) // k_folds
    scores = []
    
    for i in range(k_folds):
        # Validation set: current fold
        start_idx = i * fold_size
        end_idx = start_idx + fold_size if i < k_folds - 1 else len(df)
        
        if end_idx <= start_idx:
            continue
        
        val_data = df.iloc[start_idx:end_idx]
        
        if len(val_data) < 20:
            continue
        
        score = _calculate_metric_for_df(val_data, metric)
        if not np.isnan(score):
            scores.append(score)
    
    if not scores:
        return -np.inf
    
    return np.mean(scores)


def _calculate_metric_for_df(df: pd.DataFrame, metric: str) -> float:
    """Calculate single metric from signal DataFrame."""
    returns = df['close'].pct_change().dropna()
    signals = df['signal'].dropna()
    
    # Align signals with returns
    aligned_returns = returns.iloc[1:].values
    aligned_signals = signals.values[:len(aligned_returns)]
    
    strategy_returns = aligned_returns * aligned_signals
    
    if metric == 'sharpe':
        if len(strategy_returns) < 2:
            return -np.inf
        sharpe = np.sqrt(252) * strategy_returns.mean() / (strategy_returns.std() + 1e-8)
        return sharpe if not np.isnan(sharpe) else -np.inf
    
    elif metric == 'return':
        total_return = strategy_returns.sum()
        return total_return if not np.isnan(total_return) else -np.inf
    
    elif metric == 'winrate':
        if len(strategy_returns) == 0:
            return 0
        wins = len(strategy_returns[strategy_returns > 0])
        win_rate = wins / len(strategy_returns)
        return win_rate
    
    return 0


class AutomatedOptimRunner:
    """
    High-level optimizer that runs automated experiments.
    """
    
    def __init__(self, results_dir='./opt_results'):
        self.results_dir = results_dir
        self.experiments = []
    
    def run_experiment(self, strategy_name: str, base_config: dict,
                      opt_param_grid: dict, 
                      df: pd.DataFrame,
                      metric='sharpe'):
        """
        Run a complete optimization experiment.
        
        Args:
            strategy_name: Name of strategy
            base_config: Base configuration for strategy
            opt_param_grid: Parameters to optimize
            df: Historical data
            metric: Optimization target
            
        Returns:
            Experiment results dict
        """
        from scripts.strategies import get_strategy
        
        # Create strategy with base config
        full_config = {**base_config}
        for param, values in opt_param_grid.items():
            if isinstance(values, list):
                full_config[param] = values[0]  # Start with first value
            else:
                full_config[param] = values
        
        strategy = get_strategy(strategy_name, full_config)
        
        # Optimize
        best_params, best_score = optimize_parameters(
            strategy, df, opt_param_grid, metric
        )
        
        # Add optimal values to base config
        final_config = {**base_config, **best_params}
        
        result = {
            'strategy': strategy_name,
            'original_config': base_config,
            'optimized_config': final_config,
            'best_score': best_score,
            'metric': metric,
            'timestamp': pd.Timestamp.now().isoformat()
        }
        
        self.experiments.append(result)
        
        return result
    
    def summarize_experiments(self):
        """Print summary of all experiments."""
        if not self.experiments:
            print("No experiments run yet.")
            return
        
        print("\n" + "="*70)
        print("OPTIMIZATION EXPERIMENT SUMMARY")
        print("="*70)
        
        for exp in self.experiments:
            print(f"\n{exp['strategy'].upper()}")
            print("-"*70)
            print(f"Original Config: {exp['original_config']}")
            print(f"Optimized Config: {exp['optimized_config']}")
            print(f"Best Score ({exp['metric']}): {exp['best_score']:.4f}")
        
        print("="*70 + "\n")
