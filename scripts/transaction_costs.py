#!/usr/bin/env python3
"""
Transaction Cost Modeling for Realistic Backtesting.
Includes fees, slippage, and market impact simulation.
"""

from dataclasses import dataclass
from typing import Optional
import numpy as np


@dataclass
class TransactionCost:
    """Represents a single transaction cost."""
    timestamp: str
    entry_price: float
    exit_price: float
    quantity: float
    side: str  # 'long' or 'short'
    fee_rate: float  # Per trade fee rate (e.g., 0.001 = 0.1%)
    slippage_bps: int  # Slippage in basis points (100 bps = 1%)
    
    @property
    def total_fee(self) -> float:
        """Calculate total fees for this transaction."""
        return self.entry_price * self.quantity * self.fee_rate
    
    @property
    def slippage_cost(self) -> float:
        """Calculate slippage cost."""
        return self.entry_price * self.quantity * (self.slippage_bps / 10000)
    
    @property
    def total_cost(self) -> float:
        """Total cost including fees and slippage."""
        return self.total_fee + self.slippage_cost


class CostModel:
    """
    Comprehensive transaction cost modeling for backtesting.
    
    Features:
    - Configurable trading fees
    - Dynamic slippage based on volatility
    - Market impact simulation
    - Overnight funding fees (for perpetual contracts)
    """
    
    def __init__(
        self,
        fee_rate: float = 0.0004,  # 0.04% maker/taker
        slippage_base: float = 0.0005,  # 0.05% base slippage
        slippage_multiplier: float = 1.5,  # Volatility multiplier
        funding_rate_annual: float = 0.10,  # 10% annual funding (configurable)
        min_fee_usd: float = 1.0  # Minimum fee per trade
    ):
        self.fee_rate = fee_rate
        self.slippage_base = slippage_base
        self.slippage_multiplier = slippage_multiplier
        self.funding_rate_annual = funding_rate_annual
        self.min_fee_usd = min_fee_usd
        
        self.transaction_history = []
        
    def calculate_slippage(self, volatility: float) -> float:
        """
        Calculate dynamic slippage based on market volatility.
        
        Args:
            volatility: Asset's recent volatility (daily std dev)
            
        Returns:
            Slippage as decimal (e.g., 0.001 = 0.1%)
        """
        # Base slippage + volatility-based increase
        return self.slippage_base * (1 + volatility * self.slippage_multiplier)
    
    def estimate_trade_cost(
        self, 
        entry_price: float, 
        exit_price: float, 
        quantity: float,
        volatility: float,
        days_held: int = 0
    ) -> dict:
        """
        Estimate total cost for a trade.
        
        Args:
            entry_price: Entry price
            exit_price: Exit price
            quantity: Trade size in quote currency
            volatility: Daily volatility
            days_held: How long position was held
            
        Returns:
            Dict with cost breakdown
        """
        # Entry costs
        entry_fee = max(entry_price * quantity * self.fee_rate, self.min_fee_usd)
        entry_slippage = entry_price * quantity * self.calculate_slippage(volatility)
        
        # Exit costs
        exit_fee = max(exit_price * quantity * self.fee_rate, self.min_fee_usd)
        exit_slippage = exit_price * quantity * self.calculate_slippage(volatility)
        
        # Funding fees (for perpetuals)
        if days_held > 0:
            daily_funding = self.funding_rate_annual / 365
            funding_fee = entry_price * quantity * daily_funding * days_held
        else:
            funding_fee = 0
        
        total_cost = entry_fee + entry_slippage + exit_fee + exit_slippage + funding_fee
        
        return {
            'entry_fee': entry_fee,
            'exit_fee': exit_fee,
            'entry_slippage': entry_slippage,
            'exit_slippage': exit_slippage,
            'funding_fee': funding_fee,
            'total_cost': total_cost,
            'total_cost_pct': (total_cost / (entry_price * quantity)) * 100
        }
    
    def record_transaction(self, entry_price: float, exit_price: float, 
                          quantity: float, pnl_before_costs: float,
                          timestamp: str):
        """Record a completed trade with costs."""
        vol = abs((exit_price - entry_price) / entry_price)  # Simple vol estimate
        days_held = 1  # Simplified
        
        costs = self.estimate_trade_cost(entry_price, exit_price, quantity, vol, days_held)
        
        self.transaction_history.append({
            'timestamp': timestamp,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'quantity': quantity,
            'pnl_before_costs': pnl_before_costs,
            'costs': costs,
            'pnl_after_costs': pnl_before_costs - costs['total_cost']
        })
    
    def get_cost_summary(self) -> dict:
        """Get summary of all recorded transaction costs."""
        if not self.transaction_history:
            return {'message': 'No transactions recorded'}
        
        total_fees = sum(t['costs']['entry_fee'] + t['costs']['exit_fee'] 
                        for t in self.transaction_history)
        total_slippage = sum(t['costs']['entry_slippage'] + t['costs']['exit_slippage']
                            for t in self.transaction_history)
        total_funding = sum(t['costs']['funding_fee'] for t in self.transaction_history)
        total_pnl_loss = sum(t['costs']['total_cost'] for t in self.transaction_history)
        
        gross_pnl = sum(t['pnl_before_costs'] for t in self.transaction_history)
        net_pnl = sum(t['pnl_after_costs'] for t in self.transaction_history)
        
        return {
            'total_trades': len(self.transaction_history),
            'total_fees': total_fees,
            'total_slippage': total_slippage,
            'total_funding_fees': total_funding,
            'gross_pnl': gross_pnl,
            'net_pnl': net_pnl,
            'cost_impact': total_pnl_loss,
            'avg_cost_per_trade': total_pnl_loss / len(self.transaction_history),
            'net_pnl_after_costs': net_pnl
        }


def apply_realistic_costs(trades_df, prices_df, cost_model: CostModel):
    """
    Apply transaction costs to a DataFrame of trades.
    
    Args:
        trades_df: DataFrame with trade entries containing entry_time, exit_time, etc.
        prices_df: DataFrame with OHLCV data indexed by timestamp
        cost_model: CostModel instance
        
    Returns:
        Modified trades_df with adjusted P&L
    """
    adjusted_trades = []
    
    for _, trade in trades_df.iterrows():
        entry_idx = prices_df.index.get_loc(trade['entry_time'])
        exit_idx = prices_df.index.get_loc(trade['exit_time'])
        
        entry_price = trade['entry_price']
        exit_price = trade['exit_price']
        
        # Estimate quantity from capital allocation (assume 1% per trade)
        quantity = entry_price * 0.01  # Simplified
        
        # Calculate P&L before costs
        pnl_before = (exit_price - entry_price) * trade['position'] * quantity
        
        # Get costs
        timestamps = prices_df.index[exit_idx]
        cost_est = cost_model.estimate_trade_cost(
            entry_price, exit_price, quantity, 
            volatility=0.02,  # Assume 2% daily vol
            days_held=exit_idx - entry_idx
        )
        
        pnl_after = pnl_before - cost_est['total_cost']
        
        adjusted_trades.append({
            **trade,
            'pnl_after_costs': pnl_after,
            'total_costs': cost_est['total_cost']
        })
    
    return pd.DataFrame(adjusted_trades)
