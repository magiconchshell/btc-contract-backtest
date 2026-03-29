#!/usr/bin/env python3
"""
Main entry point for Bitcoin Contract Backtest System - Phase 4
Professional trading simulation with costs, risk management, and advanced analytics.
"""

import sys
import os
import argparse
from datetime import datetime, timedelta
import pandas as pd

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import all modules
from scripts.backtest_engine import CryptoBacktestEngine
from scripts.strategy_manager import StrategyManager
from scripts.transaction_costs import CostModel
from scripts.risk_management import RiskParameters, PositionSizer
from scripts.backtest_report import BacktestReportGenerator, print_detailed_report


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Bitcoin Contract Trading Backtest System (Phase 4)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic backtest with realistic costs
  python main.py --days 60 --timeframe 1h --include-costs
  
  # With risk management
  python main.py --days 90 --strategy rsi --risk conservative
  
  # Advanced analysis
  python main.py --days 60 --strategy hybrid \
      --config '{"base_strategies": [{"name":"rsi"}, {"name":"macd"}], "required_votes": 1}' \
      --include-costs --risk aggressive --output ./reports/hybrid_test

Cost Options:
  --fee-rate RATE         Trading fee rate (default: 0.0004)
  --slippage BPS          Slippage in basis points (default: 5)
  
Risk Options:
  --risk MODE             Risk level: conservative, aggressive, custom
  --max-pos PERCENT       Max position size % (overrides default)
  --stop-loss PCT         Stop loss percentage
                        """,
        prefix_chars='-+'
    )
    
    # Core parameters
    parser.add_argument('--symbol', type=str, default='BTC/USDT',
                       help='Trading pair symbol')
    parser.add_argument('--days', type=int, default=30,
                       help='Historical days to analyze')
    parser.add_argument('--timeframe', type=str, default='1h', 
                       choices=['1m', '5m', '15m', '30m', '1h', '4h', '1d', '7d'],
                       help='Candle timeframe')
    
    # Strategy settings
    parser.add_argument('--leverage', type=int, default=10,
                       help='Leverage level')
    parser.add_argument('--strategy', type=str, default='sma_cross',
                       help='Strategy to use')
    parser.add_argument('--config', type=str, default=None,
                       help='Strategy config JSON')
    
    # Cost modeling
    parser.add_argument('--include-costs', action='store_true',
                       help='Include transaction cost modeling')
    parser.add_argument('--fee-rate', type=float, default=0.0004,
                       help='Trading fee rate (e.g., 0.0004 = 0.04%)')
    parser.add_argument('--slippage', type=int, default=5,
                       help='Slippage in basis points (100 bps = 1%)')
    
    # Risk management
    parser.add_argument('--risk', type=str, default='custom',
                       choices=['conservative', 'aggressive', 'custom'])
    parser.add_argument('--max-pos', type=float, default=0.02,
                       help='Max position size %')
    parser.add_argument('--stop-loss', type=float, default=None,
                       help='Stop loss %')
    
    # Output options
    parser.add_argument('--optimize', type=str, default=None,
                       help='Run parameter optimization')
    parser.add_argument('--param-grid', type=str, default=None,
                       help='Parameter grid for optimization')
    parser.add_argument('--metric', type=str, default='sharpe',
                       help='Optimization metric')
    parser.add_argument('--output', type=str, default='./backtest_reports',
                       help='Output directory')
    parser.add_argument('--no-plot', action='store_true',
                       help='Skip generating plots')
    
    return parser.parse_args()


def run_backtest(args):
    """Execute complete backtest workflow."""
    
    print("\n" + "="*70)
    print("🎰 BITCOIN CONTRACT BACKTEST SYSTEM (PHASE 4)")
    print("="*70)
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-"*70)
    
    # Initialize components
    engine = CryptoBacktestEngine(
        symbol=args.symbol,
        timeframe=args.timeframe,
        leverage=args.leverage
    )
    
    # Fetch data
    start_date = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')
    
    df = engine.fetch_historical_data(start_date, end_date)
    
    if df is None or len(df) == 0:
        print("❌ Failed to fetch data.")
        return
    
    print(f"\n📊 Data loaded: {len(df)} candles from {start_date} to {end_date}")
    
    # Setup strategy
    from scripts.strategies import get_strategy
    
    config_dict = None
    try:
        import json
        config_dict = json.loads(args.config) if args.config else {}
    except:
        pass
    
    manager = StrategyManager()
    
    if args.optimize:
        print(f"\n🔍 Running parameter optimization for {args.optimize}...")
        
        try:
            import ast
            param_grid = ast.literal_eval(args.param_grid) if args.param_grid else {}
            
            manager.set_strategy(args.optimize, {})
            result_df = manager.run_strategy(df)
            
            from scripts.optimization import optimize_parameters
            best_params, best_score = optimize_parameters(
                manager.current_strategy, result_df, param_grid, args.metric
            )
            
            print(f"✅ Best params: {best_params}, Score: {best_score:.4f}")
            
            # Run with optimized params
            final_config = {**(config_dict or {}), **best_params}
            manager.set_strategy(args.optimize, final_config)
            df_signals = manager.run_strategy(df)
            
        except Exception as e:
            print(f"❌ Optimization failed: {e}")
            import traceback
            traceback.print_exc()
            return
    
    else:
        # Normal backtest
        manager.set_strategy(args.strategy, config_dict or None)
        df_signals = manager.run_strategy(df)
    
    # Setup cost model
    cost_model = None
    if args.include_costs:
        cost_model = CostModel(
            fee_rate=args.fee_rate,
            slippage_base=args.slippage / 10000
        )
        print(f"💸 Transaction costs enabled")
        print(f"   Fee rate: {args.fee_rate*100}% | Slippage: {args.slippage} bps")
    
    # Setup risk parameters
    risk_params = RiskParameters()
    if args.risk == 'conservative':
        risk_params = RiskParameters.conservative()
    elif args.risk == 'aggressive':
        risk_params = RiskParameters.aggressive()
    else:
        risk_params.max_position_size_pct = args.max_pos / 100
        if args.stop_loss:
            risk_params.stop_loss_pct = args.stop_loss / 100
    
    print(f"🛡️  Risk management: {args.risk} mode")
    print(f"   Max position: {args.max_pos}% | Stop loss: {args.stop_loss}%")
    
    # Simulate trades
    print("\n💹 Running trade simulation...")
    results = engine.simulate_trades(
        df_signals, 
        include_costs=args.include_costs,
        cost_model=cost_model,
        risk_params=risk_params
    )
    
    if results is None:
        print("❌ Simulation failed.")
        return
    
    # Calculate metrics
    cost_summary = None
    if args.include_costs and cost_model:
        cost_summary = cost_model.get_cost_summary()
    
    metrics = engine.calculate_metrics(results, cost_summary)
    metrics['initial_capital'] = results['initial_capital']
    
    # Print report
    print_detailed_report(metrics, results.to_dict(), cost_summary)
    
    # Generate visualizations
    if not args.no_plot:
        print("\n📈 Generating reports...")
        
        report_gen = BacktestReportGenerator(results.to_dict(), 
                                            f"{args.symbol}_{args.strategy}",
                                            args.timeframe)
        
        try:
            report_gen.generate_full_report(save_dir=args.output)
        except Exception as e:
            print(f"⚠️ Plot generation warning: {e}")
    
    print(f"\n✨ Backtest completed!")
    print("="*70 + "\n")


def main():
    """Main entry point."""
    args = parse_arguments()
    run_backtest(args)


if __name__ == "__main__":
    main()
