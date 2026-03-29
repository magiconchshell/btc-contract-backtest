#!/usr/bin/env python3
"""
Comprehensive Multi-Strategy Backtest Report.
Tests multiple strategies on historical data and generates comparative analysis.
"""

import sys
import os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.backtest_engine import CryptoBacktestEngine
from scripts.strategy_manager import StrategyManager
from scripts.transaction_costs import CostModel
from scripts.risk_management import RiskParameters
from scripts.backtest_report import PerformanceMetrics, print_detailed_report


def run_single_strategy_test(engine, strategy_name, config_dict, params,
                            start_date, end_date, leverage, initial_capital,
                            include_costs=True, cost_model=None, risk_params=None):
    """Run a single strategy backtest."""
    
    # Fetch data
    df = engine.fetch_historical_data(start_date, end_date)
    
    if df is None or len(df) < 50:
        print(f"❌ {strategy_name}: Insufficient data")
        return None
    
    # Setup strategy
    manager = StrategyManager()
    manager.set_strategy(strategy_name, config_dict or None)
    df_signals = manager.run_strategy(df)
    
    n_signals = len(df_signals[df_signals['signal'] != 0])
    
    # Simulate trades
    results = engine.simulate_trades(
        df_signals,
        include_costs=include_costs,
        cost_model=cost_model,
        risk_params=risk_params
    )
    
    if results is None:
        print(f"❌ {strategy_name}: Simulation failed")
        return None
    
    # Adjust for custom capital
    scaling_factor = initial_capital / 10000
    results['equity_curve']['equity'] *= scaling_factor
    results['initial_capital'] = initial_capital
    results['final_capital'] *= scaling_factor
    
    # Calculate metrics
    equity = results['equity_curve']['equity']
    returns = equity.pct_change().dropna()
    
    perf = PerformanceMetrics(equity, returns)
    metrics = perf.calculate_all()
    
    metrics['strategy_name'] = f"{strategy_name} ({config_dict})"
    metrics['signals_generated'] = n_signals
    metrics['trades_executed'] = len(results['trades'])
    
    cost_summary = None
    if include_costs and cost_model:
        cost_summary = cost_model.get_cost_summary()
        metrics.update(cost_summary)
    
    return {
        'metrics': metrics,
        'results': results,
        'data': df,
        'signals': df_signals,
        'strategy_info': {
            'name': strategy_name,
            'config': config_dict,
            'leverage': leverage,
            'capital': initial_capital
        }
    }


def create_comparison_report(test_results, output_dir='./comparative_reports'):
    """Create comprehensive comparison visualization."""
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Filter valid results
    valid_results = [r for r in test_results if r is not None]
    
    if len(valid_results) < 2:
        print("⚠️ Not enough valid strategies to compare")
        return
    
    plt.style.use('seaborn-v0_8-whitegrid')
    
    # Figure size
    fig = plt.figure(figsize=(20, 20))
    
    # Extract equity curves
    equity_curves = []
    labels = []
    
    for i, result in enumerate(valid_results):
        equity = result['results']['equity_curve']['equity']
        equity_curves.append(equity)
        labels.append(result['strategy_info']['name'].split('(')[0])
    
    # Page 1: Equity Curves Comparison (Top Left)
    ax1 = fig.add_subplot(3, 3, 1)
    colors = ['#2ecc71', '#3498db', '#e74c3c', '#9b59b6', '#f39c12']
    for i, (equity, label) in enumerate(zip(equity_curves, labels)):
        color = colors[i % len(colors)]
        ax1.plot(equity.index, equity.values, linewidth=2, label=label, color=color)
    
    # Initial capital reference
    initial_caps = [result['strategy_info']['capital'] for result in valid_results]
    ax1.axhline(y=initial_caps[0], color='gray', linestyle='--', alpha=0.7, 
               label=f'Initial (${initial_caps[0]:.0f})')
    
    ax1.set_title('💰 Equity Curve Comparison\nMultiple Strategies Over Time', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Account Value (USDT)')
    ax1.legend(loc='best', fontsize=10)
    ax1.grid(True, alpha=0.3)
    
    # Page 2: Final Performance Metrics Bar Chart (Top Middle)
    ax2 = fig.add_subplot(3, 3, 2)
    
    final_caps = [result['results']['final_capital'] for result in valid_results]
    total_returns = [(cap - init) / init * 100 for cap, init in zip(final_caps, initial_caps)]
    
    colors_green = ['#27ae60' if r > 0 else '#e74c3c' for r in total_returns]
    bars = ax2.bar(labels, total_returns, color=colors_green, edgecolor='black', alpha=0.8)
    
    # Add value labels
    for bar, ret in zip(bars, total_returns):
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height,
                f'{ret:.1f}%', ha='center', va='bottom' if height > 0 else 'top',
                fontweight='bold')
    
    ax2.axhline(y=0, color='black', linewidth=1)
    ax2.set_title('📊 Total Return (%) by Strategy', fontsize=14, fontweight='bold')
    ax2.set_ylabel('Return (%)')
    ax2.tick_params(axis='x', rotation=45)
    
    # Page 3: Sharpe Ratio Comparison (Top Right)
    ax3 = fig.add_subplot(3, 3, 3)
    sharpe_ratios = [result['metrics']['sharpe_ratio'] for result in valid_results]
    colors_blue = ['#2980b9' if s > 0 else '#e74c3c' for s in sharpe_ratios]
    bars = ax3.bar(labels, sharpe_ratios, color=colors_blue, edgecolor='black', alpha=0.8)
    
    for bar, sr in zip(bars, sharpe_ratios):
        height = abs(bar.get_height())
        ax3.text(bar.get_x() + bar.get_width()/2., bar.get_height(),
                f'{sr:.2f}' if sr >= 0 else f'-{abs(sr):.2f}',
                ha='center', va='bottom' if sr >= 0 else 'top', fontweight='bold')
    
    ax3.axhline(y=0, color='black', linewidth=1)
    ax3.set_title('📈 Sharpe Ratio Comparison', fontsize=14, fontweight='bold')
    ax3.set_ylabel('Sharpe Ratio')
    ax3.tick_params(axis='x', rotation=45)
    
    # Page 4: Win Rate Comparison (Middle Left)
    ax4 = fig.add_subplot(3, 3, 4)
    win_rates = [result['metrics']['win_rate'] for result in valid_results]
    colors_purple = ['#9b59b6' for _ in win_rates]
    bars = ax4.bar(labels, win_rates, color=colors_purple, edgecolor='black', alpha=0.8)
    
    for bar, wr in zip(bars, win_rates):
        height = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2., height,
                f'{wr:.1f}%', ha='center', va='bottom', fontweight='bold')
    
    ax4.axhline(y=50, color='orange', linestyle='--', alpha=0.7, label='Random Benchmark')
    ax4.set_title('🎯 Win Rate (%) by Strategy', fontsize=14, fontweight='bold')
    ax4.set_ylabel('Win Rate (%)')
    ax4.legend()
    ax4.tick_params(axis='x', rotation=45)
    
    # Page 5: Drawdown Comparison (Middle Center)
    ax5 = fig.add_subplot(3, 3, 5)
    max_drawdowns = [-result['metrics']['max_drawdown'] * 100 for result in valid_results]  # Positive values
    colors_red = ['#c0392b' for _ in max_drawdowns]
    bars = ax5.bar(labels, max_drawdowns, color=colors_red, edgecolor='black', alpha=0.8)
    
    for bar, dd in zip(bars, max_drawdowns):
        height = bar.get_height()
        ax5.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.1f}%', ha='center', va='bottom', fontweight='bold')
    
    ax5.set_title('📉 Maximum Drawdown (%) - Lower is Better', fontsize=14, fontweight='bold')
    ax5.set_ylabel('Drawdown (%)')
    ax5.tick_params(axis='x', rotation=45)
    
    # Page 6: Number of Trades (Middle Right)
    ax6 = fig.add_subplot(3, 3, 6)
    trade_counts = [result['metrics']['total_trades'] for result in valid_results]
    colors_orange = ['#e67e22' for _ in trade_counts]
    bars = ax6.bar(labels, trade_counts, color=colors_orange, edgecolor='black', alpha=0.8)
    
    for bar, tc in zip(bars, trade_counts):
        height = bar.get_height()
        ax6.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(height)}', ha='center', va='bottom', fontweight='bold')
    
    ax6.set_title('🔄 Total Trades Executed', fontsize=14, fontweight='bold')
    ax6.set_ylabel('Number of Trades')
    ax6.tick_params(axis='x', rotation=45)
    
    # Page 7: Signal Generation Count (Bottom Left)
    ax7 = fig.add_subplot(3, 3, 7)
    signal_counts = [result['metrics']['signals_generated'] for result in valid_results]
    colors_teal = ['#1abc9c' for _ in signal_counts]
    bars = ax7.bar(labels, signal_counts, color=colors_teal, edgecolor='black', alpha=0.8)
    
    for bar, sc in zip(bars, signal_counts):
        height = bar.get_height()
        ax7.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(height)}', ha='center', va='bottom', fontweight='bold')
    
    ax7.set_title('📡 Signals Generated by Strategy', fontsize=14, fontweight='bold')
    ax7.set_ylabel('Number of Signals')
    ax7.tick_params(axis='x', rotation=45)
    
    # Page 8: Profit Factor (Bottom Center)
    ax8 = fig.add_subplot(3, 3, 8)
    profit_factors = [result['metrics']['profit_factor'] for result in valid_results]
    colors_gold = ['#f1c40f' if pf >= 1.5 else '#e67e22' for pf in profit_factors]
    bars = ax8.bar(labels, profit_factors, color=colors_gold, edgecolor='black', alpha=0.8)
    
    for bar, pf in zip(bars, profit_factors):
        height = bar.get_height()
        ax8.text(bar.get_x() + bar.get_width()/2., height,
                f'{pf:.2f}', ha='center', va='bottom', fontweight='bold')
    
    ax8.axhline(y=1.0, color='gray', linestyle='--', alpha=0.5, label='Break-even')
    ax8.axhline(y=1.5, color='green', linestyle=':', alpha=0.5, label='Good (≥1.5)')
    ax8.set_title('💵 Profit Factor (Higher is Better)', fontsize=14, fontweight='bold')
    ax8.set_ylabel('Profit Factor')
    ax8.legend(fontsize=9)
    ax8.tick_params(axis='x', rotation=45)
    
    # Page 9: Combined Summary Table (Bottom Right)
    ax9 = fig.add_subplot(3, 3, 9)
    ax9.axis('off')
    
    summary_text = "📋 STRATEGY COMPARISON SUMMARY\n" + "="*50 + "\n\n"
    
    for i, result in enumerate(valid_results):
        m = result['metrics']
        info = result['strategy_info']
        
        entry = (
            f"\n{'─'*50}\n"
            f"{info['name'].upper()}\n"
            f"{info['name']} | Leverage: {info['leverage']}x | Capital: ${info['capital']:.0f}\n"
            f"{info['name']} | Config: {info['config']}\n\n"
            f"{'Performance':<20} {'Value':>15}\n"
            f"{'─'*50}\n"
            f"{'Total Return':<20} {m['total_return']*100:>13.2f}%\n"
            f"{'Annualized Return':<20} {m['annualized_return']*100:>13.2f}%\n"
            f"{'Volatility':<20} {m['volatility']*100:>13.2f}%\n"
            f"{'Sharpe Ratio':<20} {m['sharpe_ratio']:>13.2f}\n"
            f"{'Sortino Ratio':<20} {m['sortino_ratio']:>13.2f}\n"
            f"{'Max Drawdown':<20} {m['max_drawdown']*100:>13.2f}%\n"
            f"{'Recovery Days':<20} {m['recovery_days']:>13.0f}\n\n"
            f"{'Trade Stats':<20} {'Value':>15}\n"
            f"{'─'*50}\n"
            f"{'Total Trades':<20} {int(m['total_trades']):>13.0f}\n"
            f"{'Signals Generated':<20} {int(m['signals_generated']):>13.0f}\n"
            f"{'Win Rate':<20} {m['win_rate']:>13.2f}%\n"
            f"{'Profit Factor':<20} {m['profit_factor']:>13.2f}\n"
            f"{'Avg Win':<20} ${m['avg_win']:>+12.2f}\n"
            f"{'Avg Loss':<20} ${m['avg_loss']:>+12.2f}\n"
            f"{'Consec Wins':<20} {m['max_consecutive_wins']:>13.0f}\n"
            f"{'Consec Losses':<20} {m['max_consecutive_losses']:>13.0f}\n"
        )
        summary_text += entry
    
    ax9.text(0.05, 0.95, summary_text, transform=ax9.transAxes, fontsize=9,
            verticalalignment='top', fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='#f8f8f8', alpha=0.95, edgecolor='#ccc'))
    
    plt.suptitle('BTC/USDT Perpetual Contract - Multi-Strategy Comparative Analysis', 
                fontsize=18, fontweight='bold', y=0.98)
    plt.figtext(0.5, 0.02, 
               f'Date Range: 2025-01-01 to 2026-03-29 (~458 days)\n' +
               f'Leverage: {valid_results[0]["strategy_info"]["leverage"]}x | Initial Capital: ${valid_results[0]["strategy_info"]["capital"]:.0f} USDT',
               ha='center', fontsize=10, style='italic')
    
    plt.tight_layout(rect=[0, 0.05, 1, 0.96])
    
    # Save figure
    filename = f"{output_dir}/btc_backtest_comparison_{timestamp}.png"
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    plt.close(fig)
    
    print(f"\n✅ Comprehensive report saved to: {filename}")
    return filename


def print_strategy_rankings(test_results):
    """Print ranked list of strategies."""
    valid_results = [r for r in test_results if r is not None]
    
    if not valid_results:
        print("\n❌ No valid strategies to rank")
        return
    
    # Rank by different metrics
    rankings = {
        'Total Return': lambda x: x['metrics']['total_return'],
        'Sharpe Ratio': lambda x: x['metrics']['sharpe_ratio'],
        'Win Rate': lambda x: x['metrics']['win_rate'],
        'Profit Factor': lambda x: x['metrics']['profit_factor'],
        'Lower DD': lambda x: x['metrics']['max_drawdown'],  # Reverse for ranking
    }
    
    print("\n" + "="*70)
    print("🏆 STRATEGY RANKINGS")
    print("="*70)
    
    for metric_name, key_func in rankings.items():
        sorted_results = sorted(valid_results, key=key_func, reverse=(metric_name != 'Lower DD'))
        
        print(f"\n🥇 Ranked by {metric_name}:")
        print("-"*70)
        for i, result in enumerate(sorted_results[:3], 1):
            name = result['strategy_info']['name']
            value = key_func(result['metrics'])
            
            if metric_name == 'Lower DD':
                value_display = f"-{abs(value)*100:.2f}%"
            elif 'Return' in metric_name:
                value_display = f"{value*100:.2f}%"
            elif 'Rate' in metric_name:
                value_display = f"{value*100:.2f}%"
            else:
                value_display = f"{value:.2f}"
            
            medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i:2d}."
            print(f"{medal} {i:2d}. {name:<40} {value_display:>12}")
    
    print("="*70)


def main():
    """Execute comprehensive multi-strategy backtest."""
    
    print("\n" + "="*70)
    print("🎰 COMPREHENSIVE MULTI-STRATEGY BACKTEST SYSTEM")
    print("="*70)
    
    # Configuration
    start_date = '2025-01-01'
    end_date = datetime.now().strftime('%Y-%m-%d')
    symbol = 'BTC/USDT'
    timeframe = '1d'  # Daily candles for long-term test
    leverage = 5
    initial_capital = 100  # USDT
    
    print(f"📅 Date Range: {start_date} to {end_date}")
    print(f"🪙 Trading Pair: {symbol}")
    print(f"⚖️ Leverage: {leverage}x")
    print(f"💵 Initial Capital: ${initial_capital}")
    print("-"*70)
    
    # Initialize engine
    engine = CryptoBacktestEngine(symbol=symbol, timeframe=timeframe, leverage=leverage)
    
    # Setup cost model
    cost_model = CostModel(
        fee_rate=0.0004,  # 0.04% per trade
        slippage_base=0.0005,  # 0.05% base slippage
        funding_rate_annual=0.10  # 10% annual funding rate
    )
    
    # Setup risk parameters
    risk_params = RiskParameters.conservative()
    risk_params.max_position_size_pct = 0.05  # 5% per trade for small capital
    
    # Define strategies to test
    strategies_to_test = [
        {
            'name': 'RSI Mean Reversion',
            'type': 'rsi',
            'config': {'rsi_period': 14, 'threshold_low': 30, 'threshold_high': 70}
        },
        {
            'name': 'MACD Momentum',
            'type': 'macd',
            'config': {'fast_ema': 12, 'slow_ema': 26, 'signal_smooth': 9}
        },
        {
            'name': 'Bollinger Bands Volatility',
            'type': 'bollinger',
            'config': {'bb_period': 20, 'bb_std': 2}
        },
        {
            'name': 'SMA Trend Following',
            'type': 'sma_cross',
            'config': {'short_window': 10, 'long_window': 30}
        },
        {
            'name': 'Hybrid (RSI + MACD)',
            'type': 'hybrid',
            'config': {
                'base_strategies': [
                    {'name': 'rsi', 'config': {}},
                    {'name': 'macd', 'config': {}}
                ],
                'required_votes': 1
            }
        },
        {
            'name': 'Conservative Hybrid (2-of-2)',
            'type': 'hybrid',
            'config': {
                'base_strategies': [
                    {'name': 'rsi', 'config': {}},
                    {'name': 'sma_cross', 'config': {}}
                ],
                'required_votes': 2
            }
        },
    ]
    
    print(f"\n🧪 Testing {len(strategies_to_test)} strategies...")
    print("-"*70)
    
    # Run all backtests
    test_results = []
    
    for i, strat_cfg in enumerate(strategies_to_test, 1):
        print(f"\n[{i}/{len(strategies_to_test)}] Testing: {strat_cfg['name']}")
        print("-"*70)
        
        try:
            result = run_single_strategy_test(
                engine=engine,
                strategy_name=strat_cfg['type'],
                config_dict=strat_cfg['config'],
                params=None,
                start_date=start_date,
                end_date=end_date,
                leverage=leverage,
                initial_capital=initial_capital,
                include_costs=True,
                cost_model=cost_model,
                risk_params=risk_params
            )
            
            if result:
                test_results.append(result)
                m = result['metrics']
                print(f"✅ Completed! Return: {m['total_return']*100:.2f}% | Sharpe: {m['sharpe_ratio']:.2f}")
                
        except Exception as e:
            print(f"❌ Failed: {e}")
            import traceback
            traceback.print_exc()
    
    # Print detailed reports
    print("\n" + "="*70)
    print("📊 DETAILED RESULTS FOR EACH STRATEGY")
    print("="*70)
    
    for result in test_results:
        m = result['metrics']
        print("\n" + "-"*70)
        print(f"Strategy: {result['strategy_info']['name']}")
        print("-"*70)
        print(f"Total Return: {m['total_return']*100:.2f}%")
        print(f"Final Capital: ${m['final_capital']:.2f}")
        print(f"Sharpe Ratio: {m['sharpe_ratio']:.2f}")
        print(f"Win Rate: {m['win_rate']:.2f}%")
        print(f"Total Trades: {int(m['total_trades'])}")
        if 'total_fees' in m:
            print(f"Total Fees Paid: ${m['total_fees']:.2f}")
    
    # Generate comparison report
    print("\n" + "="*70)
    print("📈 GENERATING COMPARATIVE VISUAL REPORT")
    print("="*70)
    
    output_dir = './backtest_comparative_reports'
    report_file = create_comparison_report(test_results, output_dir=output_dir)
    
    # Print rankings
    print_strategy_rankings(test_results)
    
    print("\n✨ All backtests completed!")
    print(f"📁 Visual report saved to: {report_file}")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
