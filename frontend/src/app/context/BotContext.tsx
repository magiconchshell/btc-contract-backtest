'use client';

import React, { createContext, useContext, ReactNode } from 'react';
import { useTradingSocket, BotStatus, LogEntry } from '../hooks/useTradingSocket';

interface BotContextType {
  status: BotStatus | null;
  logs: LogEntry[];
  connected: boolean;
}

const BotContext = createContext<BotContextType | undefined>(undefined);

export function BotProvider({ children }: { children: ReactNode }) {
  const socketData = useTradingSocket();

  return (
    <BotContext.Provider value={socketData}>
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
