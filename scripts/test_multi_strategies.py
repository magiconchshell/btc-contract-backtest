#!/usr/bin/env python3
"""
Simple multi-strategy backtest test for BTC/USDT from 2025-01-01 to now.
Uses 5x leverage, $100 initial capital.
"""

import sys
import os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.backtest_engine import CryptoBacktestEngine
from scripts.strategy_manager import StrategyManager


def run_backtest(display_name, strategy_type, config, symbol, timeframe, days, leverage, capital):
    """Run a single strategy backtest."""
    
    print(f"\n{'='*70}")
    print(f"🧪 Testing: {display_name}")
    print(f"   Type: {strategy_type}")
    print(f"   Config: {config}")
    print(f"{'-'*70}")
    
    # Initialize engine
    engine = CryptoBacktestEngine(symbol=symbol, timeframe=timeframe, leverage=leverage)
    
    # Fetch data
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')
    
    df = engine.fetch_historical_data(start_date, end_date)
    
    if df is None or len(df) < 50:
        print("❌ Insufficient data")
        return None
    
    print(f"✅ Loaded {len(df)} daily candles")
    
    # Setup and run strategy
    manager = StrategyManager()
    manager.set_strategy(strategy_type, config)
    df_signals = manager.run_strategy(df)
    
    n_signals = len(df_signals[df_signals['signal'] != 0])
    print(f"📡 Generated {n_signals} signals")
    
    # Simulate trades with basic parameters
    results = engine.simulate_trades(df_signals)
    
    if results is None:
        print("❌ Simulation failed")
        return None
    
    # Scale for custom capital
    scaling = capital / 10000
    results['equity_curve']['equity'] *= scaling
    results['initial_capital'] = capital
    results['final_capital'] *= scaling
    
    # Calculate metrics
    equity = results['equity_curve']['equity']
    returns = equity.pct_change().dropna()
    
    total_return = ((results['final_capital'] - capital) / capital) * 100
    annualized_return = total_return * (365 / days)
    
    sharpe = 0
    if len(returns) > 1:
        sharpe = (returns.mean() / returns.std()) * np.sqrt(252)
    
    cumulative_max = equity.cummax()
    drawdown = (equity - cumulative_max) / cumulative_max
    max_dd = drawdown.min() * 100
    
    win_rate = 0
    if len(results['trades']) > 0:
        wins = len(results['trades'][results['trades']['pnl_after_costs'] > 0])
        win_rate = (wins / len(results['trades'])) * 100
    
    print(f"\n📊 RESULTS:")
    print(f"   Total Return:    {total_return:.2f}%")
    print(f"   Annualized:      {annualized_return:.2f}%")
    print(f"   Sharpe Ratio:    {sharpe:.2f}")
    print(f"   Max Drawdown:    {max_dd:.2f}%")
    print(f"   Win Rate:        {win_rate:.2f}%")
    print(f"   Trades:          {len(results['trades'])}")
    print(f"   Final Capital:   ${results['final_capital']:.2f}")
    
    return {
        'name': display_name,
        'config': str(config)[:50],
        'return': total_return,
        'sharpe': sharpe,
        'dd': abs(max_dd),
        'winrate': win_rate,
        'trades': len(results['trades']),
        'final_capital': results['final_capital'],
        'signals': n_signals
    }


def main():
    """Run all strategy tests."""
    
    print("\n" + "="*70)
    print("💰 BTC/USDT MULTI-STRATEGY BACKTEST COMPARISON")
    print("="*70)
    print(f"📅 Period: ~458 days (2025-01-01 to {datetime.now().strftime('%Y-%m-%d')})")
    print(f"⚖️ Leverage: 5x | 💵 Capital: $100")
    print("="*70)
    
    # Test configurations
    strategies = [
        ("RSI Mean Reversion", "rsi", {"rsi_period": 14, "threshold_low": 30, "threshold_high": 70}),
        ("MACD Crossover", "macd", {"fast_ema": 12, "slow_ema": 26, "signal_smooth": 9}),
        ("Bollinger Bands", "bollinger", {"bb_period": 20, "bb_std": 2}),
        ("SMA Crossover", "sma_cross", {"short_window": 10, "long_window": 30}),
        ("Hybrid RSI+MACD", "hybrid", {
            "base_strategies": [{"name": "rsi"}, {"name": "macd"}],
            "required_votes": 1
        }),
    ]
    
    results = []
    
    for display_name, strat_type, config in strategies:
        result = run_backtest(display_name, strat_type, config, "BTC/USDT", "1d", 458, 5, 100)
        if result:
            results.append(result)
    
    # Print summary table
    print("\n" + "="*70)
    print("📋 STRATEGY SUMMARY TABLE")
    print("="*70)
    print(f"\n{'Strategy':<25} {'Return':<12} {'Sharpe':<10} {'DD':<10} {'Win%':<8} {'Trades':<8}")
    print("-"*70)
    
    for r in sorted(results, key=lambda x: x['return'], reverse=True):
        print(f"{r['name']:<25} {r['return']:>10.2f}% {r['sharpe']:>8.2f} {r['dd']:>8.2f}% {r['winrate']:>6.1f}% {r['trades']:>8}")
    
    print("-"*70)
    
    # Show final capital progression
    print("\n🎯 FINAL CAPITAL BY STRATEGY ($100 starting)")
    print("-"*70)
    
    for r in sorted(results, key=lambda x: x['final_capital'], reverse=True):
        status = "✅ Profit" if r['return'] > 0 else "❌ Loss"
        print(f"{status} {r['name']:<25} ${r['final_capital']:>10.2f} ({r['return']+100:.2f}%)")
    
    print("="*70)
    
    if results:
        best = max(results, key=lambda x: x['return'])
        print(f"\n🏆 Best Performer: {best['name']} with {best['return']:.2f}% return!")
    
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
