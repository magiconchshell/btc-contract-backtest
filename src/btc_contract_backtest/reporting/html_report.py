from __future__ import annotations

import json
from pathlib import Path


HTML_TEMPLATE = """
<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>BTC 合約回測報告</title>
  <script
    src="https://cdn.plot.ly/plotly-2.35.2.min.js"
  ></script>
  <style>
    body {
      font-family: Inter, -apple-system, BlinkMacSystemFont, sans-serif;
      background: #0b1020;
      color: #e8ecf3;
      margin: 0;
    }
    .wrap { max-width:1400px; margin:0 auto; padding:24px; }
    .hero {
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: flex-start;
      margin-bottom: 24px;
    }
    .card {
      background: #121a30;
      border: 1px solid #25304f;
      border-radius: 18px;
      padding: 20px;
      box-shadow: 0 8px 30px rgba(0, 0, 0, 0.25);
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 24px;
    }
    .metric .label {
      color: #8ea0c9;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .08em;
    }
    .metric .value { font-size:28px; font-weight:700; margin-top:8px; }
    .section-title { font-size:22px; font-weight:700; margin:24px 0 12px; }
    .chart { height:460px; margin-bottom:20px; }
    table { width:100%; border-collapse:collapse; }
    th, td { padding:12px 10px; border-bottom:1px solid #273252; text-align:left; }
    th { color:#8ea0c9; font-weight:600; }
    .small { color:#95a4c6; font-size:13px; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div>
        <h1>BTC/USDT 合約回測報告</h1>
        <div class="small">
          期間：2025-01-01 至今｜本金：100 USD｜市場：Perpetual Futures｜可做多做空｜槓桿 5x
        </div>
      </div>
      <div class="card small">
        高可視化 HTML 報表，可透過 FastAPI 提供並由 ngrok 對外。
      </div>
    </div>

    <div id="summary-cards" class="grid"></div>
    <div class="section-title">策略資金曲線比較</div>
    <div id="equity-chart" class="card chart"></div>
    <div class="section-title">報酬 / 風險對比</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
      <div id="returns-chart" class="card chart"></div>
      <div id="drawdown-chart" class="card chart"></div>
    </div>
    <div class="section-title">交易品質</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
      <div id="trades-chart" class="card chart"></div>
      <div id="winrate-chart" class="card chart"></div>
    </div>
    <div class="section-title">策略明細</div>
    <div class="card">
      <table>
        <thead>
          <tr>
            <th>策略</th>
            <th>總報酬</th>
            <th>Sharpe</th>
            <th>最大回撤</th>
            <th>勝率</th>
            <th>交易數</th>
            <th>最終資金</th>
          </tr>
        </thead>
        <tbody id="table-body"></tbody>
      </table>
    </div>
  </div>
<script>
const payload = __PAYLOAD__;
const strategies = payload.strategies;
const best = [...strategies].sort((a,b)=>b.metrics.total_return-a.metrics.total_return)[0];
const cards = [
  ['最佳策略', best.name],
  ['最高報酬', best.metrics.total_return.toFixed(2) + '%'],
  ['最佳 Sharpe', Math.max(...strategies.map(s=>s.metrics.sharpe_ratio)).toFixed(2)],
  ['回測策略數', String(strategies.length)]
];
const cardsNode = document.getElementById('summary-cards');
cards.forEach(([label,value])=>{
  const div=document.createElement('div');
  div.className='card metric';
  div.innerHTML=`<div class="label">${label}</div><div class="value">${value}</div>`;
  cardsNode.appendChild(div);
});
Plotly.newPlot('equity-chart', strategies.map(s => ({
  x: s.equity_curve.map(p => p.timestamp),
  y: s.equity_curve.map(p => p.equity),
  mode: 'lines',
  name: s.name,
  line: {width: 3}
})), {paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)', font:{color:'#e8ecf3'}, margin:{t:20}});
Plotly.newPlot(
  'returns-chart',
  [{
    type: 'bar',
    x: strategies.map(s => s.name),
    y: strategies.map(s => s.metrics.total_return),
    marker: {color: ['#4ade80', '#60a5fa', '#f59e0b']}
  }],
  {
    title: '總報酬 (%)',
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: {color: '#e8ecf3'}
  }
);
Plotly.newPlot(
  'drawdown-chart',
  [{
    type: 'bar',
    x: strategies.map(s => s.name),
    y: strategies.map(s => s.metrics.max_drawdown),
    marker: {color: '#f87171'}
  }],
  {
    title: '最大回撤 (%)',
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: {color: '#e8ecf3'}
  }
);
Plotly.newPlot(
  'trades-chart',
  [{
    type: 'bar',
    x: strategies.map(s => s.name),
    y: strategies.map(s => s.metrics.total_trades),
    marker: {color: '#a78bfa'}
  }],
  {
    title: '交易數',
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: {color: '#e8ecf3'}
  }
);
Plotly.newPlot(
  'winrate-chart',
  [{
    type: 'bar',
    x: strategies.map(s => s.name),
    y: strategies.map(s => s.metrics.win_rate),
    marker: {color: '#22d3ee'}
  }],
  {
    title: '勝率 (%)',
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: {color: '#e8ecf3'}
  }
);
const tbody = document.getElementById('table-body');
strategies.forEach(s => {
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td>${s.name}</td>
    <td>${s.metrics.total_return.toFixed(2)}%</td>
    <td>${s.metrics.sharpe_ratio.toFixed(2)}</td>
    <td>${s.metrics.max_drawdown.toFixed(2)}%</td>
    <td>${s.metrics.win_rate.toFixed(2)}%</td>
    <td>${s.metrics.total_trades}</td>
    <td>${s.metrics.final_capital.toFixed(2)}</td>
  `;
  tbody.appendChild(tr);
});
</script>
</body>
</html>
"""


def build_report_html(payload: dict) -> str:
    return HTML_TEMPLATE.replace("__PAYLOAD__", json.dumps(payload))


def write_report(output_path: str | Path, payload: dict) -> Path:
    output_path = Path(output_path)
    output_path.write_text(build_report_html(payload), encoding="utf-8")
    return output_path
