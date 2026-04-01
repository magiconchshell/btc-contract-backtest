'use client';

import React, { useEffect, useRef } from 'react';
import { useBotContext } from '../app/context/BotContext';

export default function LogViewer() {
  const { logs } = useBotContext();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  return (
    <div className="log-viewer full-height flex-col">
      <div className="log-header">
        <h3>System Operations Log</h3>
      </div>
      <div className="log-content">
        {logs.length === 0 ? (
          <div className="text-muted">No logs yet... Waiting for connection.</div>
        ) : (
          logs.map((log, i) => {
            const isError = log.level === 'ERROR' || log.level === 'CRITICAL';
            const isWarn = log.level === 'WARNING';
            const cls = isError ? 'log-error' : isWarn ? 'log-warn' : 'log-info';
            
            return (
              <div key={i} className={`log-entry ${cls}`}>
                <span className="log-time text-muted">
                  {new Date(log.timestamp).toLocaleTimeString()}
                </span>
                <span className="log-level">[{log.level}]</span>
                <span className="log-message">{log.message}</span>
              </div>
            );
          })
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}
