'use client';

import React, { useEffect, useState } from 'react';
import { useBotContext } from '../app/context/BotContext';

function AnimatedNumber({ value, prefix = '', suffix = '', decimals = 2 }: { value: number, prefix?: string, suffix?: string, decimals?: number }) {
  const [prev, setPrev] = useState(value);
  const [flash, setFlash] = useState('');

  useEffect(() => {
    if (value > prev) {
      setFlash('value-flash-up');
    } else if (value < prev) {
      setFlash('value-flash-down');
    }
    setPrev(value);
    
    const timer = setTimeout(() => setFlash(''), 500);
    return () => clearTimeout(timer);
  }, [value, prev]);

  return (
    <span className={flash}>
      {prefix}{(value || 0).toFixed(decimals)}{suffix}
    </span>
  );
}

export default function StatusCard() {
  const { status } = useBotContext();
  
  if (!status) {
    return (
      <div className="text-muted p-4">Waiting for engine state...</div>
    );
  }

  // Use the parsed payload exactly from FastAPI bot_manager.py get_status()
  const mtmEquity = status.capital || 0;
  const unrealizedPnL = status.unrealized_pnl || 0;
  
  const pos = status.position || { side: 0, quantity: 0, entry_price: 0 };
  const side = pos.side;
  const openPosition = pos.quantity;

  const perf = status.performance || {};
  const maxDrawdown = perf.max_drawdown_pct || 0;
  const realizedPnl = perf.total_pnl || 0;
  const winRate = perf.win_rate || 0;
  const profitFactor = perf.profit_factor || 0;
  const totalTrades = perf.total_trades || 0;

  return (
    <>
      <div className="stat-card glass-panel">
        <label>Current Equity</label>
        <div className="stat-value text-primary">
          <AnimatedNumber value={mtmEquity} prefix="$" />
        </div>
      </div>
      
      <div className="stat-card glass-panel">
        <label>Unrealized PnL</label>
        <div className={`stat-value ${unrealizedPnL > 0 ? 'text-success' : unrealizedPnL < 0 ? 'text-danger' : ''}`}>
          <AnimatedNumber value={unrealizedPnL} prefix="$" />
        </div>
      </div>
      
      <div className="stat-card glass-panel">
        <label>Total Realized PnL</label>
        <div className={`stat-value ${realizedPnl > 0 ? 'text-success' : realizedPnl < 0 ? 'text-danger' : ''}`}>
          <AnimatedNumber value={realizedPnl} prefix="$" />
        </div>
      </div>

      <div className="stat-card glass-panel">
        <label>Max Drawdown</label>
        <div className="stat-value text-danger">
          <AnimatedNumber value={maxDrawdown} suffix="%" />
        </div>
      </div>

      <div className="stat-card glass-panel">
        <label>Win Rate</label>
        <div className="stat-value">
          <AnimatedNumber value={winRate} suffix="%" />
        </div>
      </div>

      <div className="stat-card glass-panel">
        <label>Profit Factor</label>
        <div className="stat-value">
          <AnimatedNumber value={profitFactor} decimals={2} />
        </div>
      </div>

      <div className="stat-card glass-panel">
        <label>Total Trades</label>
        <div className="stat-value">
          <AnimatedNumber value={totalTrades} decimals={0} />
        </div>
      </div>
      
      <div className="stat-card glass-panel">
        <label>Open Position</label>
        <div className="stat-value" style={{ fontSize: '1.25rem', display: 'flex', alignItems: 'center' }}>
          {side === 0 ? (
            <span className="text-muted">FLAT</span>
          ) : (
            <span className={side > 0 ? 'text-success' : 'text-danger'}>
              {side > 0 ? 'LONG ' : 'SHORT '} {Math.abs(openPosition).toFixed(4)}
            </span>
          )}
        </div>
      </div>
    </>
  );
}
