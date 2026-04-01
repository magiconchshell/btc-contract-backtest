'use client';

import React, { useEffect, useState } from 'react';
import { useBotContext } from '../app/context/BotContext';
import { getStrategies, startBot, runBacktest } from '../app/api';

export default function ControlPanel() {
  const { connected, setActiveSessionId } = useBotContext();
  const [strategies, setStrategies] = useState<string[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  
  const [formData, setFormData] = useState({
    capital: 1000.0,
    leverage: 5,
    mode: 'PAPER',
    symbol: 'BTC/USDT',
    timeframe: '1h',
    interval_seconds: 15,
    days: 30, // For backtesting
    strategy: 'sparse_meta_portfolio'
  });

  useEffect(() => {
    getStrategies().then(setStrategies).catch(console.error);
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: (name === 'capital' || name === 'leverage' || name === 'interval_seconds' || name === 'days') 
        ? Number(value) 
        : value
    }));
  };

  const handleStart = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      if (formData.mode === 'BACKTEST') {
        setIsProcessing(true);
        const result = await runBacktest(formData);
        if (result?.session_id) {
            setActiveSessionId(result.session_id);
        }
        setIsProcessing(false);
      } else {
        setIsProcessing(true);
        const result = await startBot(formData);
        if (result?.session_id) {
            setActiveSessionId(result.session_id);
        }
        setIsProcessing(false);
      }
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to start');
      setIsProcessing(false);
    }
  };

  const isBTMode = formData.mode === 'BACKTEST';

  return (
    <div className="panel flex-col full-height control-panel glass-panel" style={{ maxWidth: '600px', margin: '2rem auto', padding: '2rem' }}>
      <h2>Create New Session</h2>
      <p style={{ color: '#aaa', marginBottom: '1.5rem' }}>Configure a new trading bot or historical backtest.</p>
      
      <div className={`connection-status ${connected ? 'text-success' : 'text-danger'}`} style={{ marginBottom: '1rem' }}>
        ● {connected ? 'Connected to Core' : 'Disconnected'}
      </div>

      <form onSubmit={handleStart} className="flex-col gap-md">
        <label>
          <span>Trading Mode</span>
          <select name="mode" value={formData.mode} onChange={handleChange} disabled={isProcessing}>
            <option value="PAPER">Simulated Trading (Mainnet)</option>
            <option value="LIVE">Guarded Live (Mainnet)</option>
            <option value="BACKTEST">Historical Backtest</option>
          </select>
        </label>

        <label>
          <span>Strategy Profile</span>
          <select name="strategy" value={formData.strategy} onChange={handleChange} disabled={isProcessing}>
            {strategies.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>

        <div className="flex-row gap-sm">
          <label>
            <span>Capital (USDT)</span>
            <input type="number" name="capital" value={formData.capital} onChange={handleChange} disabled={isProcessing} />
          </label>
          <label>
            <span>Leverage</span>
            <input type="number" name="leverage" value={formData.leverage} onChange={handleChange} disabled={isProcessing} />
          </label>
        </div>

        <div className="flex-row gap-sm">
          <label>
            <span>Symbol</span>
            <input type="text" name="symbol" value={formData.symbol} onChange={handleChange} disabled={isProcessing} />
          </label>
          <label>
            <span>Timeframe</span>
            <input type="text" name="timeframe" value={formData.timeframe} onChange={handleChange} disabled={isProcessing} />
          </label>
        </div>

        {isBTMode ? (
          <label>
            <span>Backtest History (Days)</span>
            <input type="number" name="days" value={formData.days} onChange={handleChange} disabled={isProcessing} />
          </label>
        ) : (
          <label>
            <span>Interval (Seconds)</span>
            <input type="number" name="interval_seconds" value={formData.interval_seconds} onChange={handleChange} disabled={isProcessing} />
          </label>
        )}

        <div className="actions mt-md flex-col gap-sm">
          {!isProcessing ? (
            <button type="submit" className="btn btn-primary" disabled={(!connected && !isBTMode)}>
              {isBTMode ? '🔬 Run Backtest' : '🚀 Launch Engine Session'}
            </button>
          ) : (
            <button type="button" className="btn btn-primary" disabled>
              ⏳ Processing...
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
