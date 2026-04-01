'use client';

import React, { useEffect, useState } from 'react';
import { useBotContext } from '../app/context/BotContext';
import { getStrategies, startBot, stopBot, runBacktest } from '../app/api';

export default function ControlPanel() {
  const { status, connected, setBacktestResult, clearBacktestResult } = useBotContext();
  const [strategies, setStrategies] = useState<string[]>([]);
  const [isBacktesting, setIsBacktesting] = useState(false);
  
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
        setIsBacktesting(true);
        clearBacktestResult();
        // ensure bot is logically stopped via API if running, though UI could just ignore it for now
        const result = await runBacktest(formData);
        if (result?.status === 'completed') {
            setBacktestResult(result);
        }
        setIsBacktesting(false);
      } else {
        clearBacktestResult();
        await startBot(formData);
      }
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to start');
      setIsBacktesting(false);
    }
  };

  const handleStop = async () => {
    try {
      await stopBot();
    } catch (err: any) {
      console.error('Failed to stop bot', err);
    }
  };

  const isRunning = status?.status === 'running';
  const isBTMode = formData.mode === 'BACKTEST';

  return (
    <div className="panel flex-col full-height control-panel">
      <h2>Engine Control</h2>
      
      <div className={`connection-status ${connected ? 'text-success' : 'text-danger'}`}>
        ● {connected ? 'Connected to Core' : 'Disconnected'}
      </div>

      <form onSubmit={handleStart} className="flex-col gap-md">
        <label>
          <span>Trading Mode</span>
          <select name="mode" value={formData.mode} onChange={handleChange} disabled={isRunning || isBacktesting}>
            <option value="PAPER">Simulated Trading (Mainnet)</option>
            <option value="LIVE">Guarded Live (Mainnet)</option>
            <option value="BACKTEST">Historical Backtest</option>
          </select>
        </label>

        <label>
          <span>Strategy Profile</span>
          <select name="strategy" value={formData.strategy} onChange={handleChange} disabled={isRunning || isBacktesting}>
            {strategies.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>

        <div className="flex-row gap-sm">
          <label>
            <span>Capital (USDT)</span>
            <input type="number" name="capital" value={formData.capital} onChange={handleChange} disabled={isRunning || isBacktesting} />
          </label>
          <label>
            <span>Leverage</span>
            <input type="number" name="leverage" value={formData.leverage} onChange={handleChange} disabled={isRunning || isBacktesting} />
          </label>
        </div>

        <div className="flex-row gap-sm">
          <label>
            <span>Symbol</span>
            <input type="text" name="symbol" value={formData.symbol} onChange={handleChange} disabled={isRunning || isBacktesting} />
          </label>
          <label>
            <span>Timeframe</span>
            <input type="text" name="timeframe" value={formData.timeframe} onChange={handleChange} disabled={isRunning || isBacktesting} />
          </label>
        </div>

        {isBTMode ? (
          <label>
            <span>Backtest History (Days)</span>
            <input type="number" name="days" value={formData.days} onChange={handleChange} disabled={isRunning || isBacktesting} />
          </label>
        ) : (
          <label>
            <span>Interval (Seconds)</span>
            <input type="number" name="interval_seconds" value={formData.interval_seconds} onChange={handleChange} disabled={isRunning} />
          </label>
        )}

        <div className="actions mt-md flex-col gap-sm">
          {(!isRunning && !isBacktesting) && (
            <button type="submit" className="btn btn-primary" disabled={(!connected && !isBTMode)}>
              {isBTMode ? '🔬 Run Backtest' : '🚀 Launch Engine'}
            </button>
          )}
          {isBacktesting && (
            <button type="button" className="btn btn-primary" disabled>
              ⏳ Processing Backtest...
            </button>
          )}
          {isRunning && (
            <button type="button" onClick={handleStop} className="btn btn-danger">
              🛑 Halt Execution
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
