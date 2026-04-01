'use client';

import React, { useEffect, useRef, useState } from 'react';
import { createChart, AreaSeries, LineSeries } from 'lightweight-charts';
import { useBotContext } from '../app/context/BotContext';
import { getStatus, getPerformance, getTrades } from '../app/api';

export default function ReportView() {
  const { activeSessionId } = useBotContext();
  const equityContainerRef = useRef<HTMLDivElement>(null);
  const priceContainerRef = useRef<HTMLDivElement>(null);
  
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!activeSessionId || activeSessionId === 'new') return;
    
    setLoading(true);
    Promise.all([
      getStatus(activeSessionId),
      getPerformance(activeSessionId),
      getTrades(activeSessionId)
    ]).then(([status, perf, trades]) => {
      setData({ status, pf: perf, trades });
      setLoading(false);
    }).catch(err => {
      console.error("Error loading report data", err);
      // Wait, is it `/status` returning 404 because session is gone?
      setLoading(false);
    });
  }, [activeSessionId]);

  useEffect(() => {
    if (loading || !data || !equityContainerRef.current || !priceContainerRef.current) return;

    // Common chart options suitable for PDF (light background, dark text)
    const commonOpts = {
      layout: { background: { type: 'solid', color: '#ffffff' }, textColor: '#475569' },
      grid: { vertLines: { color: '#f1f5f9' }, horzLines: { color: '#f1f5f9' } },
      timeScale: { timeVisible: true, secondsVisible: false },
      handleScroll: false,
      handleScale: false,
    };

    // 1. Equity Chart
    const eqChart = createChart(equityContainerRef.current, commonOpts as any);
    const eqSeries = eqChart.addSeries(AreaSeries, {
      lineColor: '#0ea5e9',
      topColor: 'rgba(14, 165, 233, 0.4)',
      bottomColor: 'rgba(14, 165, 233, 0.05)',
      lineWidth: 2,
    });
    
    if (data.status.equity_curve && data.status.equity_curve.length > 0) {
      const sortedEq = [...data.status.equity_curve].sort((a: any, b: any) => a.time - b.time);
      const uniqueEq: any[] = [];
      let lastTEq = 0;
      sortedEq.forEach((d: any) => {
        if (d.time > lastTEq) { uniqueEq.push(d); lastTEq = d.time; }
      });
      eqSeries.setData(uniqueEq);
      eqChart.timeScale().fitContent();
    }

    // 2. Price Chart (Line Series)
    const pxChart = createChart(priceContainerRef.current, commonOpts as any);
    const pxSeries = pxChart.addSeries(LineSeries, {
      color: '#475569',
      lineWidth: 2,
    });
    
    if (data.status.ohlcv && data.status.ohlcv.length > 0) {
      const closePrices = data.status.ohlcv.map((bar: any) => ({
        time: bar.time,
        value: bar.close
      })).sort((a: any, b: any) => a.time - b.time);
      
      const uniquePx: any[] = [];
      let lastTPx = 0;
      closePrices.forEach((d: any) => {
        if (d.time > lastTPx) { uniquePx.push(d); lastTPx = d.time; }
      });
      pxSeries.setData(uniquePx);
      pxChart.timeScale().fitContent();
    }

    return () => {
      eqChart.remove();
      pxChart.remove();
    };
  }, [data, loading]);

  const handleDownloadPDF = async () => {
    if (!activeSessionId) return;
    try {
      // Dynamic import to avoid SSR issues
      const html2pdfModule = await import('html2pdf.js');
      // @ts-ignore
      const html2pdf = html2pdfModule.default || html2pdfModule;
      
      const element = document.getElementById('pdf-report-document') as HTMLElement;
      if (!element) return;
      
      const opt = {
        margin:       10,
        filename:     `Session_Report_${activeSessionId.substring(0,8)}.pdf`,
        image:        { type: 'jpeg' as const, quality: 0.98 },
        html2canvas:  { scale: 2, useCORS: true },
        jsPDF:        { unit: 'mm' as const, format: 'a4' as const, orientation: 'portrait' as const }
      };
      
      html2pdf().set(opt).from(element).save();
    } catch(err) {
      console.error("PDF generation error", err);
      alert("Failed to compile PDF");
    }
  };

  if (loading) return <div className="report-view-container glass-panel"><div style={{padding: '2rem'}}>Loading report data for {activeSessionId}...</div></div>;
  if (!data) return <div className="report-view-container glass-panel"><div style={{padding: '2rem'}}>Failed to load data for this session.</div></div>;

  const { status, pf, trades } = data;
  const totalPnlStr = pf.total_pnl >= 0 ? `+$${pf.total_pnl.toFixed(2)}` : `-$${Math.abs(pf.total_pnl).toFixed(2)}`;

  return (
    <div className="report-view-container flex-col">
      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', justifyContent: 'flex-end', paddingRight: '1rem' }}>
        <button className="btn btn-primary" onClick={handleDownloadPDF} style={{ padding: '0.5rem 1rem' }}>
          📥 Download PDF Report
        </button>
      </div>

      {/* The Printable Container */}
      <div id="pdf-report-document" className="report-document">
        <div className="report-header">
          <h2 style={{ marginBottom: '8px', fontSize: '1.5rem', fontWeight: 700 }}>Trading Session Performance Report</h2>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: '#64748b', fontSize: '0.85rem' }}>
            <span>ID: {activeSessionId}</span>
            <span>Generated: {new Date().toLocaleString()}</span>
          </div>
          
          <div style={{ marginTop: '1.5rem', display: 'flex', gap: '2rem', flexWrap: 'wrap', backgroundColor: '#f8fafc', padding: '1rem', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
            <div><div className="report-stat-label">SYMBOL</div><div style={{ fontWeight: 600 }}>{status.config?.symbol || '--'}</div></div>
            <div><div className="report-stat-label">MODE</div><div style={{ fontWeight: 600 }}>{status.config?.mode || '--'}</div></div>
            <div><div className="report-stat-label">STRATEGY</div><div style={{ fontWeight: 600 }}>{status.config?.strategy?.replace(/_/g, ' ') || '--'}</div></div>
            <div><div className="report-stat-label">LEVERAGE</div><div style={{ fontWeight: 600 }}>{status.config?.leverage ? `${status.config.leverage}x` : '--'}</div></div>
          </div>
        </div>

        <div className="report-stats-grid">
          <div className="report-stat-card" style={{ backgroundColor: 'rgba(22, 163, 74, 0.05)', borderColor: 'rgba(22, 163, 74, 0.2)' }}>
            <div className="report-stat-label">Net Profit</div>
            <div className={`report-stat-value ${pf.total_pnl >= 0 ? 'positive' : 'negative'}`}>
              {totalPnlStr} ({pf.pnl_pct.toFixed(2)}%)
            </div>
          </div>
          <div className="report-stat-card">
            <div className="report-stat-label">Win Rate</div>
            <div className="report-stat-value">{pf.win_rate}%</div>
          </div>
          <div className="report-stat-card">
            <div className="report-stat-label">Profit Factor</div>
            <div className="report-stat-value">{pf.profit_factor}</div>
          </div>
          <div className="report-stat-card">
            <div className="report-stat-label">Max Drawdown</div>
            <div className="report-stat-value">{pf.max_drawdown_pct}%</div>
          </div>
          <div className="report-stat-card">
            <div className="report-stat-label">Total Trades</div>
            <div className="report-stat-value">{pf.total_trades}</div>
          </div>
        </div>

        <div className="report-chart-box">
          <h3>Account Equity Curve</h3>
          <div ref={equityContainerRef} className="report-chart-container" />
        </div>

        <div className="report-chart-box">
          <h3>Asset Close Price</h3>
          <div ref={priceContainerRef} className="report-chart-container" />
        </div>

        <div style={{ marginTop: '2.5rem' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 600, color: '#334155', marginBottom: '1rem' }}>Executed Trades</h3>
          <table className="report-trade-table">
            <thead>
              <tr>
                <th>Date/Time</th>
                <th>Side</th>
                <th>Entry Price</th>
                <th>Exit Price</th>
                <th>PnL</th>
              </tr>
            </thead>
            <tbody>
              {(!trades || trades.length === 0) ? (
                <tr><td colSpan={5} className="text-muted" style={{ textAlign: 'center', padding: '2rem' }}>No completed trades.</td></tr>
              ) : (
                trades.slice().reverse().map((t: any, i: number) => {
                  const pnl = t.pnl_after_costs || 0;
                  const isLong = t.position === 1;
                  return (
                    <tr key={i}>
                      <td>{new Date(t.exit_time).toLocaleString()}</td>
                      <td className={isLong ? 'trade-long' : 'trade-short'}>{isLong ? 'LONG' : 'SHORT'}</td>
                      <td>${t.entry_price.toFixed(2)}</td>
                      <td>${t.exit_price.toFixed(2)}</td>
                      <td style={{ color: pnl >= 0 ? '#16a34a' : '#dc2626', fontWeight: 600 }}>
                        {pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
