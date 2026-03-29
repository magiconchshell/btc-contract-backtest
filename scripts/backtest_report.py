#!/usr/bin/env python3
"""
Advanced Backtest Report Generation.
Creates comprehensive performance analysis with risk metrics.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import matplotlib.pyplot as plt
import seaborn as sns


class PerformanceMetrics:
    """Calculate comprehensive backtest performance metrics."""
    
    def __init__(self, equity_curve: pd.Series, returns: pd.Series):
        self.equity = equity_curve
        self.returns = returns
    
    def calculate_all(self) -> Dict[str, float]:
        """Calculate all key performance metrics."""
        metrics = {}
        
        # Basic return metrics
        total_return = (self.equity.iloc[-1] / self.equity.iloc[0]) - 1
        metrics['total_return'] = total_return
        
        # Annualized return (assuming 365 days)
        days = len(self.equity)
        annualized_return = ((1 + total_return) ** (365 / days)) - 1 if days > 0 else 0
        metrics['annualized_return'] = annualized_return
        
        # Risk metrics
        volatility = self.returns.std() * np.sqrt(252) if len(self.returns) > 1 else 0
        metrics['volatility'] = volatility
        
        # Sharpe ratio (assuming 0% risk-free rate for crypto)
        if volatility > 0:
            sharpe = (annualized_return / volatility) if annualized_return > 0 else 0
        else:
            sharpe = 0
        metrics['sharpe_ratio'] = sharpe
        
        # Sortino ratio (downside deviation)
        negative_returns = self.returns[self.returns < 0]
        if len(negative_returns) > 1 and negative_returns.std() > 0:
            downside_dev = negative_returns.std() * np.sqrt(252)
            sortino = annualized_return / downside_dev if downside_dev > 0 else 0
        else:
            sortino = 0
        metrics['sortino_ratio'] = sortino
        
        # Maximum Drawdown
        cumulative_max = self.equity.cummax()
        drawdown = (self.equity - cumulative_max) / cumulative_max
        max_dd = drawdown.min()
        metrics['max_drawdown'] = max_dd
        
        # Recovery time (days to recover from max DD)
        recovery_time = self._calculate_recovery_time(max_dd)
        metrics['recovery_days'] = recovery_time
        
        # Win rate
        if len(self.returns) > 0:
            wins = len(self.returns[self.returns > 0])
            win_rate = wins / len(self.returns)
        else:
            win_rate = 0
        metrics['win_rate'] = win_rate
        
        # Profit factor
        gross_profit = self.returns[self.returns > 0].sum()
        gross_loss = abs(self.returns[self.returns < 0].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        metrics['profit_factor'] = profit_factor
        
        # Average win/loss
        avg_win = self.returns[self.returns > 0].mean() if len(self.returns[self.returns > 0]) > 0 else 0
        avg_loss = self.returns[self.returns < 0].mean() if len(self.returns[self.returns < 0]) > 0 else 0
        metrics['avg_win'] = avg_win
        metrics['avg_loss'] = avg_loss
        
        # Consecutive wins/losses
        consec_wins, consec_losses = self._calc_consecutive_streaks()
        metrics['max_consecutive_wins'] = consec_wins
        metrics['max_consecutive_losses'] = consec_losses
        
        return metrics
    
    def _calculate_recovery_time(self, max_dd: float) -> int:
        """Calculate days needed to recover from maximum drawdown."""
        if max_dd == 0:
            return 0
        
        trough_idx = (self.equity - self.equity.cummax()).idxmin()
        recovery_point = self.equity.loc[trough_idx] * (1 - max_dd)
        
        post_trough = self.equity[self.equity.index > trough_idx]
        recovery = post_trough[post_trough >= recovery_point]
        
        if len(recovery) > 0:
            return (recovery.index[0] - trough_idx).days
        return len(self.equity) - trough_idx
    
    def _calc_consecutive_streaks(self) -> tuple[int, int]:
        """Calculate max consecutive wins and losses."""
        if len(self.returns) == 0:
            return 0, 0
        
        signs = np.sign(self.returns.fillna(0)).tolist()
        
        max_consec_win = 0
        max_consec_loss = 0
        current_win = 0
        current_loss = 0
        
        for sign in signs:
            if sign > 0:
                current_win += 1
                current_loss = 0
                max_consec_win = max(max_consec_win, current_win)
            elif sign < 0:
                current_loss += 1
                current_win = 0
                max_consec_loss = max(max_consec_loss, current_loss)
        
        return max_consec_win, max_consec_loss


class BacktestReportGenerator:
    """Generate comprehensive backtest reports with visualizations."""
    
    def __init__(self, results: dict, symbol: str, timeframe: str):
        self.results = results
        self.symbol = symbol
        self.timeframe = timeframe
        self.figures = []
        
    def generate_full_report(self, save_dir: str = './backtest_reports'):
        """Generate complete report with all visualizations."""
        import os
        os.makedirs(save_dir, exist_ok=True)
        
        timestamp = pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')
        
        # Calculate metrics
        equity = self.results['equity_curve']['equity']
        returns = equity.pct_change().dropna()
        
        perf_metrics = PerformanceMetrics(equity, returns)
        metrics_dict = perf_metrics.calculate_all()
        
        # Create multi-page report
        fig = plt.figure(figsize=(20, 15))
        
        # Page 1: Main performance overview
        ax1 = fig.add_subplot(2, 3, 1)
        ax1.plot(equity.index, equity.values, linewidth=2, label='Equity')
        ax1.axhline(y=equity.iloc[0], color='gray', linestyle='--', alpha=0.5)
        ax1.set_title(f'💰 Equity Curve\n{self.symbol} {self.timeframe}')
        ax1.set_ylabel('Account Value (USDT)')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Page 2: Drawdown chart
        ax2 = fig.add_subplot(2, 3, 2)
        cumulative_max = equity.cummax()
        drawdown = (equity - cumulative_max) / cumulative_max * 100
        ax2.fill_between(drawdown.index, drawdown.values, 0, 
                        color='red' if drawdown.min() < 0 else 'green', 
                        alpha=0.5)
        ax2.axhline(y=metrics_dict['max_drawdown'] * 100, color='red', 
                   linestyle='--', alpha=0.7, 
                   label=f'Max DD: {metrics_dict["max_drawdown"]*100:.2f}%')
        ax2.set_title('📉 Drawdown Analysis')
        ax2.set_ylabel('Drawdown (%)')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # Page 3: Trade P&L histogram
        ax3 = fig.add_subplot(2, 3, 3)
        if len(self.results.get('trades', [])) > 0:
            pnl_values = [t['pnl_after_costs'] for t in self.results['trades']]
            ax3.hist(pnl_values, bins=30, color='steelblue', alpha=0.7, edgecolor='black')
            ax3.axvline(x=0, color='black', linestyle='--', alpha=0.5)
            ax3.set_title('💵 Trade P&L Distribution')
            ax3.set_xlabel('P&L (USDT)')
            ax3.set_ylabel('Frequency')
            ax3.grid(True, alpha=0.3)
        
        # Page 4: Monthly returns
        ax4 = fig.add_subplot(2, 3, 4)
        monthly_returns = returns.resample('ME').sum()
        colors = ['green' if x > 0 else 'red' for x in monthly_returns.values]
        ax4.bar(monthly_returns.index, monthly_returns.values, color=colors, alpha=0.7)
        ax4.set_title('📅 Monthly Returns')
        ax4.set_ylabel('Monthly Return')
        ax4.tick_params(axis='x', rotation=45)
        ax4.grid(True, alpha=0.3, axis='y')
        
        # Page 5: Key metrics table
        ax5 = fig.add_subplot(2, 3, 5)
        ax5.axis('off')
        
        metrics_text = (
            f"PERFORMANCE METRICS - {self.symbol} {self.timeframe}\n"
            "="*50 + "\n\n"
            f"Total Return:           {metrics_dict['total_return']*100:>8.2f}%\n"
            f"Annualized Return:      {metrics_dict['annualized_return']*100:>8.2f}%\n"
            f"Volatility (Ann.):      {metrics_dict['volatility']*100:>8.2f}%\n"
            f"Sharpe Ratio:           {metrics_dict['sharpe_ratio']:>8.2f}\n"
            f"Sortino Ratio:          {metrics_dict['sortino_ratio']:>8.2f}\n"
            f"Max Drawdown:           {metrics_dict['max_drawdown']*100:>8.2f}%\n"
            f"Recovery Days:          {metrics_dict['recovery_days']:>8.d}\n"
            f"\nTRADE STATISTICS\n"
            "="*50 + "\n\n"
            f"Win Rate:               {metrics_dict['win_rate']*100:>8.2f}%\n"
            f"Profit Factor:          {metrics_dict['profit_factor']:>8.2f}\n"
            f"Avg Win:                ${metrics_dict['avg_win']:>+8.2f}\n"
            f"Avg Loss:               ${metrics_dict['avg_loss']:>+8.2f}\n"
            f"Max Consecutive Wins:   {metrics_dict['max_consecutive_wins']:>8d}\n"
            f"Max Consecutive Losses: {metrics_dict['max_consecutive_losses']:>8d}\n"
        )
        
        ax5.text(0.1, 0.9, metrics_text, transform=ax5.transAxes, fontsize=11,
                verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        # Page 6: Position timeline
        ax6 = fig.add_subplot(2, 3, 6)
        if len(self.results.get('trades', [])) > 0:
            trades = self.results['trades']
            positions = []
            for _, t in trades.iterrows():
                side = t['position']
                if side > 0:
                    positions.append((t['entry_time'], t['exit_time'], 1, t['pnl_after_costs']))
                elif side < 0:
                    positions.append((t['entry_time'], t['exit_time'], -1, t['pnl_after_costs']))
            
            y_pos = []
            for entry, exit_t, side, pnl in positions:
                y_pos.append(1 if side > 0 else -1)
                
            ax6.bar(range(len(positions)), y_pos, color=['green' if p > 0 else 'red' for p in y_pos], alpha=0.7)
            ax6.set_ylim(-2, 2)
            ax6.set_xticks([])
            ax6.set_yticks([-1, 0, 1])
            ax6.set_yticklabels(['Short', 'None', 'Long'])
            ax6.set_title('🎯 Trade Timeline')
        
        plt.tight_layout()
        
        # Save figure
        filename = f"{save_dir}/{self.symbol.replace('/', '_')}_{timestamp}_report.png"
        plt.savefig(filename, dpi=150, bbox_inches='tight')
        plt.close(fig)
        
        print(f"✅ Full report saved to: {filename}")
        
        return metrics_dict


def print_detailed_report(metrics: Dict[str, float], results: dict, 
                         cost_summary: Optional[dict] = None):
    """Print detailed text report to console."""
    
    print("\n" + "="*70)
    print("📊 COMPREHENSIVE BACKTEST REPORT")
    print("="*70)
    
    print("\n⚡ PERFORMANCE SUMMARY")
    print("-"*70)
    print(f"{'Metric':<25} {'Value':<25}")
    print("-"*70)
    print(f"{'Total Return':<25} {metrics['total_return']*100:>10.2f}%")
    print(f"{'Annualized Return':<25} {metrics['annualized_return']*100:>10.2f}%")
    print(f"{'Volatility (Ann.)':<25} {metrics['volatility']*100:>10.2f}%")
    print(f"{'Sharpe Ratio':<25} {metrics['sharpe_ratio']:>10.2f}")
    print(f"{'Sortino Ratio':<25} {metrics['sortino_ratio']:>10.2f}")
    print(f"{'Max Drawdown':<25} {metrics['max_drawdown']*100:>10.2f}%")
    print(f"{'Recovery Time':<25} {metrics['recovery_days']:>10.0f} days")
    
    print("\n💼 TRADE STATISTICS")
    print("-"*70)
    print(f"{'Metric':<25} {'Value':<25}")
    print("-"*70)
    print(f"{'Total Trades':<25} {results['trades'].shape[0]:>10.0f}")
    print(f"{'Win Rate':<25} {metrics['win_rate']*100:>10.2f}%")
    print(f"{'Profit Factor':<25} {metrics['profit_factor']:>10.2f}")
    print(f"{'Avg Win':<25} ${metrics['avg_win']:>+10.2f}")
    print(f"{'Avg Loss':<25} ${metrics['avg_loss']:>+10.2f}")
    print(f"{'Max Consecutive Wins':<25} {metrics['max_consecutive_wins']:>10.0f}")
    print(f"{'Max Consecutive Losses':<25} {metrics['max_consecutive_losses']:>10.0f}")
    
    if cost_summary:
        print("\n💸 COST ANALYSIS")
        print("-"*70)
        print(f"{'Metric':<25} {'Value':<25}")
        print("-"*70)
        print(f"{'Total Fees':<25} ${cost_summary['total_fees']:>10.2f}")
        print(f"{'Total Slippage':<25} ${cost_summary['total_slippage']:>10.2f}")
        print(f"{'Funding Fees':<25} ${cost_summary['total_funding_fees']:>10.2f}")
        print(f"{'Gross P&L':<25} ${cost_summary['gross_pnl']:>10.2f}")
        print(f"{'Net P&L (after costs)':<25} ${cost_summary['net_pnl']:>10.2f}")
        print(f"{'Cost Impact':<25} ${cost_summary['cost_impact']:>10.2f}")
    
    print("\n" + "="*70)
    print("✨ END OF REPORT")
    print("="*70 + "\n")
