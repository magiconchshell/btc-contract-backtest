'use client';

import React, { useState } from 'react';
import { useBotContext } from './context/BotContext';
import ControlPanel from '@/components/ControlPanel';
import StatusCard from '@/components/StatusCard';
import TradingChart from '@/components/TradingChart';
import LogViewer from '@/components/LogViewer';
import Sidebar from '@/components/Sidebar';

function DashboardContent() {
  const { activeSessionId, activeSession } = useBotContext();

  if (activeSessionId === 'new') {
    return (
      <div className="new-session-view">
        <ControlPanel />
      </div>
    );
  }

  if (!activeSessionId || !activeSession) {
    return (
      <div className="empty-state-view">
        <div className="glass-panel" style={{ padding: '3rem', textAlign: 'center' }}>
          <h2 style={{ marginBottom: '1rem', color: 'var(--accent-base)' }}>Welcome to Magic Conch Shell</h2>
          <p className="text-muted">Select an active session from the sidebar or create a new one to begin monitoring.</p>
        </div>
      </div>
    );
  }

  return (
    <section className="dashboard-main flex-col">
      <div className="status-cards-row">
        <StatusCard />
      </div>
      <div className="chart-wrapper glass-panel">
        <TradingChart />
      </div>
      <footer className="dashboard-footer glass-panel">
        <LogViewer />
      </footer>
    </section>
  );
}

export default function Home() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const { activeSession, connected } = useBotContext();

  const isRunning = activeSession?.status === 'running';
  const mode = activeSession?.config?.mode || 'OFFLINE';

  return (
    <div className={`dashboard-grid ${!isSidebarOpen ? 'sidebar-collapsed' : ''}`}>

      <header className="dashboard-header glass-panel">
        <div className="flex-row items-center gap-md">
          <h1 className="header-logo">⚡ Magic Conch Shell</h1>
          {activeSession && (
            <>
              <div className="header-divider" />
              <div className="header-session-info">
                <span className="session-strat-name">
                  {activeSession.config?.strategy?.replace(/_/g, ' ')}
                </span>
                <span className="session-symbol-name">
                  {activeSession.config?.symbol}
                </span>
              </div>
            </>
          )}
        </div>

        <div className="header-controls">
          <button
            className="sidebar-toggle-btn"
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
          >
            {isSidebarOpen ? '⏹ Hide Panel' : '⚙️ Sessions'}
          </button>
          <div className={`status-badge ${isRunning ? 'running' : 'stopped'}`}>
            <span className="dot" />
            <span>{isRunning ? `${mode} ACTIVE` : `ENGINE ${connected ? 'READY' : 'OFFLINE'}`}</span>
          </div>
        </div>
      </header>

      <aside className="dashboard-sidebar glass-panel">
        <Sidebar />
      </aside>

      <main className="dashboard-content-area">
        <DashboardContent />
      </main>
    </div>
  );
}
