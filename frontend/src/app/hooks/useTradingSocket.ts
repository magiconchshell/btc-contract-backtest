import { useState, useEffect, useCallback, useRef } from 'react';

export interface BotStatus {
  event: string;
  is_running: boolean;
  status?: string;
  bot_id: string | null;
  config: any;
  core: any;
  ohlcv: any[];
  equity_curve?: any[];
  decision_history: any[];
  capital?: number;
  position?: any;
  performance?: any;
  latest_decision?: any;
  unrealized_pnl?: number;
}

export interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  logger: string;
  session_id: string;
}

export function useTradingSocket(url: string = 'ws://localhost:8000/ws') {
  const [sessionsData, setSessionsData] = useState<Record<string, BotStatus>>({});
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    console.log(`📡 Connecting to ${url}...`);
    const ws = new WebSocket(url);

    ws.onopen = () => {
      console.log('✅ WebSocket connected');
      setConnected(true);
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'update') {
          if (data.sessions) setSessionsData(data.sessions);
          if (data.logs && data.logs.length > 0) {
            setLogs((prev) => {
              const newLogs = [...prev, ...data.logs];
              return newLogs.slice(-200); // Keep last 200 logs
            });
          }
        }
      } catch (err) {
        console.error('Error parsing WS message:', err);
      }
    };

    ws.onclose = () => {
      console.log('❌ WebSocket disconnected. Reconnecting...');
      setConnected(false);
      reconnectTimeoutRef.current = setTimeout(connect, 3000);
    };

    ws.onerror = (err) => {
      console.error('WebSocket error:', err);
      ws.close();
    };

    wsRef.current = ws;
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  return { sessionsData, logs, connected };
}
