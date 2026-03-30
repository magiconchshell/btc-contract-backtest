#!/usr/bin/env python3
"""
Contract/futures backtest engine.
Supports leverage and both long/short positions for perpetual-style testing.
"""

import ccxt
import pandas as pd
import numpy as np


class CryptoBacktestEngine:
    def __init__(self, symbol="BTC/USDT", timeframe="1h", leverage=5, initial_capital=10000.0):
        self.symbol = symbol
        self.timeframe = timeframe
        self.leverage = leverage
        self.initial_capital = initial_capital
        self.exchange = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})

    def fetch_historical_data(self, start_date, end_date):
        print(f"📊 Fetching {self.symbol} data...")
        print(f"   Timeframe: {self.timeframe}")
        print(f"   Period: {start_date} to {end_date}")
        since = int(pd.Timestamp(start_date).timestamp() * 1000)
        ohlcv = self.exchange.fetch_ohlcv(self.symbol, timeframe=self.timeframe, since=since, limit=1000)
        rows = list(ohlcv)
        tf_ms = self._parse_timeframe()
        while rows and pd.to_datetime(rows[-1][0], unit="ms") < pd.Timestamp(end_date) and len(rows) < 20000:
            nxt = self.exchange.fetch_ohlcv(self.symbol, timeframe=self.timeframe, since=rows[-1][0] + tf_ms, limit=1000)
            if not nxt:
                break
            rows.extend(nxt)
        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df[df["timestamp"] <= pd.Timestamp(end_date)]
        df.set_index("timestamp", inplace=True)
        print(f"✅ Downloaded {len(df)} candles")
        return df

    def _parse_timeframe(self):
        m = {"1m": 60000, "5m": 300000, "15m": 900000, "30m": 1800000, "1h": 3600000, "4h": 14400000, "1d": 86400000, "7d": 604800000}
        return m.get(self.timeframe, 3600000)

    def simulate_trades(self, df, include_costs=False, cost_model=None, risk_params=None):
        if df is None or "signal" not in df.columns:
            print("⚠️ No valid strategy signals found")
            return None
        print("💹 Simulating contract trades...")
        capital = self.initial_capital
        current_side = 0
        entry_price = None
        entry_time = None
        equity_curve = []
        trades = []
        position_notional = capital * 0.95
        
        for idx, row in df.iterrows():
            price = float(row["close"])
            unrealized = 0.0
            if current_side != 0 and entry_price is not None:
                unrealized = ((price - entry_price) / entry_price) * position_notional * self.leverage * current_side
            equity_curve.append({"timestamp": idx, "close": price, "equity": capital + unrealized, "position": current_side})
            signal = int(row.get("signal", 0))
            if signal == 0:
                continue
            if current_side == 0:
                current_side = signal
                entry_price = price
                entry_time = idx
                position_notional = capital * 0.95
                continue
            if signal != current_side:
                pnl_before = ((price - entry_price) / entry_price) * position_notional * self.leverage * current_side
                total_cost = 0.0
                if include_costs and cost_model:
                    vol = abs((price - entry_price) / entry_price)
                    total_cost = cost_model.estimate_trade_cost(entry_price, price, position_notional, vol, 1)["total_cost"]
                pnl_after = pnl_before - total_cost
                capital += pnl_after
                trades.append({
                    "entry_time": entry_time,
                    "exit_time": idx,
                    "entry_price": entry_price,
                    "exit_price": price,
                    "position": current_side,
                    "pnl_before_costs": pnl_before,
                    "pnl_after_costs": pnl_after,
                    "total_costs": total_cost,
                })
                current_side = signal
                entry_price = price
                entry_time = idx
                position_notional = capital * 0.95
        return {
            "equity_curve": pd.DataFrame(equity_curve),
            "trades": pd.DataFrame(trades),
            "initial_capital": self.initial_capital,
            "final_capital": capital,
        }

    def calculate_metrics(self, results, cost_summary=None):
        if results is None:
            return {}
        equity = results["equity_curve"]["equity"]
        returns = equity.pct_change().dropna()
        total_return = ((results["final_capital"] - results["initial_capital"]) / results["initial_capital"]) * 100
        sharpe = 0 if len(returns) < 2 or returns.std() == 0 else (returns.mean() / returns.std()) * np.sqrt(252)
        dd = ((equity - equity.cummax()) / equity.cummax()).min() * 100 if len(equity) else 0
        trades = results["trades"]
        win_rate = 0 if trades.empty else (len(trades[trades["pnl_after_costs"] > 0]) / len(trades)) * 100
        metrics = {
            "total_return": total_return,
            "sharpe_ratio": sharpe,
            "max_drawdown": dd,
            "win_rate": win_rate,
            "total_trades": len(trades),
            "final_capital": results["final_capital"],
        }
        if cost_summary:
            metrics.update(cost_summary)
        return metrics
