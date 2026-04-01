'use client';

import React, { useState } from 'react';
import { BotProvider } from './context/BotContext';
import ControlPanel from '../components/ControlPanel';
import StatusCard from '../components/StatusCard';
import TradingChart from '../components/TradingChart';
import LogViewer from '../components/LogViewer';

export default function Home() {
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  return (
    <BotProvider>
      <div className={`dashboard-grid ${!isSidebarOpen ? 'sidebar-collapsed' : ''}`}>
        <header className="dashboard-header glass-panel">
          <h1>⚡ Antigravity Engine</h1>
          <div className="header-controls">
            <button 
              className="sidebar-toggle-btn" 
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            >
              {isSidebarOpen ? '⏹ Hide Panel' : '⚙️ Settings'}
            </button>
            <div className="status-badge">
              <span className="dot" />
              <span>Dashboard Ready</span>
            </div>
          </div>
        </header>
        
        <aside className="dashboard-sidebar glass-panel">
          <ControlPanel />
        </aside>

        <section className="dashboard-main flex-col">
          <div className="status-cards-row">
            <StatusCard />
          </div>
          <div className="chart-wrapper glass-panel">
            <TradingChart />
          </div>
        </section>

        <footer className="dashboard-footer glass-panel">
          <LogViewer />
        </footer>
      </div>
    </BotProvider>
  );
}
