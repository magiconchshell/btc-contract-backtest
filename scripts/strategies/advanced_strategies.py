#!/usr/bin/env python3
"""
Advanced Trading Strategies for Bitcoin Contract Backtesting.
Includes RSI, MACD, Bollinger Bands, and custom strategy combinations.
"""

import pandas as pd
import numpy as np
from .strategy_base import BaseStrategy


class SMACrossStrategy(BaseStrategy):
    """
    Simple Moving Average Crossover Strategy
    
    Long when short SMA crosses above long SMA
    Short when short SMA crosses below long SMA
    """
    
    def __init__(self, short_window=10, long_window=30, **kwargs):
        super().__init__(kwargs)
        self.params = {
            'short_window': short_window,
            'long_window': long_window
        }
    
    def get_strategy_name(self) -> str:
        return "SMA_Crossover"
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < self.params['long_window']:
            return df
        
        # Calculate SMAs
        df['sma_short'] = df['close'].rolling(window=self.params['short_window']).mean()
        df['sma_long'] = df['close'].rolling(window=self.params['long_window']).mean()
        
        # Generate signals
        df['signal'] = 0
        
        # Bullish crossover
        bullish = (df['sma_short'] > df['sma_long']) & \
                  (df['sma_short'].shift(1) <= df['sma_long'].shift(1))
        
        # Bearish crossover
        bearish = (df['sma_short'] < df['sma_long']) & \
                  (df['sma_short'].shift(1) >= df['sma_long'].shift(1))
        
        df.loc[bullish, 'signal'] = 1   # Long
        df.loc[bearish, 'signal'] = -1  # Short
        
        return df


class RSIStrategy(BaseStrategy):
    """
    Relative Strength Index (RSI) Reversal Strategy
    
    Long when RSI goes oversold (< threshold_low)
    Short when RSI goes overbought (> threshold_high)
    Exit when RSI returns to neutral
    """
    
    def __init__(self, rsi_period=14, threshold_low=30, threshold_high=70, **kwargs):
        super().__init__(kwargs)
        self.params = {
            'rsi_period': rsi_period,
            'threshold_low': threshold_low,
            'threshold_high': threshold_high
        }
    
    def get_strategy_name(self) -> str:
        return "RSI_Reversal"
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < self.params['rsi_period']:
            return df
        
        # Calculate RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.params['rsi_period']).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.params['rsi_period']).mean()
        
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # Generate signals
        df['signal'] = 0
        
        # Long on oversold bounce
        long_signal = (df['rsi'] < self.params['threshold_low']) & \
                      (df['rsi'].shift(1) <= self.params['threshold_low'])
        
        # Short on overbought rejection
        short_signal = (df['rsi'] > self.params['threshold_high']) & \
                       (df['rsi'].shift(1) >= self.params['threshold_high'])
        
        # Exit signals
        exit_long = df['rsi'] > 50
        exit_short = df['rsi'] < 50
        
        df.loc[long_signal, 'signal'] = 1
        df.loc[short_signal, 'signal'] = -1
        df.loc[df['signal'] == 1 & exit_long, 'signal'] = 0
        df.loc[df['signal'] == -1 & exit_short, 'signal'] = 0
        
        return df


class MACDCrossStrategy(BaseStrategy):
    """
    Moving Average Convergence Divergence (MACD) Crossover Strategy
    
    Long when MACD line crosses above signal line
    Short when MACD line crosses below signal line
    """
    
    def __init__(self, fast_ema=12, slow_ema=26, signal_smooth=9, **kwargs):
        super().__init__(kwargs)
        self.params = {
            'fast_ema': fast_ema,
            'slow_ema': slow_ema,
            'signal_smooth': signal_smooth
        }
    
    def get_strategy_name(self) -> str:
        return "MACD_Crossover"
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < self.params['slow_ema']:
            return df
        
        # Calculate EMAs
        ema_fast = df['close'].ewm(span=self.params['fast_ema'], adjust=False).mean()
        ema_slow = df['close'].ewm(span=self.params['slow_ema'], adjust=False).mean()
        
        # Calculate MACD line
        df['macd'] = ema_fast - ema_slow
        
        # Calculate signal line
        df['signal_line'] = df['macd'].ewm(span=self.params['signal_smooth'], adjust=False).mean()
        
        # Generate signals
        df['strategy_signal'] = 0
        
        # Bullish crossover
        bullish = (df['macd'] > df['signal_line']) & \
                  (df['macd'].shift(1) <= df['signal_line'].shift(1))
        
        # Bearish crossover
        bearish = (df['macd'] < df['signal_line']) & \
                  (df['macd'].shift(1) >= df['signal_line'].shift(1))
        
        df.loc[bullish, 'strategy_signal'] = 1
        df.loc[bearish, 'strategy_signal'] = -1
        
        return df


class BollingerBandsStrategy(BaseStrategy):
    """
    Bollinger Bands Mean Reversion Strategy
    
    Long when price touches lower band and bounces
    Short when price touches upper band and rejects
    """
    
    def __init__(self, bb_period=20, bb_std=2, **kwargs):
        super().__init__(kwargs)
        self.params = {
            'bb_period': bb_period,
            'bb_std': bb_std
        }
    
    def get_strategy_name(self) -> str:
        return "Bollinger_Bands"
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < self.params['bb_period']:
            return df
        
        # Calculate Bollinger Bands
        df['sma'] = df['close'].rolling(window=self.params['bb_period']).mean()
        df['std'] = df['close'].rolling(window=self.params['bb_period']).std()
        
        df['upper_band'] = df['sma'] + (self.params['bb_std'] * df['std'])
        df['lower_band'] = df['sma'] - (self.params['bb_std'] * df['std'])
        
        # Generate signals
        df['signal'] = 0
        
        # Long when price breaks below lower band and reverses up
        long_signal = (df['close'] < df['lower_band']) & \
                      (df['close'].shift(1) >= df['lower_band'].shift(1))
        
        # Short when price breaks above upper band and reverses down
        short_signal = (df['close'] > df['upper_band']) & \
                       (df['close'].shift(1) <= df['upper_band'].shift(1))
        
        # Exit when price returns to mean
        exit_long = df['close'] > df['sma']
        exit_short = df['close'] < df['sma']
        
        df.loc[long_signal, 'signal'] = 1
        df.loc[short_signal, 'signal'] = -1
        df.loc[(df['signal'] == 1) & exit_long, 'signal'] = 0
        df.loc[(df['signal'] == -1) & exit_short, 'signal'] = 0
        
        return df


class HybridStrategy(BaseStrategy):
    """
    Multi-indicator hybrid strategy combining multiple signals.
    
    Requires confirmation from at least N indicators to enter position.
    """
    
    def __init__(self, 
                 strategies=None, 
                 required_confirmations=2,
                 **kwargs):
        super().__init__(kwargs)
        self.strategies = strategies or []
        self.required_confirmations = required_confirmations
        self.params = {
            'strategies': [s.get_strategy_name() for s in self.strategies],
            'required_confirmations': required_confirmations
        }
    
    def get_strategy_name(self) -> str:
        return f"Hybrid_{len(self.strategies)}Indicator"
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.strategies:
            df['signal'] = 0
            return df
        
        # Run all strategies
        df = df.copy()
        df['signal_count'] = 0
        df['negative_signals'] = 0
        
        for strategy in self.strategies:
            strategy_df = strategy.generate_signals(df.copy())
            
            # Count positive signals
            df.loc[strategy_df['signal'] == 1, 'signal_count'] += 1
            
            # Check for conflicting signals
            df.loc[strategy_df['signal'] == -1, 'negative_signals'] += 1
        
        # Enter long if enough confirmations and no negative signals
        df['signal'] = 0
        long_conditions = (df['signal_count'] >= self.required_confirmations) & \
                         (df['negative_signals'] == 0)
        df.loc[long_conditions, 'signal'] = 1
        
        # Enter short similarly
        short_conditions = (df['signal_count'] >= self.required_confirmations) & \
                          (df['positive_signals'] == 0) if 'positive_signals' in df.columns else False
        df.loc[short_conditions, 'signal'] = -1
        
        return df
