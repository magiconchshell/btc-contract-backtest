'use client';

import React, { useEffect, useState } from 'react';
import { useBotContext } from '../app/context/BotContext';
import { getStrategies, startBot, stopBot } from '../app/api';

export default function ControlPanel() {
  const { status, connected } = useBotContext();
  const [strategies, setStrategies] = useState<string[]>([]);
  
  const [formData, setFormData] = useState({
    capital: 1000.0,
    leverage: 5,
    mode: 'PAPER',
    symbol: 'BTC/USDT',
    timeframe: '1h',
    interval_seconds: 15,
    strategy: 'sparse_meta_portfolio'
  });

  useEffect(() => {
    getStrategies().then(setStrategies).catch(console.error);
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: (name === 'capital' || name === 'leverage' || name === 'interval_seconds') 
        ? Number(value) 
        : value
    }));
  };

  const handleStart = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await startBot(formData);
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to start bot');
    }
  };

  const handleStop = async () => {
    try {
      await stopBot();
    } catch (err: any) {
      alert('Failed to stop bot');
    }
  };

  const isRunning = status?.is_running;

  return (
    <div className="panel flex-col full-height control-panel">
      <h2>Engine Control</h2>
      
      <div className={`connection-status ${connected ? 'text-success' : 'text-danger'}`}>
        ● {connected ? 'Connected to Core' : 'Disconnected'}
      </div>

      <form onSubmit={handleStart} className="flex-col gap-md">
        <label>
          <span>Trading Mode</span>
          <select name="mode" value={formData.mode} onChange={handleChange} disabled={isRunning}>
            <option value="PAPER">Mainnet Paper Trading</option>
            <option value="LIVE">Mainnet Guarded Live</option>
            <option value="BACKTEST">Historical Backtest</option>
          </select>
        </label>

        <label>
          <span>Strategy Profile</span>
          <select name="strategy" value={formData.strategy} onChange={handleChange} disabled={isRunning}>
            {strategies.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>

        <div className="flex-row gap-sm">
          <label>
            <span>Capital (USDT)</span>
            <input type="number" name="capital" value={formData.capital} onChange={handleChange} disabled={isRunning} />
          </label>
          <label>
            <span>Leverage</span>
            <input type="number" name="leverage" value={formData.leverage} onChange={handleChange} disabled={isRunning} />
          </label>
        </div>

        <div className="flex-row gap-sm">
          <label>
            <span>Symbol</span>
            <input type="text" name="symbol" value={formData.symbol} onChange={handleChange} disabled={isRunning} />
          </label>
          <label>
            <span>Timeframe</span>
            <input type="text" name="timeframe" value={formData.timeframe} onChange={handleChange} disabled={isRunning} />
          </label>
        </div>

        <div className="actions mt-md flex-col gap-sm">
          {!isRunning ? (
            <button type="submit" className="btn btn-primary" disabled={!connected}>
              🚀 Launch Engine
            </button>
          ) : (
            <button type="button" onClick={handleStop} className="btn btn-danger">
              🛑 Halt Execution
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
