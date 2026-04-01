'use client';

import React from 'react';
import { useBotContext } from '../app/context/BotContext';
import { stopBot, deleteSession } from '../app/api';

export default function Sidebar() {
  const { activeSessionId, setActiveSessionId, sessionsData } = useBotContext();

  const handleStop = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!confirm('Are you sure you want to halt this engine session?')) return;
    try {
      await stopBot(id);
    } catch (err) {
      console.error(err);
      alert('Failed to stop session');
    }
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    if (!confirm('Permanently delete this session and all its data?')) return;
    try {
      await deleteSession(id);
      if (id === activeSessionId) {
        setActiveSessionId('new');
      }
    } catch (err) {
      console.error(err);
      alert('Failed to delete session');
    }
  };

  const getBadgeClass = (mode: string) => {
    switch (mode?.toUpperCase()) {
      case 'PAPER': return 'badge-paper';
      case 'LIVE': return 'badge-live';
      case 'BACKTEST': return 'badge-backtest';
      default: return '';
    }
  };

  return (
    <div className="sidebar-container">
      <h3 className="sidebar-title">Trading Sessions</h3>

      <button
        className={`btn btn-primary ${activeSessionId === 'new' ? 'active' : ''}`}
        style={{ width: '100%', marginBottom: '1.5rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
        onClick={() => setActiveSessionId('new')}
      >
        <span style={{ fontSize: '1.2rem' }}>+</span> Create New
      </button>

      <div className="sessions-list flex-col">
        {Object.entries(sessionsData).length === 0 && (
          <div className="text-muted" style={{ textAlign: 'center', padding: '2rem 1rem', fontSize: '0.875rem' }}>
            No active sessions.<br />Start a new bot to begin.
          </div>
        )}

        {Object.entries(sessionsData)
          .sort((a, b) => (a[1].config?.mode === 'BACKTEST' ? 1 : -1)) // Group live on top
          .map(([id, session]) => {
            const isActive = id === activeSessionId;
            const isRunning = session.status === 'running';
            const mode = session.config?.mode || 'PAPER';

            return (
              <div
                key={id}
                className={`session-item ${isActive ? 'active' : ''}`}
                onClick={() => setActiveSessionId(id)}
              >
                <div className="flex-between" style={{ marginBottom: '6px' }}>
                  <span style={{ fontWeight: '600', fontSize: '0.9rem', color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                    {session.config?.strategy?.split('_').map((w: string) => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}
                  </span>
                  {isRunning && <span className="dot" style={{ backgroundColor: 'var(--success-color)', width: '8px', height: '8px', borderRadius: '50%' }} />}
                </div>

                <div className="flex-between">
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{session.config?.symbol}</span>
                  <span className={`session-badge ${getBadgeClass(mode)}`}>
                    {mode}
                  </span>
                </div>

                {isRunning && mode !== 'BACKTEST' ? (
                  <button
                    className="session-delete-btn"
                    title="Stop Session"
                    onClick={(e) => handleStop(e, id)}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                    </svg>
                  </button>
                ) : (
                  <button
                    className="session-delete-btn"
                    title="Delete Session"
                    onClick={(e) => handleDelete(e, id)}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="3 6 5 6 21 6"></polyline>
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                    </svg>
                  </button>
                )}
              </div>
            );
          })}
      </div>

      <div style={{ marginTop: 'auto', paddingTop: '1rem', borderTop: '1px solid var(--border-color)', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
        <p>© 2026 Magic Conch Shell Engine</p>
        <p>Multi-Session Architecture v2.0</p>
      </div>
    </div>
  );
}
