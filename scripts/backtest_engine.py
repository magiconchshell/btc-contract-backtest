#!/usr/bin/env python3
"""
Bitcoin Contract Trading Backtest Engine - Phase 4
Enhanced with transaction costs, risk management, and professional reporting.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import ccxt
import warnings
warnings.filterwarnings('ignore')


class CryptoBacktestEngine:
    """
    Professional cryptocurrency contract trading backtest engine (Phase 4).
    
    Features:
    - Historical Binance data download
    - Flexible strategy configuration
    - Transaction cost modeling
    - Risk management controls
    - Comprehensive performance analysis
    
    Use when you need realistic backtesting with fees, slippage, and risk controls.
    """
    
    def __init__(self, symbol='BTC/USDT', timeframe='1h', leverage=10):
        """
        Initialize backtest engine.
        
        Args:
            symbol: Trading pair (default: BTC/USDT)
            timeframe: Candle timeframe ('1m', '5m', '1h', '1d', etc.)
            leverage: Default leverage level
        """
        self.symbol = symbol
        self.timeframe = timeframe
        self.leverage = leverage
        
        # Initialize CCXT for Binance
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 2}  # 2 = futures
        })
        
        # Results storage
        self.equity_curve = []
        self.trades = []
        
    def fetch_historical_data(self, start_date, end_date):
        """
        Fetch historical candle data from Binance.
        
        Args:
            start_date: Start date string (YYYY-MM-DD)
            end_date: End date string (YYYY-MM-DD)
            
        Returns:
            DataFrame with OHLCV data
        """
        print(f"📊 Fetching {self.symbol} data...")
        print(f"   Timeframe: {self.timeframe}")
        print(f"   Period: {start_date} to {end_date}")
        
        try:
            ohlcv = self.exchange.fetch_ohlcv(
                symbol=self.symbol,
                timeframe=self.timeframe,
                since=int(pd.Timestamp(start_date).timestamp() * 1000),
                limit=1000
            )
            
            if len(ohlcv) < 1000:
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            else:
                all_data = ohlcv.copy()
                last_ts = ohlcv[-1][0]
                
                while len(all_data) < 10000:
                    new_data = self.exchange.fetch_ohlcv(
                        symbol=self.symbol,
                        timeframe=self.timeframe,
                        since=last_ts + 999 * self._parse_timeframe(),
                        limit=1000
                    )
                    if not new_data:
                        break
                    all_data.extend(new_data)
                    last_ts = new_data[-1][0]
                
                df = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df.index.name = None
            
            print(f"✅ Downloaded {len(df)} candles")
            return df
            
        except Exception as e:
            print(f"❌ Error fetching data: {e}")
            return None
    
    def _parse_timeframe(self):
        """Convert timeframe string to milliseconds."""
        time_map = {
            '1m': 60000, '5m': 300000, '15m': 900000, '30m': 1800000,
            '1h': 3600000, '4h': 14400000, '1d': 86400000, '7d': 604800000
        }
        return time_map.get(self.timeframe, 3600000)
    
    def run_strategy(self, df, strategy_manager):
        """
        Run strategy on price data.
        
        Args:
            df: DataFrame with OHLCV data
            strategy_manager: StrategyManager instance
            
        Returns:
            DataFrame with signals
        """
        if df is None or len(df) < 50:
            print("⚠️ Not enough data for strategy")
            return pd.DataFrame()
        
        print("🤖 Running trading strategy...")
        
        result_df = strategy_manager.run_strategy(df)
        
        return result_df
    
    def simulate_trades(self, df, include_costs=False, cost_model=None, risk_params=None):
        """
        Simulate trades based on strategy signals with risk controls.
        
        Args:
            df: DataFrame with strategy signals
            include_costs: Whether to model transaction costs
            cost_model: CostModel instance for fee/slippage calculation
            risk_params: RiskParameters for position sizing
            
        Returns:
            Results dict with equity curve and trade log
        """
        if df is None or 'signal' not in df.columns:
            print("⚠️ No valid strategy signals found")
            return None
        
        print("💹 Simulating trades with risk controls...")
        
        initial_capital = 10000  # USDT
        capital = initial_capital
        position = 0
        entry_price = 0
        trade_count = 0
        
        equity_curve = []
        trades = []
        
        for i, row in df.iterrows():
            idx = row.name if hasattr(row, 'name') else i
            current_value = capital
            
            equity_curve.append({
                'timestamp': idx,
                'close': row['close'],
                'equity': current_value,
                'position': position
            })
            
            # Check for trade signals
            if row['signal'] != 0:
                if row['signal'] == 1 and position == 0:
                    # Open long position
                    position = 1
                    entry_price = row['close']
                    
                    # Calculate position size with risk management
                    if risk_params:
                        volatility = df['close'].pct_change().std()
                        quantity_calc = risk_params.calculate_size(
                            row['close'], capital, volatility
                        )
                        capital_allocation = quantity_calc['size_usd']
                    else:
                        capital_allocation = capital * 0.01
                    
                    trade_count += 1
                        
                elif row['signal'] == -1 and position == 0:
                    # Open short position  
                    position = -1
                    entry_price = row['close']
                    
                    if risk_params:
                        volatility = df['close'].pct_change().std()
                        quantity_calc = risk_params.calculate_size(
                            row['close'], capital, volatility
                        )
                        capital_allocation = quantity_calc['size_usd']
                    else:
                        capital_allocation = capital * 0.01
                    
                    trade_count += 1
                    
                elif row['signal'] == 0 and position != 0:
                    # Close position
                    pnl_before = (row['close'] - entry_price) * position * capital_allocation / entry_price
                    
                    if include_costs and cost_model:
                        vol = abs((row['close'] - entry_price) / entry_price)
                        days = 1
                        
                        costs = cost_model.estimate_trade_cost(
                            entry_price, row['close'], capital_allocation,
                            vol, days
                        )
                        
                        pnl_after = pnl_before - costs['total_cost']
                        
                        trade_record = {
                            'entry_time': trades[-1]['exit_time'] if trades else idx,
                            'exit_time': idx,
                            'entry_price': entry_price,
                            'exit_price': row['close'],
                            'pnl_before_costs': pnl_before,
                            'pnl_after_costs': pnl_after,
                            'total_costs': costs['total_cost'],
                            'position': position
                        }
                    else:
                        pnl_after = pnl_before
                        trade_record = {
                            'entry_time': trades[-1]['exit_time'] if trades else idx,
                            'exit_time': idx,
                            'entry_price': entry_price,
                            'exit_price': row['close'],
                            'pnl_before_costs': pnl_before,
                            'pnl_after_costs': pnl_after,
                            'total_costs': 0,
                            'position': position
                        }
                    
                    capital += pnl_after
                    trades.append(trade_record)
                    position = 0
        
        return {
            'equity_curve': pd.DataFrame(equity_curve),
            'trades': pd.DataFrame(trades) if trades else pd.DataFrame(),
            'initial_capital': initial_capital,
            'final_capital': capital,
            'trade_count': trade_count
        }
    
    def calculate_metrics(self, results, cost_summary=None):
        """Calculate comprehensive performance metrics."""
        if results is None:
            return {}
        
        equity = results['equity_curve']['equity']
        final_capital = results['final_capital']
        initial_capital = results['initial_capital']
        
        total_return = ((final_capital - initial_capital) / initial_capital) * 100
        
        # Calculate returns series
        returns = equity.pct_change().dropna()
        
        # Sharpe ratio
        if len(returns) > 1:
            sharpe = (returns.mean() / returns.std()) * np.sqrt(252)
        else:
            sharpe = 0
        
        # Max drawdown
        cumulative_max = equity.cummax()
        drawdown = (equity - cumulative_max) / cumulative_max * 100
        max_drawdown = drawdown.min()
        
        # Win rate
        if len(results['trades']) > 0:
            wins = len(results['trades'][results['trades']['pnl_after_costs'] > 0])
            win_rate = (wins / len(results['trades'])) * 100
        else:
            win_rate = 0
        
        metrics = {
            'total_return': total_return,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'total_trades': len(results['trades']),
            'final_capital': final_capital
        }
        
        if cost_summary:
            metrics.update(cost_summary)
        
        return metrics
        """
        Fetch historical candle data from Binance.
        
        Args:
            start_date: Start date string (YYYY-MM-DD)
            end_date: End date string (YYYY-MM-DD)
            
        Returns:
            DataFrame with OHLCV data
        """
        print(f"📊 Fetching {self.symbol} data...")
        print(f"   Timeframe: {self.timeframe}")
        print(f"   Period: {start_date} to {end_date}")
        
        try:
            ohlcv = self.exchange.fetch_ohlcv(
                symbol=self.symbol,
                timeframe=self.timeframe,
                since=int(pd.Timestamp(start_date).timestamp() * 1000),
                limit=1000  # Max per request for some timeframes
            )
            
            # If we need more data, fetch in batches
            if len(ohlcv) < 1000:
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            else:
                # Fetch more data if needed
                all_data = ohlcv.copy()
                last_ts = ohlcv[-1][0]
                
                while len(all_data) < 10000:  # Reasonable max
                    new_data = self.exchange.fetch_ohlcv(
                        symbol=self.symbol,
                        timeframe=self.timeframe,
                        since=last_ts + 999 * self._parse_timeframe(),
                        limit=1000
                    )
                    if not new_data:
                        break
                    all_data.extend(new_data)
                    last_ts = new_data[-1][0]
                
                df = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df.index.name = None
            
            print(f"✅ Downloaded {len(df)} candles")
            return df
            
        except Exception as e:
            print(f"❌ Error fetching data: {e}")
            return None
    
    def _parse_timeframe(self):
        """Convert timeframe string to milliseconds."""
        time_map = {
            '1m': 60000, '5m': 300000, '15m': 900000, '30m': 1800000,
            '1h': 3600000, '4h': 14400000, '1d': 86400000, '7d': 604800000
        }
        return time_map.get(self.timeframe, 3600000)
    
    def run_basic_strategy(self, df):
        """
        Run strategy (replaces old basic SMA strategy).
        
        This method now delegates to StrategyManager for flexible strategy support.
        Use set_strategy() before running or specify strategy directly in main.py.
        """
        if df is None or len(df) < 50:
            print("⚠️ Not enough data for strategy")
            return pd.DataFrame()
        
        print("🤖 Running trading strategy...")
        
        # Import strategy manager
        from scripts.strategy_manager import StrategyManager
        
        manager = StrategyManager()
        manager.set_strategy('sma_cross')  # Default strategy
        df_with_signals = manager.run_strategy(df)
        
        return df_with_signals
    
    def simulate_trades(self, df):
        """
        Simulate trades based on strategy signals.
        
        Args:
            df: DataFrame with strategy signals (using 'signal' column)
            
        Returns:
            Results with equity curve and trade log
        """
        if df is None or 'signal' not in df.columns:
            print("⚠️ No valid strategy signals found")
            return None
        
        print("💹 Simulating trades...")
        
        initial_capital = 10000  # USDT
        capital = initial_capital
        position = 0  # 0 = none, 1 = long, -1 = short
        entry_price = 0
        
        equity_curve = []
        trades = []
        
        for i, row in enumerate(df.iterrows()):
            idx, data = row
            
            current_value = capital * (1 + (data['close'] / df.iloc[0]['close']) - 1) * self.leverage
            equity_curve.append({
                'timestamp': idx,
                'close': data['close'],
                'equity': current_value,
                'position': position
            })
            
            # Check for trade signals (based on signal column)
            if data['signal'] != 0:
                if data['signal'] == 1 and position == 0:
                    # Open long position
                    position = 1
                    entry_price = data['close']
                
                elif data['signal'] == -1 and position == 0:
                    # Open short position  
                    position = -1
                    entry_price = data['close']
                    
                elif data['signal'] == 0 and position != 0:
                    # Close position
                    pnl = (data['close'] - entry_price) * position * 0.01 * self.leverage
                    capital += pnl
                    trades.append({
                        'entry_time': df.index[i-1] if i > 0 else idx,
                        'exit_time': idx,
                        'entry_price': entry_price,
                        'exit_price': data['close'],
                        'pnl': pnl,
                        'position': position
                    })
                    position = 0
        
        return {
            'equity_curve': pd.DataFrame(equity_curve),
            'trades': pd.DataFrame(trades),
            'initial_capital': initial_capital,
            'final_capital': capital
        }
    
    def calculate_metrics(self, results):
        """Calculate performance metrics."""
        if results is None:
            return {}
        
        equity = results['equity_curve']['equity']
        final_capital = results['final_capital']
        initial_capital = results['initial_capital']
        
        total_return = ((final_capital - initial_capital) / initial_capital) * 100
        
        # Sharpe ratio (simplified)
        returns = equity.pct_change().dropna()
        sharpe = (returns.mean() / returns.std()) * np.sqrt(252) if len(returns) > 1 else 0
        
        # Max drawdown
        cumulative_max = equity.cummax()
        drawdown = (equity - cumulative_max) / cumulative_max * 100
        max_drawdown = drawdown.min()
        
        # Win rate
        if len(results['trades']) > 0:
            wins = len(results['trades'][results['trades']['pnl'] > 0])
            win_rate = (wins / len(results['trades'])) * 100
        else:
            win_rate = 0
        
        return {
            'total_return': total_return,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'total_trades': len(results['trades']),
            'final_capital': final_capital
        }


if __name__ == "__main__":
    # Example usage
    engine = CryptoBacktestEngine(symbol='BTC/USDT', timeframe='1h', leverage=10)
    
    # Fetch data
    df = engine.fetch_historical_data(
        start_date=(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
        end_date=datetime.now().strftime('%Y-%m-%d')
    )
    
    if df is not None:
        # Run strategy
        df_with_signals = engine.run_basic_strategy(df)
        
        # Simulate
        results = engine.simulate_trades(df_with_signals)
        
        if results is not None:
            # Calculate metrics
            metrics = engine.calculate_metrics(results)
            
            print("\n" + "="*60)
            print("📈 BACKTEST RESULTS")
            print("="*60)
            for key, value in metrics.items():
                print(f"{key}: {value:.2f}" if isinstance(value, float) else f"{key}: {value}")
            print("="*60)
