// Main Javascript for the Trading Engine Dashboard

let chart;
let equitySeries;
let socket;
let currentEquity = 1000;
let initialCapital = 1000;
let tradeHistory = [];

// Initialize Dashboard
document.addEventListener('DOMContentLoaded', async () => {
    // Phase 1: Critical UI components
    try { initTabs(); } catch (e) { console.error("Tabs init failed", e); }
    try { setupEventListeners(); } catch (e) { console.error("Events init failed", e); }
    
    // Phase 2: Metadata discovery (High priority for user)
    await fetchStrategies();
    
    // Phase 3: Monitoring & Charts
    try { initChart(); } catch (e) { console.error("Chart init failed", e); }
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
                opt.textContent = s.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
                if (s === 'sparse_meta_portfolio') opt.selected = true;
                select.appendChild(opt);
            });
        }
    } catch (err) {
        console.error("Failed to fetch strategies:", err);
    }
}

// Tab Navigation
function initTabs() {
    const navItems = document.querySelectorAll('.nav-item');
    const views = document.querySelectorAll('.view');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const target = item.getAttribute('data-view');
            
            navItems.forEach(i => i.classList.remove('active'));
            views.forEach(v => v.classList.remove('active'));
            
            item.classList.add('active');
            document.getElementById(target).classList.add('active');
            
            // Resize chart if switching to dashboard
            if (target === 'dashboard-view' && chart) {
                window.dispatchEvent(new Event('resize'));
            }
        });
    });
}

// Chart Initialization
function initChart() {
    const chartContainer = document.getElementById('equity-chart');
    chart = LightweightCharts.createChart(chartContainer, {
        layout: {
            background: { type: 'solid', color: 'transparent' },
            textColor: '#94a3b8',
        },
        grid: {
            vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
            horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
        },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
        timeScale: { borderColor: 'rgba(255, 255, 255, 0.1)', timeVisible: true, secondsVisible: true },
    });

    equitySeries = chart.addLineSeries({
        color: '#38bdf8',
        lineWidth: 3,
        lineType: 0,
        priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    });

    // Add starting point
    const now = Math.floor(Date.now() / 1000);
    equitySeries.setData([{ time: now, value: 1000 }]);

    window.addEventListener('resize', () => {
        chart.applyOptions({ 
            width: chartContainer.clientWidth,
            height: chartContainer.clientHeight 
        });
    });
}

// Event Listeners for Buttons
function setupEventListeners() {
    document.getElementById('btn-start').addEventListener('click', startBot);
    document.getElementById('btn-stop').addEventListener('click', stopBot);
}

// API Calls
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

    try {
        const res = await fetch('/api/bot/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        const data = await res.json();
        if (res.ok) {
            alert('Bot Started Successfully');
            // Switch to dashboard
            document.querySelector('[data-view="dashboard-view"]').click();
        } else {
            alert('Error: ' + data.detail);
        }
    } catch (e) {
        console.error(e);
    }
}

async function stopBot() {
    try {
        const res = await fetch('/api/bot/stop', { method: 'POST' });
        const data = await res.json();
        alert('Bot Terminated');
    } catch (e) {
        console.error(e);
    }
}

async function checkBotStatus() {
    try {
        const res = await fetch('/api/bot/status');
        const data = await res.json();
        updateUIStatus(data);
    } catch (e) {
        console.error(e);
    }
}

// WebSocket Connection
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
        // Try to reconnect
        setTimeout(connectWebSocket, 5000);
    };

    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'update') {
            updateDashboard(data);
        }
    };
}

function updateDashboard(data) {
    const { status, logs } = data;
    
    // Update Stats
    if (status && status.status === 'running') {
        const equity = status.capital;
        const pnl = equity - initialCapital;
        const pnlPct = (pnl / initialCapital * 100).toFixed(2);
        
        document.getElementById('stat-equity').innerText = `$${equity.toLocaleString(undefined, {minimumFractionDigits: 2})}`;
        document.getElementById('stat-pnl').innerText = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)} (${pnlPct}%)`;
        document.getElementById('stat-pnl').style.color = pnl >= 0 ? 'var(--success)' : 'var(--danger)';
        
        const pos = status.position;
        const posSide = pos.side === 0 ? 'FLAT' : (pos.side === 1 ? 'LONG' : 'SHORT');
        document.getElementById('stat-pos').innerText = `${posSide} ${pos.quantity ? pos.quantity.toFixed(4) : ''}`;
        document.getElementById('stat-pos').style.color = pos.side === 0 ? 'var(--text-primary)' : (pos.side === 1 ? 'var(--success)' : 'var(--danger)');

        // Update Strategy Label
        if (status.config && status.config.strategy) {
            document.getElementById('active-strategy').innerText = status.config.strategy.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
        }
        
        // Update Chart
        const now = Math.floor(Date.now() / 1000);
        equitySeries.update({ time: now, value: equity });
    }

    // Append Logs
    if (logs && logs.length > 0) {
        const logList = document.getElementById('log-list');
        logs.forEach(log => {
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            
            // Format time
            const time = new Date(log.timestamp).toLocaleTimeString();
            
            entry.innerHTML = `
                <span class="log-time">${time}</span>
                <span class="log-level-${log.level}">[${log.level}]</span>
                <span class="log-msg">${log.message}</span>
            `;
            logList.prepend(entry); // Newest on top
            
            // Limit shown logs
            if (logList.children.length > 200) logList.removeChild(logList.lastChild);

            // Special case for decision logs
            if (log.message.includes('Step') || log.message.includes('Decision')) {
                updateDecisionPanel(log.message);
            }

            // Sync trade history if fills mentioned
            if (log.message.includes('Fill received') || log.message.includes('Position fully closed')) {
                refreshTradeHistory();
            }
        });
        document.getElementById('log-count').innerText = `${logList.children.length} entries`;
    }
}

function updateDecisionPanel(msg) {
    const panel = document.getElementById('decision-panel');
    if (!panel) return;
    const entry = document.createElement('p');
    entry.style.marginBottom = '8px';
    entry.style.fontSize = '0.8rem';
    entry.innerHTML = `<span style="color:var(--primary); font-weight:600;">></span> ${msg}`;
    panel.prepend(entry);
    if (panel.children.length > 10) panel.removeChild(panel.lastChild);
}

function updateUIStatus(data) {
    const btnStart = document.getElementById('btn-start');
    const btnStop = document.getElementById('btn-stop');
    if (!btnStart || !btnStop) return;

    if (data.status === 'running') {
        btnStart.disabled = true;
        btnStart.classList.add('disabled');
        btnStop.disabled = false;
        btnStop.classList.remove('disabled');
    } else {
        btnStart.disabled = false;
        btnStart.classList.remove('disabled');
        btnStop.disabled = true;
        btnStop.classList.add('disabled');
    }

    if (data.performance) {
        updatePerformanceUI(data.performance);
    }
}

function updatePerformanceUI(perf) {
    const ids = {
        'rep-winrate': `${perf.win_rate}%`,
        'rep-pf': perf.profit_factor,
        'rep-trades': perf.total_trades,
        'rep-avg-bars': perf.avg_bars_held,
        'stat-pnl': `${perf.total_pnl >= 0 ? '+' : ''}$${perf.total_pnl} (${perf.pnl_pct}%)`,
        'stat-dd': '0.00%' // Drawdown calculation can be added to backend later
    };

    for (const [id, val] of Object.entries(ids)) {
        const el = document.getElementById(id);
        if (el) {
            el.innerText = val;
            if (id === 'stat-pnl') {
                el.style.color = perf.total_pnl >= 0 ? 'var(--success)' : 'var(--danger)';
            }
        }
    }
}

async function refreshTradeHistory() {
    try {
        const res = await fetch('/api/bot/trades');
        const trades = await res.json();
        const tbody = document.getElementById('trade-history-body');
        if (!tbody) return;

        tbody.innerHTML = '';
        trades.reverse().forEach(t => {
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
                <td style="padding:12px;">${t.bars_held} bars</td>
                <td style="padding:12px; font-size:0.75rem; color:var(--text-secondary);">${t.reason}</td>
            `;
            tbody.appendChild(row);
        });
    } catch (e) {
        console.error("Failed to refresh trades:", e);
    }
}

function exportData() {
    fetch('/api/bot/trades')
        .then(res => res.json())
        .then(trades => {
            if (trades.length === 0) {
                alert('No trades to export');
                return;
            }
            const headers = Object.keys(trades[0]).join(',');
            const rows = trades.map(t => Object.values(t).join(','));
            const csv = [headers, ...rows].join('\n');
            const blob = new Blob([csv], { type: 'text/csv' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.setAttribute('href', url);
            a.setAttribute('download', `trades_${new Date().getTime()}.csv`);
            a.click();
        });
}
