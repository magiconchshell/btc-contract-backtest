#!/usr/bin/env python3
"""
Visualization module for backtest results.
Creates beautiful, easy-to-understand charts and graphs.
"""

import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
from datetime import datetime
import os

# Set style
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (14, 8)
plt.rcParams['font.size'] = 10


def create_comprehensive_report(results, metrics, df=None, symbol='BTC/USDT'):
    """
    Create comprehensive visualizations of backtest results.
    
    Args:
        results: Backtest results dict with equity_curve and trades
        metrics: Performance metrics
        df: Original price data DataFrame
        symbol: Trading pair symbol
        
    Returns:
        List of figure objects (can be saved or displayed)
    """
    if results is None:
        print("⚠️ No results to visualize")
        return []
    
    figures = []
    
    # Figure 1: Equity Curve
    fig1, ax1 = plt.subplots(figsize=(14, 6))
    equity = results['equity_curve']
    ax1.plot(equity['timestamp'], equity['equity'], linewidth=2, label='Equity')
    ax1.axhline(y=results['initial_capital'], color='gray', linestyle='--', alpha=0.5, label='Initial Capital')
    ax1.set_xlabel('Date')
    ax1.set_ylabel('Equity (USDT)')
    ax1.set_title(f'💰 Equity Curve - {symbol}')
    ax1.legend()
    plt.xticks(rotation=45)
    fig1.tight_layout()
    figures.append(fig1)
    
    # Figure 2: Drawdown Chart
    fig2, ax2 = plt.subplots(figsize=(14, 6))
    cumulative_max = equity['equity'].cummax()
    drawdown = (equity['equity'] - cumulative_max) / cumulative_max * 100
    ax2.fill_between(drawdown.index, drawdown.values, 0, 
                    color='red' if drawdown.min() < 0 else 'green', 
                    alpha=0.3, label='Drawdown')
    ax2.axhline(y=metrics.get('max_drawdown', 0), color='red', 
               linestyle='--', alpha=0.7, label=f'Max DD: {metrics.get("max_drawdown", 0):.2f}%')
    ax2.set_xlabel('Date')
    ax2.set_ylabel('Drawdown (%)')
    ax2.set_title('📉 Maximum Drawdown Analysis')
    ax2.legend()
    plt.xticks(rotation=45)
    fig2.tight_layout()
    figures.append(fig2)
    
    # Figure 3: Trade Distribution
    if len(results['trades']) > 0:
        fig3, ax3 = plt.subplots(figsize=(12, 6))
        trades_df = results['trades']
        
        # Bar chart of P&L distribution
        colors = ['green' if pnl > 0 else 'red' for pnl in trades_df['pnl']]
        bars = ax3.bar(range(len(trades_df)), trades_df['pnl'], color=colors, alpha=0.7)
        
        # Add zero line
        ax3.axhline(y=0, color='black', linewidth=1)
        
        # Calculate win/loss statistics
        wins = sum(1 for pnl in trades_df['pnl'] if pnl > 0)
        losses = len(trades_df) - wins
        
        ax3.text(0.5, 0.95, f'Wins: {wins} | Losses: {losses}', 
                transform=ax3.transAxes, fontsize=12, fontweight='bold',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        ax3.set_xlabel('Trade Number')
        ax3.set_ylabel('P&L (USDT)')
        ax3.set_title(f'💵 Trade-by-Trade P&L ({len(trades_df)} total trades)')
        plt.xticks(range(len(trades_df)), rotation=45)
        fig3.tight_layout()
        figures.append(fig3)
    
    # Figure 4: Return Distribution
    if len(results['trades']) > 1:
        fig4, ax4 = plt.subplots(figsize=(12, 6))
        
        # Histogram of trade returns
        ax4.hist([trades_df[trades_df['pnl'] > 0]['pnl'], 
                 trades_df[trades_df['pnl'] <= 0]['pnl']], 
                label=['Winning Trades', 'Losing Trades'],
                color=['green', 'red'], alpha=0.6, bins=20)
        
        ax4.axvline(x=0, color='black', linestyle='--', alpha=0.5)
        ax4.set_xlabel('P&L (USDT)')
        ax4.set_ylabel('Frequency')
        ax4.set_title('📊 Trade Return Distribution')
        ax4.legend()
        fig4.tight_layout()
        figures.append(fig4)
    
    # Figure 5: Strategy Signals (if original data available)
    if df is not None and 'sma_short' in df.columns:
        fig5, (ax5a, ax5b) = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
        
        # Price chart with SMAs
        ax5a.plot(df.index, df['close'], label='Price', linewidth=1.5, alpha=0.7)
        ax5a.plot(df.index, df['sma_short'], label='SMA Short (10)', 
                 linestyle='--', linewidth=2)
        ax5a.plot(df.index, df['sma_long'], label='SMA Long (30)', 
                 linestyle='--', linewidth=2)
        ax5a.set_ylabel('Price (USDT)')
        ax5a.set_title(f'📈 Price Action & Moving Averages - {symbol}')
        ax5a.legend(loc='upper left')
        ax5a.grid(True, alpha=0.3)
        
        # Position chart
        ax5b.fill_between(df.index, 0, 1, where=df['signal'] > 0, 
                         color='green', alpha=0.3, label='Long Position')
        ax5b.fill_between(df.index, -1, 0, where=df['signal'] < 0, 
                         color='red', alpha=0.3, label='Short Position')
        ax5b.set_ylabel('Position')
        ax5b.set_xlabel('Date')
        ax5b.set_ylim(-1.5, 1.5)
        ax5b.legend(loc='upper right')
        plt.xticks(rotation=45)
        fig5.tight_layout()
        figures.append(fig5)
    
    return figures


def save_figures(figures, output_dir='./backtest_reports', prefix='backtest'):
    """Save all figures to files."""
    os.makedirs(output_dir, exist_ok=True)
    
    timestamps = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    for i, fig in enumerate(figures):
        filename = f"{prefix}_{timestamps}_{i+1}.png"
        filepath = os.path.join(output_dir, filename)
        fig.savefig(filepath, dpi=150, bbox_inches='tight')
        plt.close(fig)
        print(f"✅ Saved: {filepath}")
    
    return output_dir


def print_summary_table(metrics, symbol='BTC/USDT'):
    """Print a clean summary table."""
    print("\n" + "="*70)
    print(f"🎯 BACKTEST SUMMARY - {symbol}")
    print("="*70)
    
    print(f"\n{'Metric':<25} {'Value':<30}")
    print("-"*70)
    
    if 'total_return' in metrics:
        print(f"{'Total Return':<25} {metrics['total_return']:.2f}%")
    if 'sharpe_ratio' in metrics:
        print(f"{'Sharpe Ratio':<25} {metrics['sharpe_ratio']:.2f}")
    if 'max_drawdown' in metrics:
        print(f"{'Max Drawdown':<25} {metrics['max_drawdown']:.2f}%")
    if 'win_rate' in metrics:
        print(f"{'Win Rate':<25} {metrics['win_rate']:.2f}%")
    if 'total_trades' in metrics:
        print(f"{'Total Trades':<25} {metrics['total_trades']}")
    if 'final_capital' in metrics:
        initial = metrics.get('initial_capital', 10000)
        growth = ((metrics['final_capital'] - initial) / initial * 100)
        print(f"{'Final Capital':<25} ${metrics['final_capital']:.2f} (+{growth:.2f}%)")
    
    print("="*70 + "\n")


if __name__ == "__main__":
    # Test with sample data
    print("This module should be imported and used by main backtest engine.")
