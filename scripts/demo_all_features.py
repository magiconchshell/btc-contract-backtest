#!/usr/bin/env python3
"""
Demo script to showcase all Phase 3 features.
Run this to see examples of each capability.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.strategy_manager import StrategyManager
from scripts.backtest_engine import CryptoBacktestEngine


def demo_hybrid_strategy():
    """Demonstrate hybrid multi-strategy voting."""
    print("\n" + "="*70)
    print("🧩 DEMO: Hybrid Multi-Strategy Voting")
    print("="*70)
    
    from scripts.strategies import get_strategy
    
    # Create a 3-strategy hybrid
    manager = StrategyManager()
    manager.set_strategy('hybrid', {
        'base_strategies': [
            {'name': 'rsi', 'config': {}},
            {'name': 'macd', 'config': {}},
            {'name': 'bollinger', 'config': {}}
        ],
        'required_votes': 2  # Need 2 out of 3 to agree
    })
    
    print(f"✅ Created: {manager.current_strategy.get_strategy_name()}")
    print(f"   Strategies: RSI + MACD + Bollinger Bands")
    print(f"   Required votes: 2 (majority rule)")
    

def demo_trend_filtering():
    """Demonstrate trend-filtered strategies."""
    print("\n" + "="*70)
    print("📈 DEMO: Trend Filtering")
    print("="*70)
    
    manager = StrategyManager()
    manager.set_strategy('trend_filter', {
        'base_strategy': 'rsi',
        'config': {},
        'trend_sma_period': 200
    })
    
    print(f"✅ Created: {manager.current_strategy.get_strategy_name()}")
    print(f"   Base strategy: RSI")
    print(f"   Trend filter: 200-period SMA")
    print(f"   Rule: Long only when above trend, short only when below")


def demo_parameter_optimization():
    """Show how parameter optimization works."""
    print("\n" + "="*70)
    print("🔍 DEMO: Parameter Optimization Framework")
    print("="*70)
    
    print("""
The optimization module can automatically search for best parameters:

Example usage in main.py:
    uv run python scripts/main.py --optimize rsi \\
        --param-grid 'rsi_period=[10,14,20,30]' \\
        --metric sharpe

This will test RSI periods of 10, 14, 20, and 30,
and pick the one with best Sharpe ratio using cross-validation.

For more complex grids:
    uv run python scripts/main.py --optimize sma_cross \\
        --param-grid 'short_window=[5,10,15],long_window=[20,30,50]' \\
        --metric return

Tests 3×3 = 9 combinations automatically!
""")


def demo_backtest_flow():
    """Complete backtest example."""
    print("\n" + "="*70)
    print("⚡ COMPLETE BACKTEST FLOW EXAMPLE")
    print("="*70)
    
    print("""
Full workflow in 4 simple steps:

Step 1: Initialize engine
    engine = CryptoBacktestEngine(symbol='BTC/USDT', timeframe='1h')

Step 2: Fetch historical data
    df = engine.fetch_historical_data(
        start_date='2026-01-01', 
        end_date='2026-03-29'
    )

Step 3: Set and run strategy
    manager = StrategyManager()
    manager.set_strategy('rsi')
    df_signals = manager.run_strategy(df)

Step 4: Simulate and analyze
    results = engine.simulate_trades(df_signals)
    metrics = engine.calculate_metrics(results)
    
    Print or save beautiful visualizations!

Or just use the CLI:
    uv run python scripts/main.py --days 90 --strategy rsi
""")


if __name__ == "__main__":
    print("\n💰 Bitcoin Contract Backtest System - Phase 3 Demo")
    print("===========================================\n")
    
    demo_hybrid_strategy()
    demo_trend_filtering()
    demo_parameter_optimization()
    demo_backtest_flow()
    
    print("\n" + "="*70)
    print("✨ All demos completed!")
    print("="*70)
    print("\nTo try these yourself, run:")
    print("  cd /Users/magiconch/.openclaw/workspace/skills/public/btc-contract-backtest")
    print("  uv run python scripts/main.py --help\n")
