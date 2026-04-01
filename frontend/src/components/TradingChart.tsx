'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { createChart, IChartApi, ISeriesApi, Time, CandlestickSeries, AreaSeries, ColorType, createSeriesMarkers } from 'lightweight-charts';
import { useBotContext } from '../app/context/BotContext';
import { getMarkers } from '../app/api';

export default function TradingChart() {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const equityContainerRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  
  const chartRef = useRef<IChartApi | null>(null);
  const equityChartRef = useRef<IChartApi | null>(null);
  
  const candlestickSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const seriesMarkersRef = useRef<any>(null);
  const equitySeriesRef = useRef<ISeriesApi<"Area"> | null>(null);
  
  const [markersData, setMarkersData] = useState<any[]>([]);
  const equityHistoryRef = useRef<{time: Time, value: number}[]>([]);
  const lastPositionSideRef = useRef<number | null>(null);
  
  const { status } = useBotContext();
  const [dataLoaded, setDataLoaded] = useState(false);
  const isSyncing = useRef(false);

  // Initialize Both Charts
  useEffect(() => {
    if (!chartContainerRef.current || !equityContainerRef.current) return;
    
    // 1. Price Chart
    const chart = createChart(chartContainerRef.current, {
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#D1D5DB' },
      grid: { vertLines: { color: 'rgba(255, 255, 255, 0.05)' }, horzLines: { color: 'rgba(255, 255, 255, 0.05)' } },
      timeScale: { 
        timeVisible: true, 
        secondsVisible: false,
      },
      crosshair: { mode: 0 }
    });
    
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981', downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981', wickDownColor: '#ef4444',
    });
    
    // 2. Equity Output
    const equityChart = createChart(equityContainerRef.current, {
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#D1D5DB' },
      grid: { vertLines: { color: 'rgba(255, 255, 255, 0.05)' }, horzLines: { color: 'rgba(255, 255, 255, 0.05)' } },
      timeScale: { 
        timeVisible: true, 
        secondsVisible: false,
      },
      crosshair: { mode: 0 }
    });
    
    const equitySeries = equityChart.addSeries(AreaSeries, {
      topColor: 'rgba(56, 189, 248, 0.4)',
      bottomColor: 'rgba(56, 189, 248, 0.05)',
      lineColor: '#38bdf8',
      lineWidth: 3,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    });

    chartRef.current = chart;
    equityChartRef.current = equityChart;
    candlestickSeriesRef.current = candleSeries;
    seriesMarkersRef.current = createSeriesMarkers(candleSeries);
    equitySeriesRef.current = equitySeries;

    // The User explicitly requested to decouple the synchronization of the two X-axes.
    // Bidirectional event listeners `subscribeVisibleTimeRangeChange` have been removed to prevent the "elastic snapback" infinite loop 
    // caused by mismatching array lengths resolving conflicting visible zoom bounds.

    // Setup dynamic resizing through ResizeObserver to handle flex boundaries automatically
    const resizeObserver = new ResizeObserver(entries => {
      for (let entry of entries) {
        if (entry.target === chartContainerRef.current && chartRef.current) {
          chartRef.current.applyOptions({ 
            width: entry.contentRect.width, 
            height: entry.contentRect.height 
          });
        }
        if (entry.target === equityContainerRef.current && equityChartRef.current) {
          equityChartRef.current.applyOptions({ 
            width: entry.contentRect.width, 
            height: entry.contentRect.height 
          });
        }
      }
    });

    resizeObserver.observe(chartContainerRef.current);
    resizeObserver.observe(equityContainerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      equityChart.remove();
    };
  }, []);

  // Sync Candlesticks and Equity over time
  useEffect(() => {
    if (!status?.ohlcv || !candlestickSeriesRef.current) return;
    
    // Candlesticks
    const chartData = status.ohlcv.map((d: any) => ({
      time: d.time as Time,
      open: parseFloat(d.open),
      high: parseFloat(d.high),
      low: parseFloat(d.low),
      close: parseFloat(d.close),
    }));
    
    chartData.sort((a, b) => (a.time as number) - (b.time as number));
    const uniqueTimeData = chartData.filter((item, index, self) => 
      index === self.findIndex((t) => t.time === item.time)
    );

    // Extract latest Unix Time
    const lastBarTime = uniqueTimeData.length > 0 ? (uniqueTimeData[uniqueTimeData.length - 1].time as number) : Math.floor(Date.now() / 1000);

    // Initial Load - Full Series Set
    if (!dataLoaded && uniqueTimeData.length > 0) {
      candlestickSeriesRef.current.setData(uniqueTimeData);
      
      const mtmEquity = status.capital ? Number(status.capital) : 0;
      if (mtmEquity > 0) {
        const ext = [{ time: lastBarTime as Time, value: mtmEquity }];
        equityHistoryRef.current = ext;
        if (equitySeriesRef.current) equitySeriesRef.current.setData(ext);
      }

      // Initial Viewport Zoom
      // 鎖定當下時間於圖表「正中央」：前 30 根 K 線，後 30 根空白 K 線
      // 注意：不能使用 setVisibleRange (時間)，因為底層庫會強制把未來沒有資料的時間裁切掉 (Clamp) 導致 K 線永遠貼在最右邊。
      // 使用 LogicalRange 才能強迫繪製未來的「空白座標軸」。
      const len = uniqueTimeData.length;
      const lr = {
        from: len - 30,
        to: len + 30
      };
      
      chartRef.current?.timeScale().setVisibleLogicalRange(lr);
      equityChartRef.current?.timeScale().setVisibleLogicalRange(lr);
      
      setDataLoaded(true);
      
    } else if (dataLoaded && uniqueTimeData.length > 0) {
      // Incremental Update - Do not destroy user pan/zoom states
      const lastCandle = uniqueTimeData[uniqueTimeData.length - 1];
      candlestickSeriesRef.current.update(lastCandle);
      
      const mtmEquity = status.capital ? Number(status.capital) : 0;
      if (mtmEquity > 0) {
        const ext = [...equityHistoryRef.current];
        if (ext.length === 0 || lastBarTime > (ext[ext.length - 1].time as number)) {
          ext.push({ time: lastBarTime as Time, value: mtmEquity });
        } else if (lastBarTime === (ext[ext.length - 1].time as number)) {
          ext[ext.length - 1].value = mtmEquity; // update latest tick
        }
        
        // Equity series also receives updates incrementally
        equityHistoryRef.current = ext;
        if (equitySeriesRef.current) equitySeriesRef.current.update(ext[ext.length - 1]);
      }
    }
  }, [status?.ohlcv, status?.capital, dataLoaded]);

  // Fetch Markers Logic
  const fetchAndSetMarkers = useCallback(async () => {
    try {
      if (!candlestickSeriesRef.current) return;
      const data = await getMarkers();
      if (!data || data.length === 0) return;
      setMarkersData(data); // for tooltip

      const markersMap = data.map((m: any) => {
        const isBuy = m.type === 'BUY';
        return {
          time: Number(m.time) as Time,
          position: isBuy ? 'belowBar' : 'aboveBar',
          color: isBuy ? '#10b981' : '#f43f5e',
          shape: 'circle',
          text: m.is_entry ? 'IN' : 'OUT',
          size: 2
        };
      });

      // Filter uniques
      const uniqueMarkers: any[] = [];
      const seen = new Set();
      markersMap.forEach((m: any) => {
        const key = `${m.time}-${m.text}`;
        if (!seen.has(key)) {
          uniqueMarkers.push(m);
          seen.add(key);
        }
      });
      // Sort
      uniqueMarkers.sort((a, b) => (a.time as number) - (b.time as number));
      if (seriesMarkersRef.current) {
        seriesMarkersRef.current.setMarkers(uniqueMarkers);
      }
      
    } catch (err) {
      console.error('Error fetching markers:', err);
    }
  }, []);

  // Poll for Marker updates on position side change
  useEffect(() => {
    const currentSide = status?.position?.side || 0;
    if (lastPositionSideRef.current !== null && lastPositionSideRef.current !== currentSide) {
      fetchAndSetMarkers();
    }
    lastPositionSideRef.current = currentSide;
  }, [status?.position?.side, fetchAndSetMarkers]);

  // Initial markers load
  useEffect(() => {
    fetchAndSetMarkers();
    const iv = setInterval(fetchAndSetMarkers, 10000); // Polled fallback
    return () => clearInterval(iv);
  }, [fetchAndSetMarkers]);

  // Setup React Crosshair Tooltip
  useEffect(() => {
    if (!chartRef.current || !tooltipRef.current || !chartContainerRef.current) return;
    
    chartRef.current.subscribeCrosshairMove((param) => {
      const x = param.point?.x || -1;
      const y = param.point?.y || -1;
      const time = param.time as number;

      if (!param.time || x < 0 || y < 0) {
        tooltipRef.current!.style.display = 'none';
        return;
      }

      // Check for exact matching marker 
      // Marker time is exact Unix seconds, usually lines up identically with candlestick center
      const marker = markersData.find(m => Math.abs(Number(m.time) - time) <= 30); // fuzzy match 30s
      
      if (marker && tooltipRef.current && chartContainerRef.current) {
        tooltipRef.current.style.display = 'block';
        
        const isBuy = marker.type === 'BUY';
        const isEntry = marker.is_entry;
        const pnl = marker.pnl !== undefined ? marker.pnl : 0;
        
        const sideColor = isBuy ? 'text-success' : 'text-danger';
        const pnlColor = pnl >= 0 ? 'text-success' : 'text-danger';
        
        tooltipRef.current.innerHTML = `
          <div style="display:flex; flex-direction:column; gap:6px;">
            <div class="flex-between">
              <span class="text-muted">Type:</span>
              <span class="${sideColor}"><b>${marker.type}</b> [${isEntry ? 'ENTRY' : 'EXIT'}]</span>
            </div>
            <div class="flex-between">
              <span class="text-muted">Price:</span>
              <span><b>$${parseFloat(marker.price).toLocaleString()}</b></span>
            </div>
            <div class="flex-between">
              <span class="text-muted">Qty:</span>
              <span>${parseFloat(marker.qty).toFixed(6)}</span>
            </div>
            ${!isEntry && marker.pnl !== undefined ? `
            <div class="flex-between" style="border-top: 1px solid rgba(255,255,255,0.1); padding-top: 6px; margin-top: 4px;">
              <span class="text-muted">Trade PnL:</span>
              <span class="${pnlColor}"><b>$${pnl.toFixed(2)}</b></span>
            </div>
            ` : ''}
          </div>
        `;
        
        // Position relative to the container
        let left = x + 20;
        let top = y + 20;
        
        if (left > chartContainerRef.current.clientWidth - 220) left = x - 220;
        if (top > chartContainerRef.current.clientHeight - 120) top = y - 120;
        
        tooltipRef.current.style.transform = `translate(${left}px, ${top}px)`;
      } else {
        if (tooltipRef.current) tooltipRef.current.style.display = 'none';
      }
    });
  }, [markersData]);

  return (
    <div className="chart-container-responsive full-height">
      {/* Absolute Tooltip DOM */}
      <div 
        ref={tooltipRef}
        className="glass-panel"
        style={{
          position: 'absolute',
          display: 'none',
          padding: '12px',
          width: '200px',
          zIndex: 100,
          pointerEvents: 'none',
          transition: 'transform 0.1s ease',
          fontSize: '0.85rem'
        }}
      />
      
      {/* Price Candlesticks */}
      <div className="relative full-height" style={{ flex: 2.5, minHeight: 0 }}>
        <h3 className="absolute" style={{ top: 10, left: 10, zIndex: 10, fontSize: '0.9rem', color: 'rgba(255,255,255,0.4)', pointerEvents: 'none' }}>BTC/USDT PRICE CHART</h3>
        <div ref={chartContainerRef} className="full-height" />
        {!dataLoaded && (
          <div className="absolute inset-0 flex-center">
            <div className="text-muted">Awaiting Chart Data...</div>
          </div>
        )}
      </div>

      {/* Equity Area Chart */}
      <div className="relative full-height" style={{ flex: 1, minHeight: 0 }}>
        <h3 className="absolute" style={{ top: 10, left: 10, zIndex: 10, fontSize: '0.9rem', color: 'rgba(255,255,255,0.4)', pointerEvents: 'none' }}>ACCOUNT EQUITY</h3>
        <div ref={equityContainerRef} className="full-height" />
      </div>
    </div>
  );
}
