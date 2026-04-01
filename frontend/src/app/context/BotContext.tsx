'use client';

import React, { createContext, useContext, ReactNode, useState } from 'react';
import { useTradingSocket, BotStatus, LogEntry } from '../hooks/useTradingSocket';

interface BotContextType {
  sessionsData: Record<string, BotStatus>;
  logs: LogEntry[];
  connected: boolean;
  activeSessionId: string | null;
  setActiveSessionId: (id: string | null) => void;
  // Get active session helper
  activeSession: BotStatus | null;
}

const BotContext = createContext<BotContextType | undefined>(undefined);

export function BotProvider({ children }: { children: ReactNode }) {
  const { sessionsData, logs, connected } = useTradingSocket();
  const [activeSessionId, setActiveSessionId] = useState<string | null>('new');

  const activeSession = activeSessionId && sessionsData[activeSessionId] 
    ? sessionsData[activeSessionId] 
    : null;

  return (
    <BotContext.Provider 
      value={{ 
        sessionsData, 
        logs, 
        connected, 
        activeSessionId, 
        setActiveSessionId,
        activeSession
      }}
    >
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
