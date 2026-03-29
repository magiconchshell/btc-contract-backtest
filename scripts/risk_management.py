#!/usr/bin/env python3
"""
Advanced Risk Management Module.
Provides position sizing, stop-loss, take-profit, and portfolio risk controls.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class RiskParameters:
    """Configuration for risk management parameters."""
    max_position_size_pct: float = 0.02  # Max 2% of capital per trade
    max_daily_loss_pct: float = 0.05     # Max 5% daily loss
    max_drawdown_limit: float = 0.15     # Stop trading at 15% DD
    stop_loss_pct: Optional[float] = None  # Dynamic SL from ATR or fixed
    take_profit_pct: Optional[float] = None  # TP level
    trailing_stop_pct: Optional[float] = None  # Trailing stop %
    atr_period: int = 14                 # ATR calculation period
    max_open_positions: int = 3          # Max simultaneous positions
    
    @classmethod
    def conservative(cls) -> 'RiskParameters':
        """Conservative risk settings."""
        return cls(
            max_position_size_pct=0.01,
            max_daily_loss_pct=0.02,
            max_drawdown_limit=0.08,
            stop_loss_pct=0.02,
            take_profit_pct=0.04,
            trailing_stop_pct=0.01,
            atr_period=14,
            max_open_positions=2
        )
    
    @classmethod
    def aggressive(cls) -> 'RiskParameters':
        """Aggressive risk settings."""
        return cls(
            max_position_size_pct=0.05,
            max_daily_loss_pct=0.10,
            max_drawdown_limit=0.25,
            stop_loss_pct=0.03,
            take_profit_pct=0.06,
            trailing_stop_pct=0.02,
            atr_period=14,
            max_open_positions=5
        )


class PositionSizer:
    """Calculates optimal position sizes based on risk parameters."""
    
    def __init__(self, params: RiskParameters):
        self.params = params
        
    def calculate_size(
        self, 
        entry_price: float, 
        account_equity: float,
        volatility: float,
        atr_value: float = None
    ) -> dict:
        """
        Calculate position size with risk-based sizing.
        
        Args:
            entry_price: Current price
            account_equity: Current account value
            volatility: Asset volatility
            atr_value: Average True Range (optional)
            
        Returns:
            Dict with calculated size details
        """
        # Base position size
        base_size_usd = account_equity * self.params.max_position_size_pct
        
        # Volatility adjustment - reduce size in high vol
        if volatility > 0:
            vol_adjustment = min(1.0, 0.02 / volatility)  # Scale by vol
        else:
            vol_adjustment = 1.0
            
        # ATR-based sizing if provided
        if atr_value and atr_value > 0:
            # Risk $X per point of ATR
            risk_per_share = atr_value * 0.5  # Half ATR
            if risk_per_share > 0:
                atr_size = (account_equity * 0.01) / risk_per_share  # Risk 1%
            else:
                atr_size = base_size_usd / entry_price
        else:
            atr_size = None
        
        # Choose the more conservative approach
        if atr_size:
            quantity = min(base_size_usd / entry_price, atr_size)
        else:
            quantity = base_size_usd / entry_price * vol_adjustment
        
        size_usd = quantity * entry_price
        
        return {
            'quantity': quantity,
            'size_usd': size_usd,
            'risk_amount': size_usd * self.params.stop_loss_pct if self.params.stop_loss_pct else size_usd * 0.02,
            'vol_adjustment': vol_adjustment
        }


class StopLossManager:
    """Manages stop-loss and take-profit orders."""
    
    def __init__(self, params: RiskParameters):
        self.params = params
        self.trading_stops = {}
        
    def set_stop(self, trade_id: str, entry_price: float, side: str, 
                 atr_value: float = None):
        """
        Set stop-loss and take-profit levels for a trade.
        
        Args:
            trade_id: Unique trade identifier
            entry_price: Entry price
            side: 'long' or 'short'
            atr_value: ATR for dynamic stops (optional)
        """
        stops = {}
        
        if atr_value and self.params.stop_loss_pct is None:
            # ATR-based stop
            stop_buffer = 0.5 * atr_value
        else:
            # Fixed percentage stop
            if self.params.stop_loss_pct:
                if side == 'long':
                    stop_buffer = entry_price * self.params.stop_loss_pct
                else:
                    stop_buffer = entry_price * self.params.stop_loss_pct
            else:
                stop_buffer = entry_price * 0.02  # Default 2%
        
        if side == 'long':
            stops['stop_loss'] = entry_price - stop_buffer
            stops['take_profit'] = entry_price + (stop_buffer * 2)  # 2:1 RR
        else:  # short
            stops['stop_loss'] = entry_price + stop_buffer
            stops['take_profit'] = entry_price - (stop_buffer * 2)
        
        self.trading_stops[trade_id] = stops
        return stops
    
    def check_stop(self, trade_id: str, current_price: float) -> Optional[str]:
        """
        Check if stop-loss or take-profit is triggered.
        
        Returns:
            'stop_loss', 'take_profit', or None
        """
        if trade_id not in self.trading_stops:
            return None
        
        stops = self.trading_stops[trade_id]
        
        sl = stops['stop_loss']
        tp = stops['take_profit']
        
        if current_price <= sl:
            return 'stop_loss'
        elif current_price >= tp:
            return 'take_profit'
        
        return None
    
    def update_trailing_stop(self, trade_id: str, current_price: float, 
                            highest_price: float) -> Optional[float]:
        """
        Update trailing stop based on price movement.
        
        Returns:
            Updated trailing stop price or None
        """
        if not self.params.trailing_stop_pct:
            return None
        
        if trade_id not in self.trading_stops:
            return None
        
        current_stop = self.trading_stops[trade_id]['trailing_stop']
        
        if self.params.trailing_stop_pct:
            new_stop = highest_price * (1 - self.params.trailing_stop_pct)
            
            # Only raise stop, never lower it
            if new_stop > current_stop:
                self.trading_stops[trade_id]['trailing_stop'] = new_stop
                return new_stop
        
        return None


class PortfolioRisk:
    """Monitors and manages overall portfolio risk."""
    
    def __init__(self, params: RiskParameters):
        self.params = params
        self.equity_curve = []
        self.daily_pnls = []
        
    def add_point(self, equity: float, daily_pnl: float):
        """Add a point to equity curve tracking."""
        self.equity_curve.append(equity)
        self.daily_pnls.append(daily_pnl)
        
    def get_current_drawdown(self) -> float:
        """Calculate current drawdown."""
        if not self.equity_curve:
            return 0
        
        cumulative_max = max(self.equity_curve)
        current = self.equity_curve[-1]
        
        if cumulative_max == 0:
            return 0
            
        return (current - cumulative_max) / cumulative_max
    
    def get_max_drawdown(self) -> float:
        """Calculate maximum historical drawdown."""
        if len(self.equity_curve) < 2:
            return 0
        
        cumulative_max = []
        dd = []
        
        running_max = 0
        for eq in self.equity_curve:
            running_max = max(running_max, eq)
            cumulative_max.append(running_max)
            dd.append((eq - running_max) / running_max if running_max != 0 else 0)
        
        return min(dd) if dd else 0
    
    def should_halt_trading(self) -> bool:
        """Check if trading should be halted based on risk limits."""
        current_dd = self.get_current_drawdown()
        max_dd = self.get_max_drawdown()
        
        if abs(max_dd) >= self.params.max_drawdown_limit:
            print(f"⚠️ Max drawdown limit hit: {abs(max_dd)*100:.2f}%")
            return True
        
        # Daily loss check
        if len(self.daily_pnls) >= 1:
            daily_loss = sum(self.daily_pnls[-len(self.daily_pnls):])
            if daily_loss <= -self.params.max_daily_loss_pct:
                print(f"⚠️ Daily loss limit hit")
                return True
        
        return False
    
    def can_open_position(self) -> tuple[bool, str]:
        """Check if we can open a new position."""
        if self.should_halt_trading():
            return False, "Trading halted due to risk limits"
        
        if len(self.equity_curve) >= self.params.max_open_positions:
            return False, f"Max positions ({self.params.max_open_positions}) reached"
        
        return True, "OK"


def apply_risk_controls(trades_df, prices_df, risk_params: RiskParameters):
    """
    Apply risk management controls to backtest results.
    
    Args:
        trades_df: Trade signals DataFrame
        prices_df: OHLCV DataFrame
        risk_params: Risk parameter configuration
        
    Returns:
        Filtered trades DataFrame with risk adjustments
    """
    filtered_trades = []
    pos_counter = 0
    
    for _, row in trades_df.iterrows():
        if row['signal'] == 0:
            continue
            
        # Check position count limit
        if pos_counter >= risk_params.max_open_positions:
            continue
        
        # Add trade
        filtered_trades.append(row)
        pos_counter += 1
        
        # Check exit signal
        if row['exit_signal'] == 1:
            pos_counter -= 1
    
    return pd.DataFrame(filtered_trades)
