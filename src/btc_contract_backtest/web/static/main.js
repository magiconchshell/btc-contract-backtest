// Main Javascript for the Trading Engine Dashboard

let priceChart = null;
let priceSeries = null;
let equityChart = null;
let equitySeries = null;
let socket = null;
let initialCapital = 1000;
let isPriceChartInitialized = false;
let lastOhlcvTime = 0;
let lastEquityTime = 0;
let lastPositionSide = 0;
let lastMarkersJSON = ""; // Performance: Cache stringified markers to avoid redundant setMarkers calls
let isSyncing = false; // Performance: Throttle chart sync

// Initialize Dashboard
document.addEventListener('DOMContentLoaded', async () => {
    console.log("DOM Content Loaded. Starting MCS Dashboard...");
    
    try { initTabs(); } catch (e) { console.error("Tabs init failed", e); }
    try { setupEventListeners(); } catch (e) { console.error("Events init failed", e); }
    
    await fetchStrategies();
    
    if (typeof LightweightCharts === 'undefined') {
        alert("Critical: LightweightCharts library failed to load. Please check your internet connection.");
        return;
    }
    
    try { initCharts(); } catch (e) { console.error("Charts init failed", e); }
    try { checkBotStatus(); } catch (e) { console.error("Status check failed", e); }
    try { connectWebSocket(); } catch (e) { console.error("WS connect failed", e); }
});

async function fetchStrategies() {
    try {
        const response = await fetch('/api/strategies');
        const strategies = await response.json();
        const select = document.getElementById('cfg-strategy');
        if (select) {
            select.innerHTML = '';
            strategies.forEach(s => {
                const opt = document.createElement('option');
                opt.value = s;
                let displayName = s.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
                if (s === 'high_frequency_test') {
                    displayName = `[DEBUG] ${displayName}`;
                    opt.style.color = '#fbbf24'; // Warning yellow
                    opt.style.fontWeight = 'bold';
                }
                opt.textContent = displayName;
                if (s === 'sparse_meta_portfolio') opt.selected = true;
                select.appendChild(opt);
            });
        }
    } catch (err) { console.error("Failed to fetch strategies:", err); }
}

function initTabs() {
    const navItems = document.querySelectorAll('.nav-item');
    const views = document.querySelectorAll('.view');
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const target = item.getAttribute('data-view');
            navItems.forEach(i => i.classList.remove('active'));
            views.forEach(v => v.classList.remove('active'));
            item.classList.add('active');
            const targetEl = document.getElementById(target);
            if (targetEl) targetEl.classList.add('active');
            
            if (target === 'dashboard-view') {
                setTimeout(() => {
                    if (priceChart) priceChart.resize(document.getElementById('price-chart').clientWidth, 400);
                    if (equityChart) equityChart.resize(document.getElementById('equity-chart').clientWidth, 250);
                }, 100);
            }
        });
    });
}

function initCharts() {
    console.log("Initializing synchronized dual charts...");
    const priceContainer = document.getElementById('price-chart');
    const equityContainer = document.getElementById('equity-chart');
    if (!priceContainer || !equityContainer) return;

    const commonOptions = {
        layout: {
            background: { type: 'solid', color: 'transparent' },
            textColor: '#e2e8f0', // Brighter labels for visibility
            fontSize: 12,
            fontFamily: "'Inter', sans-serif",
        },
        grid: {
            vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
            horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
        },
        timeScale: { 
            borderColor: 'rgba(255, 255, 255, 0.2)', 
            timeVisible: true, 
            secondsVisible: false,
            autoScale: true,
            rightOffset: 15,
            barSpacing: 10,
            minBarSpacing: 1,
            shiftVisibleRangeOnNewBar: true,
            fixLeftEdge: false,
            borderVisible: true,
        },
        handleScroll: { mouseWheel: true, pressedMouseButton: true },
        handleScale: { axisPressedMouseButton: true, mouseWheel: true, pinch: true },
    };

    // 1. Price K-Line Chart
    priceChart = LightweightCharts.createChart(priceContainer, { ...commonOptions, height: 400 });
    priceSeries = priceChart.addCandlestickSeries({
        upColor: '#10b981', downColor: '#ef4444',
        borderVisible: false,
        wickUpColor: '#10b981', wickDownColor: '#ef4444',
    });

    // 2. Equity Area Chart
    equityChart = LightweightCharts.createChart(equityContainer, { ...commonOptions, height: 250 });
    equitySeries = equityChart.addAreaSeries({
        topColor: 'rgba(56, 189, 248, 0.4)',
        bottomColor: 'rgba(56, 189, 248, 0.05)',
        lineColor: '#38bdf8',
        lineWidth: 3,
        priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    });

    // Sync Logic: MASTER (Price) -> SLAVE (Equity)
    // PERFORMANCE FIX: Throttle using requestAnimationFrame to avoid UI lag during rapid zoom/pan
    priceChart.timeScale().subscribeVisibleTimeRangeChange(range => {
        if (!range || isSyncing) return;
        isSyncing = true;
        requestAnimationFrame(() => {
            equityChart.timeScale().setVisibleRange(range);
            isSyncing = false;
        });
    });

    window.addEventListener('resize', () => {
        if (priceChart) priceChart.resize(priceContainer.clientWidth, 400);
        if (equityChart) equityChart.resize(equityContainer.clientWidth, 250);
    });

    setTimeout(() => {
        if (priceChart) priceChart.resize(priceContainer.clientWidth, 400);
        if (equityChart) equityChart.resize(equityContainer.clientWidth, 250);
    }, 300);
}

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        document.getElementById('service-dot').className = 'dot dot-online';
        document.getElementById('service-text').innerText = 'CONNECTED';
    };

    socket.onclose = () => {
        document.getElementById('service-dot').className = 'dot dot-offline';
        document.getElementById('service-text').innerText = 'DISCONNECTED';
        setTimeout(connectWebSocket, 3000);
    };

    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'update') updateDashboard(data);
    };
}

function updateDashboard(data) {
    const { status, logs } = data;
    
    if (status && status.status === 'running') {
        const statEquity = document.getElementById('stat-equity');
        const statPnl = document.getElementById('stat-pnl');
        const statDrawdown = document.getElementById('stat-drawdown');
        const statPos = document.getElementById('stat-pos');

        if (statEquity) statEquity.textContent = `$${status.capital.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        if (statPnl) {
            const pnl = status.capital - initialCapital;
            const pnlPct = (pnl / initialCapital * 100).toFixed(2);
            statPnl.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)} (${pnlPct}%)`;
            statPnl.style.color = pnl >= 0 ? 'var(--success)' : 'var(--danger)';
        }
        if (statDrawdown) {
            const dd = (status.performance && status.performance.max_drawdown_pct) ? status.performance.max_drawdown_pct : 0;
            statDrawdown.textContent = `${dd.toFixed(2)}%`;
        }
        
        const pos = status.position;
        if (statPos && pos) {
            const posSide = pos.side === 0 ? 'FLAT' : (pos.side === 1 ? 'LONG' : 'SHORT');
            statPos.textContent = `${posSide} ${pos.quantity ? pos.quantity.toFixed(4) : ''}`;
            statPos.style.color = pos.side === 0 ? 'var(--text-primary)' : (pos.side === 1 ? 'var(--success)' : 'var(--danger)');
        }

        // Check if position or trades changed to trigger marker refresh
    const currentSide = status.position ? status.position.side : 0;
    if (typeof lastPositionSide !== 'undefined' && lastPositionSide !== currentSide) {
        console.log("Position changed, refreshing markers...");
        refreshTradeMarkers();
    }
    lastPositionSide = currentSide;

    // --- Price & Equity Data Handling ---
        if (status.ohlcv && status.ohlcv.length > 0 && priceSeries) {
            if (!isPriceChartInitialized) {
                // First time: Load full history
                console.log("Initializing price chart with", status.ohlcv.length, "bars");
                priceSeries.setData(status.ohlcv);
                isPriceChartInitialized = true;
                lastOhlcvTime = Number(status.ohlcv[status.ohlcv.length - 1].time);
                
                // Ensure we see the full history on initial load
                setTimeout(() => {
                    priceChart.timeScale().fitContent();
                }, 100);
            } else {
                // Subsequent: Incremental update
                // Since ohlcv contains up to 500 bars, we loop through to catch missed bars
                const currentData = status.ohlcv;
                let updatedCount = 0;
                for (let i = 0; i < currentData.length; i++) {
                    const bar = currentData[i];
                    const barTime = Number(bar.time);
                    if (barTime >= lastOhlcvTime) {
                        priceSeries.update({ ...bar, time: barTime });
                        lastOhlcvTime = barTime;
                        updatedCount++;
                    }
                }
                if (updatedCount > 0) {
                    // console.log("Updated", updatedCount, "bars incremental");
                }
            }
        }

        if (equitySeries && typeof status.capital === 'number') {
            const timePoint = lastOhlcvTime || Math.floor(Date.now() / 1000);
            const fixedTime = Number(timePoint);
            // ONLY update if it's the same or newer to avoid Lightweight Charts crash
            if (fixedTime >= lastEquityTime) {
                equitySeries.update({ time: fixedTime, value: parseFloat(status.capital) });
                lastEquityTime = fixedTime;
            }
        }

        // 4. Update Strategy Insights
        if (status.latest_decision) {
            updateStrategyInsights(status.latest_decision);
        }
    }

    if (logs && logs.length > 0) {
        const logList = document.getElementById('log-list');
        logs.forEach(log => {
            appendLog(logList, log);
            // Trigger markers refresh on fills
            if (log.message.includes('filled') || log.message.includes('executed') || log.message.includes('Position')) {
                setTimeout(refreshTradeMarkers, 500);
            }
        });
        const logCount = document.getElementById('log-count');
        if (logCount) logCount.innerText = `${logList.children.length} entries`;
    }
}

function updateStrategyInsights(decision) {
    const indicator = document.getElementById('signal-indicator');
    const signalLabel = document.getElementById('signal-text');
    const decisionText = document.getElementById('decision-text');
    
    if (!indicator || !signalLabel || !decisionText) return;

    // 1. Determine Signal Status
    const sig = decision.signal !== undefined ? decision.signal : 0;
    indicator.className = 'signal-dot';
    if (sig > 0) {
        indicator.classList.add('long');
        signalLabel.innerText = 'LONG';
        signalLabel.style.color = '#10b981';
    } else if (sig < 0) {
        indicator.classList.add('short');
        signalLabel.innerText = 'SHORT';
        signalLabel.style.color = '#ef4444';
    } else {
        indicator.classList.add('neutral');
        signalLabel.innerText = 'NEUTRAL';
        signalLabel.style.color = '#94a3b8';
    }

    // 2. Format Decision Message
    let msg = "";
    if (decision.event === "decision") {
        const action = decision.action || "hold";
        const reason = decision.reason || "Strategy check";
        msg = `${action.toUpperCase()}: ${reason}`;
    } else if (decision.event === "initializing") {
        msg = "Engine starting...";
    } else {
        msg = decision.reason || "Waiting for next bars...";
    }
    decisionText.innerText = msg;
}

async function refreshTradeMarkers() {
    if (!priceSeries) return;
    try {
        const res = await fetch('/api/bot/markers');
        const data = await res.json();
        
        if (!data || data.length === 0) return;

        // PERFORMANCE FIX: Check if markers actually changed before calling expensive setMarkers
        const markersJSON = JSON.stringify(data);
        if (markersJSON === lastMarkersJSON) return;
        lastMarkersJSON = markersJSON;

        const markers = data.map(m => {
            const isBuy = m.type === 'BUY';
            // Unix time as integer from backend
            const time = Number(m.time);
            
            return {
                time: time,
                position: isBuy ? 'belowBar' : 'aboveBar',
                color: isBuy ? '#10b981' : '#f43f5e',
                shape: isBuy ? 'arrowUp' : 'arrowDown',
                text: m.type + (m.is_entry ? ' [IN]' : ' [OUT]'),
                size: 2
            };
        });

        // Sort by time (required by Lightweight Charts)
        markers.sort((a, b) => a.time - b.time);
        
        // Remove duplicates on the same time if any
        const uniqueMarkers = [];
        const seen = new Set();
        markers.forEach(m => {
            const key = `${m.time}-${m.text}`;
            if (!seen.has(key)) {
                uniqueMarkers.push(m);
                seen.add(key);
            }
        });
        
        priceSeries.setMarkers(uniqueMarkers);
    } catch (e) { 
        console.error("Marker refresh error:", e); 
    }
}

function appendLog(container, log) {
    if (!container) return;
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    const time = new Date(log.timestamp).toLocaleTimeString();
    entry.innerHTML = `<span class="log-time">${time}</span> <span class="log-level-${log.level}">[${log.level}]</span> <span class="log-msg">${log.message}</span>`;
    container.prepend(entry);
    if (container.children.length > 100) container.removeChild(container.lastChild);

    if (log.message.includes('Step') || log.message.includes('Decision')) {
        updateDecisionPanel(log.message);
    }
}

function updateDecisionPanel(msg) {
    const panel = document.getElementById('decision-panel');
    if (!panel) return;
    const entry = document.createElement('p');
    entry.style.cssText = "margin-bottom: 8px; font-size: 0.8rem; border-left: 2px solid var(--primary); padding-left: 8px;";
    entry.innerHTML = `<span style="color:var(--text-secondary); font-size:0.7rem;">${new Date().toLocaleTimeString()}</span><br/>${msg}`;
    panel.prepend(entry);
    if (panel.children.length > 8) panel.removeChild(panel.lastChild);
}

async function checkBotStatus() {
    try {
        const res = await fetch('/api/bot/status');
        const data = await res.json();
        updateUIStatus(data);
        if (data.status === 'running') refreshTradeMarkers();
    } catch (e) { console.error(e); }
}

function updateUIStatus(data) {
    const btnStart = document.getElementById('btn-start');
    const btnStop = document.getElementById('btn-stop');
    if (!btnStart || !btnStop) return;

    if (data.status === 'running') {
        btnStart.disabled = true; btnStart.classList.add('disabled');
        btnStop.disabled = false; btnStop.classList.remove('disabled');
    } else {
        btnStart.disabled = false; btnStart.classList.remove('disabled');
        btnStop.disabled = true; btnStop.classList.add('disabled');
    }
}

async function refreshTradeHistory() {
    try {
        const res = await fetch('/api/bot/trades');
        const trades = await res.json();
        const tbody = document.getElementById('trade-history-body');
        if (!tbody) return;
        tbody.innerHTML = '';
        trades.reverse().slice(0, 30).forEach(t => {
            const row = document.createElement('tr');
            row.style.borderBottom = '1px solid var(--border-color)';
            const pnl = t.pnl_after_costs || 0;
            const pnlColor = pnl >= 0 ? 'var(--success)' : 'var(--danger)';
            const side = t.position === 1 ? 'LONG' : 'SHORT';
            const sideColor = t.position === 1 ? 'var(--success)' : 'var(--danger)';
            row.innerHTML = `
                <td style="padding:12px; font-size:0.8rem; color:var(--text-secondary);">${new Date(t.exit_time).toLocaleString()}</td>
                <td style="padding:12px;"><span class="badge" style="background:${sideColor}22; color:${sideColor}; border:1px solid ${sideColor}44; padding:2px 8px; border-radius:4px; font-size:0.7rem;">${side}</span></td>
                <td style="padding:12px;">$${t.entry_price.toFixed(2)}</td>
                <td style="padding:12px;">$${t.exit_price.toFixed(2)}</td>
                <td style="padding:12px;">${t.notional_closed.toFixed(2)}</td>
                <td style="padding:12px; color:${pnlColor}; font-weight:600;">${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}</td>
                <td style="padding:12px;">${t.bars_held}</td>
                <td style="padding:12px; font-size:0.75rem; color:var(--text-secondary);">${t.reason}</td>
            `;
            tbody.appendChild(row);
        });
    } catch (e) { console.error("History refresh error:", e); }
}

function setupEventListeners() {
    document.getElementById('btn-start').addEventListener('click', startBot);
    document.getElementById('btn-stop').addEventListener('click', stopBot);
}

async function startBot() {
    const config = {
        strategy: document.getElementById('cfg-strategy').value,
        capital: parseFloat(document.getElementById('cfg-capital').value),
        leverage: parseInt(document.getElementById('cfg-leverage').value),
        mode: document.getElementById('cfg-mode').value,
        symbol: document.getElementById('cfg-symbol').value,
        timeframe: document.getElementById('cfg-timeframe').value,
        interval_seconds: parseInt(document.getElementById('cfg-interval').value),
        stop_loss_pct: parseFloat(document.getElementById('cfg-sl').value) / 100,
        take_profit_pct: parseFloat(document.getElementById('cfg-tp').value) / 100,
        risk_per_trade_pct: parseFloat(document.getElementById('cfg-risk').value) / 100,
        max_pos_pct: parseFloat(document.getElementById('cfg-max-pos').value) / 100,
        atr_stop_mult: parseFloat(document.getElementById('cfg-atr-mult').value),
        break_even_trigger_pct: parseFloat(document.getElementById('cfg-be-trigger').value) / 100,
        max_retries: parseInt(document.getElementById('cfg-max-retries').value)
    };
    initialCapital = config.capital;
    isPriceChartInitialized = false;
    try {
        const res = await fetch('/api/bot/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        if (res.ok) alert('Bot Started Successfully');
    } catch (e) { console.error(e); }
}

async function stopBot() {
    try {
        await fetch('/api/bot/stop', { method: 'POST' });
        alert('Bot Terminated');
    } catch (e) { console.error(e); }
}
