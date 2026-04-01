'use client';

import React, { useEffect, useRef } from 'react';
import { useBotContext } from '../app/context/BotContext';

export default function LogViewer() {
  const { logs, activeSessionId } = useBotContext();
  const endRef = useRef<HTMLDivElement>(null);

  const filteredLogs = logs.filter(l => 
    l.session_id === activeSessionId || l.session_id === 'system'
  );

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [filteredLogs]);

  return (
    <div className="log-viewer full-height flex-col">
      <div className="log-header">
        <h3>System Operations Log {activeSessionId && activeSessionId !== 'new' ? `[${activeSessionId.substring(0,8)}]` : ''}</h3>
      </div>
      <div className="log-content">
        {filteredLogs.length === 0 ? (
          <div className="text-muted">No logs for this session yet.</div>
        ) : (
          filteredLogs.map((log, i) => {
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
