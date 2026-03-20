"""Embedded Web UI — full dashboard served from FastAPI, zero build step."""

# This is a single HTML page with embedded JS that talks to the API via fetch/WebSocket.
# Uses Tailwind CSS via CDN and lightweight-charts for price visualization.

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CryptoMega — Dashboard</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>
tailwind.config = {
  theme: {
    extend: {
      colors: {
        bg: '#0a0a0f',
        card: '#12121a',
        border: '#1e1e2e',
        accent: '#00ff88',
        accentDim: '#00cc6a',
        blue: '#00bfff',
        warn: '#ff9800',
        danger: '#f44336',
        profit: '#00ff88',
        loss: '#ff4444',
      }
    }
  }
}
</script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap');
  * { font-family: 'JetBrains Mono', monospace; }
  body { background: #0a0a0f; }
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: #0a0a0f; }
  ::-webkit-scrollbar-thumb { background: #2a2a3a; border-radius: 3px; }
  .tab-active { border-bottom: 2px solid #00ff88; color: #00ff88; }
  .fade-in { animation: fadeIn 0.3s ease-in; }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
  .pulse { animation: pulse 2s infinite; }
  .sparkline { display: inline-block; vertical-align: middle; }
  .sparkline canvas { display: block; }
</style>
</head>
<body class="text-gray-300 min-h-screen">

<!-- Header -->
<header class="border-b border-border px-6 py-3 flex items-center justify-between sticky top-0 bg-bg/95 backdrop-blur z-50">
  <div class="flex items-center gap-4">
    <h1 class="text-accent font-bold text-lg">CryptoMega</h1>
    <span class="text-xs text-gray-600">signal tournament</span>
  </div>
  <div class="flex items-center gap-4">
    <div id="ws-status" class="flex items-center gap-1 text-xs">
      <span class="w-2 h-2 rounded-full bg-danger" id="ws-dot"></span>
      <span id="ws-label">disconnected</span>
    </div>
    <span class="text-xs text-gray-600" id="clock"></span>
  </div>
</header>

<!-- Tabs -->
<nav class="border-b border-border px-6 flex gap-6 text-sm">
  <button class="py-3 px-1 tab-active" data-tab="dashboard" onclick="switchTab('dashboard')">Dashboard</button>
  <button class="py-3 px-1 text-gray-500 hover:text-gray-300" data-tab="leaderboard" onclick="switchTab('leaderboard')">Leaderboard</button>
  <button class="py-3 px-1 text-gray-500 hover:text-gray-300" data-tab="signals" onclick="switchTab('signals')">Signals</button>
  <button class="py-3 px-1 text-gray-500 hover:text-gray-300" data-tab="positions" onclick="switchTab('positions')">Positions</button>
  <button class="py-3 px-1 text-gray-500 hover:text-gray-300" data-tab="strategies" onclick="switchTab('strategies')">Strategies</button>
  <button class="py-3 px-1 text-gray-500 hover:text-gray-300" data-tab="control" onclick="switchTab('control')">Control</button>
</nav>

<!-- Content -->
<main class="p-6 max-w-[1400px] mx-auto">

  <!-- ═══ DASHBOARD TAB ═══ -->
  <div id="tab-dashboard" class="fade-in">
    <!-- Status cards -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
      <div class="bg-card border border-border rounded-lg p-4">
        <div class="text-xs text-gray-500 mb-1">Strategies Running</div>
        <div class="text-2xl font-bold text-accent" id="stat-running">0</div>
      </div>
      <div class="bg-card border border-border rounded-lg p-4">
        <div class="text-xs text-gray-500 mb-1">Open Positions</div>
        <div class="text-2xl font-bold text-blue" id="stat-positions">0</div>
      </div>
      <div class="bg-card border border-border rounded-lg p-4">
        <div class="text-xs text-gray-500 mb-1">Total Paper P&amp;L</div>
        <div class="text-2xl font-bold" id="stat-pnl">$0.00</div>
      </div>
      <div class="bg-card border border-border rounded-lg p-4">
        <div class="text-xs text-gray-500 mb-1">Signals (24h)</div>
        <div class="text-2xl font-bold text-warn" id="stat-signals">0</div>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
      <!-- Risk card -->
      <div class="bg-card border border-border rounded-lg p-4">
        <h3 class="text-blue text-sm font-semibold mb-3">Risk Status</h3>
        <div class="space-y-2 text-sm">
          <div class="flex justify-between"><span class="text-gray-500">Equity</span><span id="risk-equity">$10,000</span></div>
          <div class="flex justify-between"><span class="text-gray-500">Drawdown</span><span id="risk-dd">0.0%</span></div>
          <div class="flex justify-between"><span class="text-gray-500">Kill Switch</span><span id="risk-ks" class="text-profit">OFF</span></div>
        </div>
      </div>
      <!-- Recent signals -->
      <div class="bg-card border border-border rounded-lg p-4">
        <h3 class="text-blue text-sm font-semibold mb-3">Recent Signals</h3>
        <div id="recent-signals" class="space-y-1 text-xs max-h-[140px] overflow-y-auto">
          <div class="text-gray-600">Waiting for signals...</div>
        </div>
      </div>
    </div>

    <!-- Top strategies mini-leaderboard -->
    <div class="bg-card border border-border rounded-lg p-4">
      <h3 class="text-blue text-sm font-semibold mb-3">Top Strategies (Paper P&amp;L)</h3>
      <div id="mini-leaderboard" class="text-xs">
        <div class="text-gray-600">No data yet — start strategies to see results</div>
      </div>
    </div>
  </div>

  <!-- ═══ LEADERBOARD TAB ═══ -->
  <div id="tab-leaderboard" class="hidden fade-in">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold text-accent">Strategy Leaderboard</h2>
      <select id="lb-sort" class="bg-card border border-border rounded px-3 py-1 text-sm" onchange="loadLeaderboard()">
        <option value="total_pnl_pct">Sort by P&amp;L %</option>
        <option value="sharpe_ratio">Sort by Sharpe</option>
        <option value="win_rate">Sort by Win Rate</option>
        <option value="profit_factor">Sort by Profit Factor</option>
        <option value="closed_positions">Sort by Trades</option>
      </select>
    </div>
    <div class="overflow-x-auto">
      <table class="w-full text-xs">
        <thead>
          <tr class="text-gray-500 border-b border-border">
            <th class="text-left py-2 px-2">#</th>
            <th class="text-left py-2 px-2">Strategy</th>
            <th class="text-right py-2 px-2">P&amp;L %</th>
            <th class="text-right py-2 px-2">Trades</th>
            <th class="text-right py-2 px-2">Win Rate</th>
            <th class="text-right py-2 px-2">Sharpe</th>
            <th class="text-right py-2 px-2">PF</th>
            <th class="text-right py-2 px-2">Max DD</th>
            <th class="text-right py-2 px-2">Open</th>
            <th class="text-right py-2 px-2">Equity</th>
            <th class="text-center py-2 px-2">Action</th>
          </tr>
        </thead>
        <tbody id="lb-body"></tbody>
      </table>
    </div>
    <div id="lb-empty" class="text-center text-gray-600 py-8">No strategies tracked yet</div>
  </div>

  <!-- ═══ SIGNALS TAB ═══ -->
  <div id="tab-signals" class="hidden fade-in">
    <h2 class="text-lg font-semibold text-accent mb-4">Signal Feed</h2>
    <div id="signal-feed" class="space-y-1 text-xs">
      <div class="text-gray-600">Waiting for signals...</div>
    </div>
  </div>

  <!-- ═══ POSITIONS TAB ═══ -->
  <div id="tab-positions" class="hidden fade-in">
    <div class="flex gap-4 mb-4">
      <button class="text-sm px-3 py-1 bg-card border border-border rounded hover:border-accent" onclick="loadPositions('open')" id="pos-btn-open">Open</button>
      <button class="text-sm px-3 py-1 bg-card border border-border rounded hover:border-accent" onclick="loadPositions('closed')" id="pos-btn-closed">Closed</button>
    </div>
    <div class="overflow-x-auto">
      <table class="w-full text-xs">
        <thead>
          <tr class="text-gray-500 border-b border-border" id="pos-header"></tr>
        </thead>
        <tbody id="pos-body"></tbody>
      </table>
    </div>
    <div id="pos-empty" class="text-center text-gray-600 py-8">No positions</div>
  </div>

  <!-- ═══ STRATEGIES TAB ═══ -->
  <div id="tab-strategies" class="hidden fade-in">
    <h2 class="text-lg font-semibold text-accent mb-4">Loaded Strategies</h2>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" id="strategy-grid">
      <div class="text-gray-600">Loading...</div>
    </div>
    <div class="mt-6 bg-card border border-border rounded-lg p-4">
      <h3 class="text-blue text-sm font-semibold mb-3">Load Strategies from Directory</h3>
      <div class="flex gap-2">
        <input id="load-dir" type="text" value="strategies_user" class="flex-1 bg-bg border border-border rounded px-3 py-2 text-sm">
        <button onclick="loadDir()" class="px-4 py-2 bg-accent/20 text-accent rounded hover:bg-accent/30 text-sm">Load</button>
      </div>
      <div id="load-result" class="mt-2 text-xs"></div>
    </div>
  </div>

  <!-- ═══ CONTROL TAB ═══ -->
  <div id="tab-control" class="hidden fade-in">
    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
      <!-- Engine Control -->
      <div class="bg-card border border-border rounded-lg p-4">
        <h3 class="text-blue text-sm font-semibold mb-3">Engine Control</h3>
        <div class="space-y-2">
          <label class="text-xs text-gray-500">Exchange</label>
          <select id="engine-exchange" class="w-full bg-bg border border-border rounded px-3 py-2 text-sm">
            <option value="binance">Binance</option>
            <option value="bybit">Bybit</option>
            <option value="okx">OKX</option>
            <option value="kucoin">KuCoin</option>
            <option value="gate">Gate.io</option>
          </select>
          <label class="text-xs text-gray-500">Symbols (comma-separated)</label>
          <input id="engine-symbols" type="text" value="BTC/USDT,ETH/USDT" class="w-full bg-bg border border-border rounded px-3 py-2 text-sm">
          <label class="text-xs text-gray-500">Interval (seconds)</label>
          <input id="engine-interval" type="number" value="60" class="w-full bg-bg border border-border rounded px-3 py-2 text-sm">
          <button onclick="startEngine()" class="w-full py-2 bg-accent/20 text-accent rounded hover:bg-accent/30 text-sm font-bold">Start Signal Engine</button>
          <button onclick="stopEngine()" class="w-full py-2 bg-danger/20 text-danger rounded hover:bg-danger/30 text-sm">Stop Engine</button>
        </div>
        <div id="engine-status" class="mt-3 text-xs text-gray-500"></div>
      </div>
      <!-- Kill Switch -->
      <div class="bg-card border border-border rounded-lg p-4">
        <h3 class="text-danger text-sm font-semibold mb-3">Emergency Controls</h3>
        <div class="space-y-3">
          <button onclick="killSwitch(true)" class="w-full py-2 bg-danger/20 text-danger rounded hover:bg-danger/30 text-sm font-bold">ACTIVATE KILL SWITCH</button>
          <button onclick="killSwitch(false)" class="w-full py-2 bg-card border border-border rounded hover:border-accent text-sm">Deactivate Kill Switch</button>
        </div>
      </div>
      <!-- Exchange Config -->
      <div class="bg-card border border-border rounded-lg p-4">
        <h3 class="text-blue text-sm font-semibold mb-3">Exchange Connection</h3>
        <div class="space-y-2">
          <select id="exchange-id" class="w-full bg-bg border border-border rounded px-3 py-2 text-sm">
            <option value="binance">Binance</option>
            <option value="bybit">Bybit</option>
            <option value="okx">OKX</option>
            <option value="kucoin">KuCoin</option>
            <option value="gate">Gate.io</option>
          </select>
          <input id="api-key" type="password" placeholder="API Key" class="w-full bg-bg border border-border rounded px-3 py-2 text-sm">
          <input id="api-secret" type="password" placeholder="API Secret" class="w-full bg-bg border border-border rounded px-3 py-2 text-sm">
          <label class="flex items-center gap-2 text-sm"><input type="checkbox" id="sandbox-mode" checked> Sandbox / Testnet</label>
          <button onclick="connectExchange()" class="w-full py-2 bg-blue/20 text-blue rounded hover:bg-blue/30 text-sm">Connect Exchange</button>
        </div>
        <div id="exchange-result" class="mt-2 text-xs"></div>
      </div>
      <!-- Promote Strategy -->
      <div class="bg-card border border-border rounded-lg p-4">
        <h3 class="text-warn text-sm font-semibold mb-3">Promote to Live Trading</h3>
        <p class="text-xs text-gray-500 mb-3">Approve a strategy for real execution. Signals from promoted strategies will be sent to the connected exchange.</p>
        <div class="flex gap-2">
          <input id="promote-id" type="text" placeholder="Strategy ID (first 8 chars)" class="flex-1 bg-bg border border-border rounded px-3 py-2 text-sm">
          <button onclick="promoteStrategy()" class="px-4 py-2 bg-warn/20 text-warn rounded hover:bg-warn/30 text-sm">Promote</button>
        </div>
        <div id="promote-result" class="mt-2 text-xs"></div>
      </div>
    </div>
  </div>

</main>

<script>
// ─── State ───
let ws = null;
let currentTab = 'dashboard';
let signalBuffer = [];

// ─── API helpers ───
const api = (path, opts) => fetch(path, opts).then(r => r.json()).catch(e => ({ error: e.message }));
const post = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

// ─── Tab switching ───
function switchTab(tab) {
  document.querySelectorAll('[data-tab]').forEach(b => {
    b.classList.toggle('tab-active', b.dataset.tab === tab);
    b.classList.toggle('text-gray-500', b.dataset.tab !== tab);
  });
  document.querySelectorAll('[id^="tab-"]').forEach(el => {
    el.classList.toggle('hidden', el.id !== 'tab-' + tab);
  });
  currentTab = tab;
  refreshTab();
}

function refreshTab() {
  if (currentTab === 'leaderboard') loadLeaderboard();
  if (currentTab === 'positions') loadPositions('open');
  if (currentTab === 'strategies') loadStrategies();
  if (currentTab === 'signals') loadSignalFeed();
}

// ─── Dashboard ───
async function refreshDashboard() {
  const [status, risk, lb, signals] = await Promise.all([
    api('/status'),
    api('/risk'),
    api('/paper/leaderboard?limit=5'),
    api('/paper/signals?limit=20'),
  ]);

  // Status cards
  const running = status.engine ? Object.keys(status.engine).length : 0;
  document.getElementById('stat-running').textContent = running;
  document.getElementById('stat-signals').textContent = signals.signals ? signals.signals.length : 0;

  // Risk
  if (risk) {
    document.getElementById('risk-equity').textContent = '$' + (risk.equity || 0).toLocaleString();
    document.getElementById('risk-dd').textContent = (risk.drawdown_pct || 0).toFixed(1) + '%';
    const ks = risk.kill_switch;
    const ksEl = document.getElementById('risk-ks');
    ksEl.textContent = ks ? 'ACTIVE' : 'OFF';
    ksEl.className = ks ? 'text-danger font-bold pulse' : 'text-profit';
  }

  // Leaderboard positions count + PnL
  if (lb.leaderboard && lb.leaderboard.length > 0) {
    let totalPnl = 0;
    let totalOpen = 0;
    lb.leaderboard.forEach(s => {
      totalPnl += s.total_pnl || 0;
      totalOpen += s.open_positions || 0;
    });
    const pnlEl = document.getElementById('stat-pnl');
    pnlEl.textContent = (totalPnl >= 0 ? '+' : '') + totalPnl.toFixed(4);
    pnlEl.className = 'text-2xl font-bold ' + (totalPnl >= 0 ? 'text-profit' : 'text-loss');
    document.getElementById('stat-positions').textContent = totalOpen;

    // Mini leaderboard
    let html = '<table class="w-full"><tr class="text-gray-500"><th class="text-left py-1">Strategy</th><th class="text-right py-1">P&L %</th><th class="text-right py-1">WR</th><th class="text-right py-1">Trades</th></tr>';
    lb.leaderboard.forEach((s, i) => {
      const color = s.total_pnl_pct >= 0 ? 'text-profit' : 'text-loss';
      html += `<tr class="border-t border-border/50"><td class="py-1">${i+1}. ${s.strategy_name}</td><td class="text-right ${color}">${s.total_pnl_pct >= 0 ? '+' : ''}${s.total_pnl_pct.toFixed(2)}%</td><td class="text-right">${s.win_rate.toFixed(0)}%</td><td class="text-right">${s.closed_positions}</td></tr>`;
    });
    html += '</table>';
    document.getElementById('mini-leaderboard').innerHTML = html;
  }

  // Recent signals
  if (signals.signals && signals.signals.length > 0) {
    let html = '';
    signals.signals.slice().reverse().slice(0, 10).forEach(s => {
      const color = s.direction === 'long' ? 'text-profit' : s.direction === 'short' ? 'text-loss' : 'text-gray-400';
      const time = new Date(s.timestamp * 1000).toLocaleTimeString();
      html += `<div class="flex justify-between py-0.5 border-b border-border/30"><span><span class="${color} font-bold uppercase">${s.direction}</span> ${s.symbol} @ ${s.price.toFixed(2)}</span><span class="text-gray-600">${s.strategy_id} | str=${s.strength} | ${time}</span></div>`;
    });
    document.getElementById('recent-signals').innerHTML = html;
  }
}

// ─── Leaderboard ───
async function loadLeaderboard() {
  const sort = document.getElementById('lb-sort').value;
  const data = await api(`/paper/leaderboard?sort_by=${sort}`);
  const body = document.getElementById('lb-body');
  const empty = document.getElementById('lb-empty');

  if (!data.leaderboard || data.leaderboard.length === 0) {
    body.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');

  body.innerHTML = data.leaderboard.map((s, i) => {
    const pnlColor = s.total_pnl_pct >= 0 ? 'text-profit' : 'text-loss';
    const wrColor = s.win_rate >= 50 ? 'text-profit' : s.win_rate >= 40 ? 'text-warn' : 'text-loss';
    const sparks = s.equity_curve && s.equity_curve.length > 1 ? miniSparkline(s.equity_curve) : '-';
    return `<tr class="border-b border-border/30 hover:bg-border/20">
      <td class="py-2 px-2 text-gray-500">${i + 1}</td>
      <td class="py-2 px-2 font-semibold">${s.strategy_name}<br><span class="text-gray-600 font-normal">${s.strategy_id}</span></td>
      <td class="py-2 px-2 text-right ${pnlColor} font-bold">${s.total_pnl_pct >= 0 ? '+' : ''}${s.total_pnl_pct.toFixed(2)}%</td>
      <td class="py-2 px-2 text-right">${s.closed_positions}</td>
      <td class="py-2 px-2 text-right ${wrColor}">${s.win_rate.toFixed(1)}%</td>
      <td class="py-2 px-2 text-right">${s.sharpe_ratio.toFixed(2)}</td>
      <td class="py-2 px-2 text-right">${s.profit_factor.toFixed(2)}</td>
      <td class="py-2 px-2 text-right text-loss">${s.max_drawdown.toFixed(2)}%</td>
      <td class="py-2 px-2 text-right text-blue">${s.open_positions}</td>
      <td class="py-2 px-2 text-right">${sparks}</td>
      <td class="py-2 px-2 text-center">${s.promoted ? '<span class="text-warn font-bold">LIVE</span>' : `<button onclick="promoteFromLB('${s.strategy_id}')" class="text-warn hover:underline">Promote</button>`}</td>
    </tr>`;
  }).join('');
}

function miniSparkline(data) {
  if (!data || data.length < 2) return '-';
  const w = 80, h = 24;
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * h;
    return `${x},${y}`;
  }).join(' ');
  const color = data[data.length - 1] >= data[0] ? '#00ff88' : '#ff4444';
  return `<svg width="${w}" height="${h}" class="inline-block"><polyline points="${points}" fill="none" stroke="${color}" stroke-width="1.5"/></svg>`;
}

// ─── Signals ───
async function loadSignalFeed() {
  const data = await api('/paper/signals?limit=200');
  if (!data.signals) return;
  const container = document.getElementById('signal-feed');
  container.innerHTML = data.signals.slice().reverse().map(s => {
    const color = s.direction === 'long' ? 'text-profit' : s.direction === 'short' ? 'text-loss' : 'text-gray-400';
    const time = new Date(s.timestamp * 1000).toLocaleTimeString();
    const sl = s.stop_loss ? ` SL=${s.stop_loss.toFixed(2)}` : '';
    const tp = s.take_profit ? ` TP=${s.take_profit.toFixed(2)}` : '';
    return `<div class="flex justify-between py-1 border-b border-border/30">
      <span><span class="${color} font-bold uppercase w-12 inline-block">${s.direction}</span> <span class="text-blue">${s.symbol}</span> @ ${s.price.toFixed(2)}${sl}${tp}</span>
      <span class="text-gray-600">${s.strategy_id} | str=${s.strength} | ${time}</span>
    </div>`;
  }).join('');
}

// ─── Positions ───
async function loadPositions(type) {
  document.getElementById('pos-btn-open').className = type === 'open' ? 'text-sm px-3 py-1 bg-accent/20 text-accent border border-accent rounded' : 'text-sm px-3 py-1 bg-card border border-border rounded hover:border-accent';
  document.getElementById('pos-btn-closed').className = type === 'closed' ? 'text-sm px-3 py-1 bg-accent/20 text-accent border border-accent rounded' : 'text-sm px-3 py-1 bg-card border border-border rounded hover:border-accent';

  const data = await api(`/paper/positions/${type}`);
  const positions = data.positions || [];
  const header = document.getElementById('pos-header');
  const body = document.getElementById('pos-body');
  const empty = document.getElementById('pos-empty');

  if (positions.length === 0) {
    header.innerHTML = '';
    body.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');

  if (type === 'open') {
    header.innerHTML = '<th class="text-left py-2 px-2">Strategy</th><th class="text-left py-2 px-2">Symbol</th><th class="py-2 px-2">Dir</th><th class="text-right py-2 px-2">Entry</th><th class="text-right py-2 px-2">Current</th><th class="text-right py-2 px-2">P&L %</th><th class="text-right py-2 px-2">SL</th><th class="text-right py-2 px-2">TP</th>';
    body.innerHTML = positions.map(p => {
      const color = p.unrealized_pnl_pct >= 0 ? 'text-profit' : 'text-loss';
      const dirColor = p.direction === 'long' ? 'text-profit' : 'text-loss';
      return `<tr class="border-b border-border/30"><td class="py-1 px-2">${p.strategy_name}<br><span class="text-gray-600">${p.strategy_id}</span></td><td class="py-1 px-2 text-blue">${p.symbol}</td><td class="py-1 px-2 ${dirColor} font-bold uppercase">${p.direction}</td><td class="py-1 px-2 text-right">${p.entry_price.toFixed(2)}</td><td class="py-1 px-2 text-right">${p.current_price.toFixed(2)}</td><td class="py-1 px-2 text-right ${color} font-bold">${p.unrealized_pnl_pct >= 0 ? '+' : ''}${p.unrealized_pnl_pct.toFixed(2)}%</td><td class="py-1 px-2 text-right">${p.stop_loss || '-'}</td><td class="py-1 px-2 text-right">${p.take_profit || '-'}</td></tr>`;
    }).join('');
  } else {
    header.innerHTML = '<th class="text-left py-2 px-2">Strategy</th><th class="text-left py-2 px-2">Symbol</th><th class="py-2 px-2">Dir</th><th class="text-right py-2 px-2">Entry</th><th class="text-right py-2 px-2">Exit</th><th class="text-right py-2 px-2">P&L %</th><th class="py-2 px-2">Reason</th><th class="py-2 px-2">Closed</th>';
    body.innerHTML = positions.map(p => {
      const color = p.realized_pnl_pct >= 0 ? 'text-profit' : 'text-loss';
      const dirColor = p.direction === 'long' ? 'text-profit' : 'text-loss';
      return `<tr class="border-b border-border/30"><td class="py-1 px-2">${p.strategy_name}<br><span class="text-gray-600">${p.strategy_id}</span></td><td class="py-1 px-2 text-blue">${p.symbol}</td><td class="py-1 px-2 ${dirColor} font-bold uppercase">${p.direction}</td><td class="py-1 px-2 text-right">${p.entry_price.toFixed(2)}</td><td class="py-1 px-2 text-right">${(p.exit_price || 0).toFixed(2)}</td><td class="py-1 px-2 text-right ${color} font-bold">${p.realized_pnl_pct >= 0 ? '+' : ''}${p.realized_pnl_pct.toFixed(2)}%</td><td class="py-1 px-2 uppercase">${p.close_reason}</td><td class="py-1 px-2 text-gray-600">${p.closed_at ? new Date(p.closed_at).toLocaleString() : ''}</td></tr>`;
    }).join('');
  }
}

// ─── Strategies ───
async function loadStrategies() {
  const data = await api('/strategies');
  const grid = document.getElementById('strategy-grid');
  if (!data.registered || Object.keys(data.registered).length === 0) {
    grid.innerHTML = '<div class="text-gray-600">No strategies loaded</div>';
    return;
  }
  const running = data.running || {};
  grid.innerHTML = Object.entries(data.registered).map(([name, cls]) => {
    const runInfo = Object.values(running).find(r => r.name === name);
    const statusColor = runInfo ? (runInfo.status === 'running' ? 'text-profit' : 'text-warn') : 'text-gray-600';
    const statusText = runInfo ? runInfo.status : 'idle';
    return `<div class="bg-card border border-border rounded-lg p-4">
      <div class="flex justify-between items-start mb-2">
        <h4 class="font-semibold text-sm">${name}</h4>
        <span class="${statusColor} text-xs uppercase">${statusText}</span>
      </div>
      ${runInfo ? `<div class="text-xs text-gray-500 space-y-1">
        <div>Signals: ${runInfo.signals}</div>
        <div>Priority: ${runInfo.priority}</div>
        <div>Errors: ${runInfo.errors.length}</div>
      </div>` : '<div class="text-xs text-gray-600">Not running</div>'}
    </div>`;
  }).join('');
}

async function loadDir() {
  const dir = document.getElementById('load-dir').value;
  const data = await post(`/strategies/load-directory?directory=${encodeURIComponent(dir)}`, {});
  document.getElementById('load-result').innerHTML = data.loaded
    ? `<span class="text-profit">Loaded: ${data.loaded.join(', ')}</span>`
    : `<span class="text-loss">Error: ${JSON.stringify(data)}</span>`;
  loadStrategies();
}

// ─── Control actions ───
async function startEngine() {
  const exchange = document.getElementById('engine-exchange').value;
  const symbols = document.getElementById('engine-symbols').value;
  const interval = document.getElementById('engine-interval').value;
  document.getElementById('engine-status').innerHTML = '<span class="text-warn">Connecting to exchange and starting...</span>';
  const data = await post(`/engine/start?interval=${interval}&symbols=${encodeURIComponent(symbols)}&exchange=${exchange}`, {});
  if (data.status === 'started') {
    document.getElementById('engine-status').innerHTML = `<span class="text-profit">Running! ${data.total_running} strategies on ${data.exchange}<br>Symbols: ${data.symbols.join(', ')}<br>Strategies: ${data.strategies_added.map(s => s.name).join(', ')}</span>`;
  } else if (data.status === 'already_running') {
    document.getElementById('engine-status').innerHTML = `<span class="text-warn">Already running (${data.strategies} strategies)</span>`;
  } else {
    document.getElementById('engine-status').innerHTML = `<span class="text-loss">${JSON.stringify(data)}</span>`;
  }
}
async function stopEngine() {
  const data = await post('/engine/stop', {});
  document.getElementById('engine-status').innerHTML = `<span class="text-warn">${JSON.stringify(data)}</span>`;
}
async function killSwitch(activate) {
  const path = activate ? '/risk/kill-switch/activate' : '/risk/kill-switch/deactivate';
  await post(path, {});
  refreshDashboard();
}
async function connectExchange() {
  const data = await post('/exchange/connect', {
    exchange_id: document.getElementById('exchange-id').value,
    api_key: document.getElementById('api-key').value,
    api_secret: document.getElementById('api-secret').value,
    sandbox: document.getElementById('sandbox-mode').checked,
  });
  document.getElementById('exchange-result').innerHTML = data.error
    ? `<span class="text-loss">${data.error}</span>`
    : `<span class="text-profit">Connected!</span>`;
}
async function promoteStrategy() {
  const id = document.getElementById('promote-id').value;
  const data = await post(`/paper/promote/${id}`, {});
  document.getElementById('promote-result').innerHTML = data.error
    ? `<span class="text-loss">${JSON.stringify(data)}</span>`
    : `<span class="text-profit">${JSON.stringify(data)}</span>`;
}
function promoteFromLB(id) {
  document.getElementById('promote-id').value = id;
  switchTab('control');
  promoteStrategy();
}

// ─── WebSocket ───
function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/signals`);
  ws.onopen = () => {
    document.getElementById('ws-dot').className = 'w-2 h-2 rounded-full bg-profit';
    document.getElementById('ws-label').textContent = 'live';
  };
  ws.onclose = () => {
    document.getElementById('ws-dot').className = 'w-2 h-2 rounded-full bg-danger';
    document.getElementById('ws-label').textContent = 'disconnected';
    setTimeout(connectWS, 3000);
  };
  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === 'signal') {
        signalBuffer.push(msg.data);
        if (signalBuffer.length > 200) signalBuffer = signalBuffer.slice(-200);
      }
    } catch {}
  };
}

// ─── Clock ───
function updateClock() {
  document.getElementById('clock').textContent = new Date().toLocaleTimeString();
}

// ─── Init ───
connectWS();
refreshDashboard();
setInterval(refreshDashboard, 5000);
setInterval(updateClock, 1000);
updateClock();
</script>
</body>
</html>"""
