'use client';

import React, { createContext, useContext, ReactNode, useState } from 'react';
import { useTradingSocket, BotStatus, LogEntry } from '../hooks/useTradingSocket';

interface BotContextType {
  status: BotStatus | null;
  logs: LogEntry[];
  connected: boolean;
  backtestResult: any | null;
  setBacktestResult: (data: any | null) => void;
  clearBacktestResult: () => void;
}

const BotContext = createContext<BotContextType | undefined>(undefined);

export function BotProvider({ children }: { children: ReactNode }) {
  const socketData = useTradingSocket();
  const [backtestResult, setBacktestResult] = useState<any | null>(null);

  const clearBacktestResult = () => setBacktestResult(null);

  return (
    <BotContext.Provider value={{ ...socketData, backtestResult, setBacktestResult, clearBacktestResult }}>
      {children}
    </BotContext.Provider>
  );
}

export function useBotContext() {
  const ctx = useContext(BotContext);
  if (ctx === undefined) {
    throw new Error('useBotContext must be used within a BotProvider');
  }
  return ctx;
}
