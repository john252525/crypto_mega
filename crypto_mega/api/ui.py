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
  .log-line { font-size: 11px; line-height: 1.6; white-space: pre-wrap; word-break: break-all; border-bottom: 1px solid #111; padding: 1px 0; }
  .signal-row { cursor: pointer; transition: background 0.15s; }
  .signal-row:hover { background: rgba(30,30,46,0.5); }
  .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.75); z-index: 100; display: flex; align-items: center; justify-content: center; }
  .modal-box { background: #12121a; border: 1px solid #1e1e2e; border-radius: 12px; max-width: 720px; width: 95%; max-height: 85vh; overflow-y: auto; padding: 24px; position: relative; }
  .modal-close { position: absolute; top: 12px; right: 16px; cursor: pointer; color: #666; font-size: 20px; }
  .modal-close:hover { color: #fff; }
  .candle-green { color: #00ff88; }
  .candle-red { color: #ff4444; }
  .indicator-row { display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid #1a1a2a; }
  .indicator-label { color: #888; }
  .indicator-value { font-weight: 600; }
  .sym-chip { display: inline-flex; align-items: center; gap: 2px; padding: 3px 8px; border-radius: 6px; font-size: 11px; cursor: pointer; border: 1px solid #1e1e2e; background: #0a0a0f; transition: all 0.15s; user-select: none; }
  .sym-chip:hover { border-color: #00ff88; }
  .sym-chip.selected { background: rgba(0,255,136,0.1); border-color: #00ff88; color: #00ff88; }
  .sym-grid { display: flex; flex-wrap: wrap; gap: 4px; max-height: 180px; overflow-y: auto; padding: 6px 0; }
  .sym-picker-actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
  .sym-picker-btn { font-size: 10px; padding: 2px 8px; border-radius: 4px; cursor: pointer; border: 1px solid #1e1e2e; background: #12121a; color: #888; transition: all 0.15s; }
  .sym-picker-btn:hover { border-color: #00bfff; color: #00bfff; }
  .sym-search { background: #0a0a0f; border: 1px solid #1e1e2e; border-radius: 4px; padding: 3px 8px; font-size: 11px; color: #ccc; outline: none; width: 120px; }
  .sym-search:focus { border-color: #00ff88; }
  .log-DEBUG { color: #555; }
  .log-INFO { color: #8bc34a; }
  .log-WARNING { color: #ff9800; }
  .log-ERROR { color: #f44336; font-weight: bold; }
  .log-CRITICAL { color: #ff0000; font-weight: bold; background: #330000; }
</style>
</head>
<body class="text-gray-300 min-h-screen">

<!-- Header -->
<header class="border-b border-border px-6 py-3 flex items-center justify-between sticky top-0 bg-bg/95 backdrop-blur z-50">
  <div class="flex items-center gap-4">
    <h1 class="text-accent font-bold text-lg">CryptoMega</h1>
    <span class="text-xs text-gray-600">signal tournament</span>
  </div>
  <div class="flex items-center gap-4 text-xs">
    <!-- System health indicators -->
    <div class="flex items-center gap-3" id="health-bar">
      <span class="flex items-center gap-1" title="Engine"><span class="w-2 h-2 rounded-full bg-gray-600" id="hb-engine"></span> Engine</span>
      <span class="flex items-center gap-1" title="Exchange"><span class="w-2 h-2 rounded-full bg-gray-600" id="hb-exchange"></span> <span id="hb-exchange-name">---</span></span>
      <span class="flex items-center gap-1" title="Database"><span class="w-2 h-2 rounded-full bg-gray-600" id="hb-db"></span> DB</span>
      <span class="flex items-center gap-1" title="Data freshness"><span class="w-2 h-2 rounded-full bg-gray-600" id="hb-data"></span> Data</span>
    </div>
    <span class="text-gray-700">|</span>
    <div id="ws-status" class="flex items-center gap-1">
      <span class="w-2 h-2 rounded-full bg-danger" id="ws-dot"></span>
      <span id="ws-label">disconnected</span>
    </div>
    <span class="text-gray-600" id="clock"></span>
  </div>
</header>

<!-- Alert banner -->
<div id="alert-banner" class="hidden px-6 py-2 text-xs border-b border-border bg-card"></div>

<!-- Tabs -->
<nav class="border-b border-border px-6 flex gap-6 text-sm">
  <button class="py-3 px-1 tab-active" data-tab="dashboard" onclick="switchTab('dashboard')">Dashboard</button>
  <button class="py-3 px-1 text-gray-500 hover:text-gray-300" data-tab="leaderboard" onclick="switchTab('leaderboard')">Leaderboard</button>
  <button class="py-3 px-1 text-gray-500 hover:text-gray-300" data-tab="signals" onclick="switchTab('signals')">Signals</button>
  <button class="py-3 px-1 text-gray-500 hover:text-gray-300" data-tab="positions" onclick="switchTab('positions')">Positions</button>
  <button class="py-3 px-1 text-gray-500 hover:text-gray-300" data-tab="strategies" onclick="switchTab('strategies')">Strategies</button>
  <button class="py-3 px-1 text-gray-500 hover:text-gray-300" data-tab="explore" onclick="switchTab('explore')">Explore</button>
  <button class="py-3 px-1 text-gray-500 hover:text-gray-300" data-tab="data" onclick="switchTab('data')">Data</button>
  <button class="py-3 px-1 text-gray-500 hover:text-gray-300" data-tab="logs" onclick="switchTab('logs')">Logs</button>
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

    <!-- Sub-tabs -->
    <div class="flex gap-4 mb-4 border-b border-border">
      <button class="py-2 px-1 text-accent border-b-2 border-accent text-sm" data-stab="loaded" onclick="switchStratTab('loaded')">Loaded Strategies</button>
      <button class="py-2 px-1 text-gray-500 hover:text-gray-300 text-sm" data-stab="generator" onclick="switchStratTab('generator')">Strategy Generator</button>
      <button class="py-2 px-1 text-gray-500 hover:text-gray-300 text-sm" data-stab="guide" onclick="switchStratTab('guide')">How-To Guide</button>
    </div>

    <!-- ─── Loaded Strategies ─── -->
    <div id="stab-loaded">
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4" id="strategy-grid">
        <div class="text-gray-600">Loading...</div>
      </div>
      <div class="mt-4 bg-card border border-border rounded-lg p-4">
        <h3 class="text-blue text-sm font-semibold mb-3">Load from Directory</h3>
        <div class="flex gap-2">
          <input id="load-dir" type="text" value="strategies_user" class="flex-1 bg-bg border border-border rounded px-3 py-2 text-sm">
          <button onclick="loadDir()" class="px-4 py-2 bg-accent/20 text-accent rounded hover:bg-accent/30 text-sm">Load</button>
        </div>
        <div id="load-result" class="mt-2 text-xs"></div>
      </div>
    </div>

    <!-- ─── Strategy Generator ─── -->
    <div id="stab-generator" class="hidden">
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <!-- Template picker -->
        <div class="bg-card border border-border rounded-lg p-4">
          <h3 class="text-accent text-sm font-semibold mb-3">1. Pick Template</h3>
          <div id="template-list" class="space-y-2"></div>
        </div>
        <!-- Parameter editor -->
        <div class="bg-card border border-border rounded-lg p-4">
          <h3 class="text-accent text-sm font-semibold mb-3">2. Configure</h3>
          <div id="template-params" class="space-y-3">
            <div class="text-gray-600 text-xs">Select a template first</div>
          </div>
        </div>
        <!-- Preview + deploy -->
        <div class="bg-card border border-border rounded-lg p-4">
          <h3 class="text-accent text-sm font-semibold mb-3">3. Deploy</h3>
          <div class="space-y-3">
            <div>
              <label class="text-xs text-gray-500">Symbols</label>
              <div id="gen-symbols-picker" class="mt-1"></div>
            </div>
            <div>
              <label class="text-xs text-gray-500">Priority (0-100)</label>
              <input id="gen-priority" type="number" value="50" min="0" max="100" class="w-full bg-bg border border-border rounded px-2 py-1 text-sm mt-1">
            </div>
            <button onclick="deployStrategy()" class="w-full px-4 py-2 bg-accent/20 text-accent rounded hover:bg-accent/30 text-sm">Deploy Strategy</button>
            <div id="gen-result" class="text-xs"></div>
            <hr class="border-border">
            <h4 class="text-xs text-gray-400 font-semibold">Batch Deploy</h4>
            <p class="text-xs text-gray-600">Generate multiple strategies at once by iterating parameters.</p>
            <button onclick="batchDeploy()" class="w-full px-4 py-2 bg-blue/20 text-blue rounded hover:bg-blue/30 text-sm">Batch Deploy (all grid combos)</button>
            <div id="batch-result" class="text-xs"></div>
          </div>
        </div>
      </div>
      <div class="mt-4 bg-card border border-border rounded-lg p-4">
        <h3 class="text-sm font-semibold text-gray-400 mb-2">Code Preview</h3>
        <pre id="gen-code-preview" class="text-xs text-gray-500 overflow-auto max-h-64 bg-bg p-3 rounded"></pre>
      </div>
    </div>

    <!-- ─── Guide ─── -->
    <div id="stab-guide" class="hidden">
      <div class="max-w-3xl space-y-6">
        <div class="bg-card border border-border rounded-lg p-5">
          <h3 class="text-accent font-semibold mb-3">Quick Start: Create a Strategy in 60 seconds</h3>
          <ol class="text-sm text-gray-300 space-y-2 list-decimal list-inside">
            <li>Go to <span class="text-accent">Strategy Generator</span> tab</li>
            <li>Pick a template (SMA Crossover, RSI, Momentum, Breakout)</li>
            <li>Tweak parameters on the right panel</li>
            <li>Click <span class="text-accent">Deploy Strategy</span> to load it instantly</li>
            <li>Or click <span class="text-blue">Batch Deploy</span> to generate all param grid combinations at once</li>
          </ol>
        </div>

        <div class="bg-card border border-border rounded-lg p-5">
          <h3 class="text-accent font-semibold mb-3">Strategy Categories</h3>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
            <div class="p-3 rounded bg-bg">
              <div class="text-green-400 font-semibold">Trend Following</div>
              <div class="text-gray-500 text-xs mt-1">Rides momentum. Great in bull/bear markets. Gets chopped in sideways. Examples: SMA Cross, EMA Momentum.</div>
            </div>
            <div class="p-3 rounded bg-bg">
              <div class="text-purple-400 font-semibold">Mean Reversion</div>
              <div class="text-gray-500 text-xs mt-1">Catches bounces from extremes. Best in ranging markets. Dangerous in strong trends. Examples: RSI+BB, MACD divergence.</div>
            </div>
            <div class="p-3 rounded bg-bg">
              <div class="text-blue-400 font-semibold">Momentum</div>
              <div class="text-gray-500 text-xs mt-1">Enters when price + volume accelerate. Needs volume confirmation. Best for catching big moves. Examples: EMA slope + volume.</div>
            </div>
            <div class="p-3 rounded bg-bg">
              <div class="text-orange-400 font-semibold">Breakout</div>
              <div class="text-gray-500 text-xs mt-1">Trades price breaking out of ranges. Many false signals, but winners are big. Examples: Channel breakout, Donchian.</div>
            </div>
          </div>
        </div>

        <div class="bg-card border border-border rounded-lg p-5">
          <h3 class="text-accent font-semibold mb-3">Writing Custom Strategies</h3>
          <div class="text-sm text-gray-300 space-y-2">
            <p>Create a <code class="text-accent">.py</code> file in <code class="text-accent">strategies_user/</code> folder:</p>
            <pre class="bg-bg p-3 rounded text-xs overflow-auto text-gray-400">from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig

class MyStrategy(BaseStrategy):
    DESCRIPTION = "What this strategy does"
    CATEGORY = "trend"          # trend | mean-reversion | momentum | breakout
    RISK_LEVEL = "medium"       # low | medium | high
    BEST_TIMEFRAMES = ["1h"]
    BEST_MARKETS = ["trending"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.my_param = config.parameters.get("my_param", 14)

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []
        for key, df in data.items():
            symbol = key.split("_")[0]
            # Your logic here...
            # signals.append(Signal(symbol=symbol, direction=SignalDirection.LONG, ...))
        return signals

    def param_grid(self):
        return {"my_param": [7, 14, 21]}

    def param_defaults(self):
        return {"my_param": 14}

    def param_descriptions(self):
        return {"my_param": "Lookback period for the indicator"}</pre>
            <p>Then load it via the <strong>Load from Directory</strong> button or restart the system.</p>
          </div>
        </div>

        <div class="bg-card border border-border rounded-lg p-5">
          <h3 class="text-accent font-semibold mb-3">Pro Tips</h3>
          <ul class="text-sm text-gray-400 space-y-1 list-disc list-inside">
            <li><strong>Batch optimization:</strong> Define <code>param_grid()</code> and use Backtest to find best params</li>
            <li><strong>Multiple timeframes:</strong> Override <code>required_timeframes()</code> for multi-TF confluence</li>
            <li><strong>Risk management:</strong> Always set <code>stop_loss</code> and <code>take_profit</code> on signals</li>
            <li><strong>API deploy:</strong> POST to <code>/strategies/load-code</code> with Python code string</li>
            <li><strong>Combine strategies:</strong> Run trend + reversion together for hedge diversification</li>
          </ul>
        </div>
      </div>
    </div>

  </div>

  <!-- ═══ LOGS TAB ═══ -->
  <div id="tab-logs" class="hidden fade-in">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold text-accent">System Logs</h2>
      <div class="flex items-center gap-3">
        <label class="flex items-center gap-1 text-xs"><input type="checkbox" id="log-auto" checked onchange="toggleAutoScroll()"> Auto-scroll</label>
        <select id="log-level-filter" class="bg-card border border-border rounded px-2 py-1 text-xs" onchange="filterLogs()">
          <option value="all">All levels</option>
          <option value="DEBUG">DEBUG</option>
          <option value="INFO">INFO</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
        </select>
        <input type="text" id="log-search" placeholder="Filter text..." class="bg-card border border-border rounded px-2 py-1 text-xs w-40" oninput="filterLogs()">
        <button onclick="clearLogs()" class="text-xs px-2 py-1 bg-card border border-border rounded hover:border-danger text-gray-500">Clear</button>
        <span class="text-xs text-gray-600" id="log-count">0 entries</span>
      </div>
    </div>
    <div id="log-container" class="bg-card border border-border rounded-lg p-3 font-mono overflow-y-auto" style="height: calc(100vh - 180px); max-height: 800px;">
      <div class="text-gray-600 text-xs">Connecting to log stream...</div>
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
          <label class="text-xs text-gray-500">Symbols</label>
          <div id="engine-symbols-picker" class="mt-1"></div>
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

  <!-- ═══ EXPLORATION TAB ═══ -->
  <div id="tab-explore" class="hidden fade-in space-y-6">

    <!-- Explorer Status Cards -->
    <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
      <div class="bg-card border border-border rounded-lg p-3 text-center">
        <div class="text-gray-500 text-xs mb-1">Explorer</div>
        <div id="explore-status" class="text-2xl font-bold text-gray-600">—</div>
        <div id="explore-status-detail" class="text-xs text-gray-600 mt-1">—</div>
      </div>
      <div class="bg-card border border-border rounded-lg p-3 text-center">
        <div class="text-gray-500 text-xs mb-1">Total Results</div>
        <div id="explore-total-results" class="text-2xl font-bold">0</div>
      </div>
      <div class="bg-card border border-border rounded-lg p-3 text-center">
        <div class="text-gray-500 text-xs mb-1">Symbols Tested</div>
        <div id="explore-unique-symbols" class="text-2xl font-bold">0</div>
      </div>
      <div class="bg-card border border-border rounded-lg p-3 text-center">
        <div class="text-gray-500 text-xs mb-1">Strategies Tested</div>
        <div id="explore-unique-strategies" class="text-2xl font-bold">0</div>
      </div>
      <div class="bg-card border border-border rounded-lg p-3 text-center">
        <div class="text-gray-500 text-xs mb-1">Workers Online</div>
        <div id="explore-workers" class="text-2xl font-bold">0</div>
      </div>
      <div class="bg-card border border-border rounded-lg p-3 text-center">
        <div class="text-gray-500 text-xs mb-1">Promoted</div>
        <div id="explore-promoted" class="text-2xl font-bold text-accent">0</div>
      </div>
    </div>

    <!-- Task pipeline -->
    <div class="bg-card border border-border rounded-lg p-4">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-bold">Task Pipeline</h3>
        <div class="flex gap-2">
          <button onclick="explorerAction('start')" class="px-3 py-1 bg-accent/10 text-accent rounded text-xs hover:bg-accent/20">Start Explorer</button>
          <button onclick="explorerAction('stop')" class="px-3 py-1 bg-warn/10 text-warn rounded text-xs hover:bg-warn/20">Stop</button>
          <button onclick="explorerAction('generate')" class="px-3 py-1 bg-blue/10 text-blue rounded text-xs hover:bg-blue/20">Generate 50 Tasks</button>
          <button onclick="explorerAction('refresh-symbols')" class="px-3 py-1 bg-gray-500/10 text-gray-400 rounded text-xs hover:bg-gray-500/20">Refresh Symbols</button>
        </div>
      </div>
      <div class="grid grid-cols-4 gap-3 text-center">
        <div class="bg-bg rounded p-2"><div class="text-xs text-gray-500">Pending</div><div id="explore-pending" class="text-lg font-bold">0</div></div>
        <div class="bg-bg rounded p-2"><div class="text-xs text-gray-500">Running</div><div id="explore-running" class="text-lg font-bold text-blue">0</div></div>
        <div class="bg-bg rounded p-2"><div class="text-xs text-gray-500">Done</div><div id="explore-done" class="text-lg font-bold text-accent">0</div></div>
        <div class="bg-bg rounded p-2"><div class="text-xs text-gray-500">Failed</div><div id="explore-failed" class="text-lg font-bold text-danger">0</div></div>
      </div>
    </div>

    <!-- Exploration Leaderboard -->
    <div class="bg-card border border-border rounded-lg p-4">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-bold">Exploration Leaderboard — Best Discoveries</h3>
        <div class="flex gap-2 items-center">
          <select id="explore-sort" onchange="loadExploreLeaderboard()" class="bg-bg border border-border rounded px-2 py-1 text-xs">
            <option value="sharpe_ratio">Sharpe Ratio</option>
            <option value="total_pnl_pct">P&L %</option>
            <option value="win_rate">Win Rate</option>
            <option value="profit_factor">Profit Factor</option>
          </select>
          <button onclick="loadExploreLeaderboard()" class="px-3 py-1 bg-blue/10 text-blue rounded text-xs hover:bg-blue/20">Refresh</button>
        </div>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-xs">
          <thead>
            <tr class="text-gray-500 border-b border-border">
              <th class="text-left py-2 px-2">#</th>
              <th class="text-left py-2 px-2">Strategy</th>
              <th class="text-left py-2 px-2">Symbol</th>
              <th class="text-left py-2 px-2">TF</th>
              <th class="text-right py-2 px-2">Sharpe</th>
              <th class="text-right py-2 px-2">P&L %</th>
              <th class="text-right py-2 px-2">Win Rate</th>
              <th class="text-right py-2 px-2">PF</th>
              <th class="text-right py-2 px-2">Trades</th>
              <th class="text-right py-2 px-2">Max DD</th>
              <th class="text-left py-2 px-2">Params</th>
              <th class="text-center py-2 px-2">Status</th>
            </tr>
          </thead>
          <tbody id="explore-lb-body"></tbody>
        </table>
      </div>
      <div id="explore-lb-empty" class="text-center text-gray-600 text-xs py-6">No exploration results yet. Start the explorer to begin discovering alpha.</div>
    </div>

    <!-- Available Symbols -->
    <div class="bg-card border border-border rounded-lg p-4">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-bold">Available Symbols by Exchange</h3>
      </div>
      <div id="explore-symbols-list" class="text-xs text-gray-400">No symbols discovered yet</div>
    </div>

  </div>

  <!-- ═══ DATA INTEGRITY TAB ═══ -->
  <div id="tab-data" class="hidden fade-in space-y-6">

    <!-- Summary cards -->
    <div class="grid grid-cols-5 gap-4">
      <div class="bg-card border border-border rounded-lg p-4">
        <div class="text-xs text-gray-500 mb-1">Total Candles</div>
        <div class="text-2xl font-bold text-accent" id="data-total-candles">—</div>
      </div>
      <div class="bg-card border border-border rounded-lg p-4">
        <div class="text-xs text-gray-500 mb-1">Symbols</div>
        <div class="text-2xl font-bold text-blue" id="data-total-symbols">—</div>
      </div>
      <div class="bg-card border border-border rounded-lg p-4">
        <div class="text-xs text-gray-500 mb-1">Timeframes</div>
        <div class="text-2xl font-bold text-blue" id="data-total-tf">—</div>
      </div>
      <div class="bg-card border border-border rounded-lg p-4">
        <div class="text-xs text-gray-500 mb-1">DB Status</div>
        <div class="text-2xl font-bold" id="data-db-status">—</div>
      </div>
      <div class="bg-card border border-border rounded-lg p-4">
        <div class="text-xs text-gray-500 mb-1">Collector</div>
        <div class="text-2xl font-bold" id="data-collector-status">—</div>
        <div class="text-xs text-gray-600 mt-1" id="data-collector-detail"></div>
      </div>
    </div>

    <!-- Series overview table -->
    <div class="bg-card border border-border rounded-lg p-4">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-sm font-bold">Candle Series Overview</h3>
        <button onclick="loadDataSummary()" class="px-3 py-1 bg-accent/10 text-accent rounded text-xs hover:bg-accent/20">Refresh</button>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-xs">
          <thead>
            <tr class="text-gray-500 border-b border-border">
              <th class="text-left py-2 px-2">Symbol</th>
              <th class="text-left py-2 px-2">TF</th>
              <th class="text-right py-2 px-2">Candles</th>
              <th class="text-left py-2 px-2">From</th>
              <th class="text-left py-2 px-2">To</th>
              <th class="text-left py-2 px-2">Days</th>
              <th class="text-left py-2 px-2">Last Checked</th>
              <th class="text-left py-2 px-2">Data Changed</th>
              <th class="text-left py-2 px-2">Interval</th>
            </tr>
          </thead>
          <tbody id="data-series-table"></tbody>
        </table>
      </div>
      <div id="data-series-empty" class="hidden text-center text-gray-600 text-xs py-8">No candle data in database yet</div>
    </div>

    <!-- Gap checker -->
    <div class="bg-card border border-border rounded-lg p-4">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-sm font-bold">Integrity Check — Gap Detection</h3>
        <div class="flex gap-2 items-center">
          <select id="gap-symbol" class="bg-bg border border-border rounded px-2 py-1 text-xs">
            <option value="">All symbols</option>
          </select>
          <select id="gap-tf" class="bg-bg border border-border rounded px-2 py-1 text-xs">
            <option value="">All timeframes</option>
          </select>
          <button onclick="runGapCheck()" id="gap-check-btn" class="px-3 py-1 bg-blue/10 text-blue rounded text-xs hover:bg-blue/20">Run Check</button>
        </div>
      </div>
      <div id="gap-results" class="space-y-3"></div>
      <div id="gap-empty" class="text-center text-gray-600 text-xs py-6">Select filters and click "Run Check" to analyze candle continuity</div>
    </div>
  </div>

</main>

<!-- Signal/Position detail modal -->
<div id="detail-modal" class="modal-overlay hidden" onclick="if(event.target===this)closeDetailModal()">
  <div class="modal-box">
    <span class="modal-close" onclick="closeDetailModal()">&times;</span>
    <div id="detail-modal-content"></div>
  </div>
</div>

<script>
// ─── State ───
let ws = null;
let currentTab = 'dashboard';
let signalBuffer = [];

// ─── API helpers ───
const api = (path, opts) => fetch(path, opts).then(r => r.json()).catch(e => ({ error: e.message }));
const post = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

// ─── Tab switching with URL hash ───
function switchTab(tab, pushState = true) {
  document.querySelectorAll('[data-tab]').forEach(b => {
    b.classList.toggle('tab-active', b.dataset.tab === tab);
    b.classList.toggle('text-gray-500', b.dataset.tab !== tab);
  });
  document.querySelectorAll('[id^="tab-"]').forEach(el => {
    el.classList.toggle('hidden', el.id !== 'tab-' + tab);
  });
  currentTab = tab;
  if (pushState) {
    history.pushState(null, '', '#' + tab);
  }
  refreshTab();
}

// Read hash on load and on back/forward navigation
window.addEventListener('hashchange', () => {
  const tab = location.hash.replace('#', '') || 'dashboard';
  if (tab !== currentTab) switchTab(tab, false);
});
window.addEventListener('DOMContentLoaded', () => {
  const tab = location.hash.replace('#', '') || 'dashboard';
  if (tab !== 'dashboard') switchTab(tab, false);
});

function refreshTab() {
  if (currentTab === 'leaderboard') loadLeaderboard();
  if (currentTab === 'positions') loadPositions('open');
  if (currentTab === 'strategies') loadStrategies();
  if (currentTab === 'signals') loadSignalFeed();
  if (currentTab === 'logs') filterLogs();
  if (currentTab === 'data') loadDataSummary();
  if (currentTab === 'explore') loadExploreTab();
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
      html += `<div class="signal-row flex justify-between py-0.5 border-b border-border/30" onclick="showSignalDetail('${s.id}')"><span><span class="${color} font-bold uppercase">${s.direction}</span> ${s.symbol} @ ${s.price.toFixed(2)}</span><span class="text-gray-600">${s.strategy_name || s.strategy_id} | str=${s.strength} | ${time}</span></div>`;
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
    return `<div class="signal-row flex justify-between py-1 border-b border-border/30" onclick="showSignalDetail('${s.id}')">
      <span><span class="${color} font-bold uppercase w-12 inline-block">${s.direction}</span> <span class="text-blue">${s.symbol}</span> @ ${s.price.toFixed(2)}${sl}${tp}</span>
      <span class="text-gray-600">${s.strategy_name || s.strategy_id} | str=${s.strength} | ${time}</span>
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
      return `<tr class="signal-row border-b border-border/30" onclick="showPositionDetail('${p.id}')"><td class="py-1 px-2">${p.strategy_name}<br><span class="text-gray-600">${p.strategy_id}</span></td><td class="py-1 px-2 text-blue">${p.symbol}</td><td class="py-1 px-2 ${dirColor} font-bold uppercase">${p.direction}</td><td class="py-1 px-2 text-right">${p.entry_price.toFixed(2)}</td><td class="py-1 px-2 text-right">${p.current_price.toFixed(2)}</td><td class="py-1 px-2 text-right ${color} font-bold">${p.unrealized_pnl_pct >= 0 ? '+' : ''}${p.unrealized_pnl_pct.toFixed(2)}%</td><td class="py-1 px-2 text-right">${p.stop_loss || '-'}</td><td class="py-1 px-2 text-right">${p.take_profit || '-'}</td></tr>`;
    }).join('');
  } else {
    header.innerHTML = '<th class="text-left py-2 px-2">Strategy</th><th class="text-left py-2 px-2">Symbol</th><th class="py-2 px-2">Dir</th><th class="text-right py-2 px-2">Entry</th><th class="text-right py-2 px-2">Exit</th><th class="text-right py-2 px-2">P&L %</th><th class="py-2 px-2">Reason</th><th class="py-2 px-2">Closed</th>';
    body.innerHTML = positions.map(p => {
      const color = p.realized_pnl_pct >= 0 ? 'text-profit' : 'text-loss';
      const dirColor = p.direction === 'long' ? 'text-profit' : 'text-loss';
      return `<tr class="signal-row border-b border-border/30" onclick="showPositionDetail('${p.id}')"><td class="py-1 px-2">${p.strategy_name}<br><span class="text-gray-600">${p.strategy_id}</span></td><td class="py-1 px-2 text-blue">${p.symbol}</td><td class="py-1 px-2 ${dirColor} font-bold uppercase">${p.direction}</td><td class="py-1 px-2 text-right">${p.entry_price.toFixed(2)}</td><td class="py-1 px-2 text-right">${(p.exit_price || 0).toFixed(2)}</td><td class="py-1 px-2 text-right ${color} font-bold">${p.realized_pnl_pct >= 0 ? '+' : ''}${p.realized_pnl_pct.toFixed(2)}%</td><td class="py-1 px-2 uppercase">${p.close_reason}</td><td class="py-1 px-2 text-gray-600">${p.closed_at ? new Date(p.closed_at).toLocaleString() : ''}</td></tr>`;
    }).join('');
  }
}

// ─── Strategies ───
const CATEGORY_COLORS = {
  trend: 'text-green-400', 'mean-reversion': 'text-purple-400',
  momentum: 'text-blue-400', breakout: 'text-orange-400',
  scalping: 'text-yellow-400', custom: 'text-gray-400'
};
const RISK_COLORS = { low: 'text-profit', medium: 'text-warn', high: 'text-loss' };

async function loadStrategies() {
  const data = await api('/strategies');
  const grid = document.getElementById('strategy-grid');
  if (!data.registered || Object.keys(data.registered).length === 0) {
    grid.innerHTML = '<div class="text-gray-600">No strategies loaded</div>';
    return;
  }
  const running = data.running || {};
  grid.innerHTML = Object.entries(data.registered).map(([name, info]) => {
    const runInfo = Object.values(running).find(r => r.name === name);
    const statusColor = runInfo ? (runInfo.status === 'running' ? 'text-profit' : 'text-warn') : 'text-gray-600';
    const statusText = runInfo ? runInfo.status : 'idle';
    const cat = info.category || 'custom';
    const catColor = CATEGORY_COLORS[cat] || 'text-gray-400';
    const risk = info.risk_level || 'medium';
    const riskColor = RISK_COLORS[risk] || 'text-gray-400';
    const desc = info.description || '';
    const params = info.parameters || {};
    const paramKeys = Object.keys(params);
    const tfs = (info.best_timeframes || []).join(', ');
    const markets = (info.best_markets || []).join(', ');
    const combos = info.total_grid_combos || 0;

    const paramHtml = paramKeys.length > 0 ? paramKeys.map(k => {
      const p = params[k];
      const gridVals = (p.grid || []).join(', ');
      return `<div class="flex justify-between">
        <span class="text-gray-400">${k}</span>
        <span class="text-gray-500">${p.default != null ? p.default : '-'}${p.description ? ` <span title="${p.description}" style="cursor:help">(?)</span>` : ''}</span>
      </div>
      ${gridVals ? `<div class="text-gray-600 text-[10px] -mt-1">grid: [${gridVals}]</div>` : ''}`;
    }).join('') : '<div class="text-gray-600">No configurable params</div>';

    return `<div class="bg-card border border-border rounded-lg p-4">
      <div class="flex justify-between items-start mb-1">
        <h4 class="font-semibold text-sm">${name}</h4>
        <span class="${statusColor} text-xs uppercase font-bold">${statusText}</span>
      </div>
      <div class="flex gap-2 mb-2">
        <span class="${catColor} text-xs border border-current/20 rounded px-1.5 py-0.5">${cat}</span>
        <span class="${riskColor} text-xs border border-current/20 rounded px-1.5 py-0.5">risk: ${risk}</span>
        ${tfs ? `<span class="text-gray-500 text-xs">TF: ${tfs}</span>` : ''}
      </div>
      <p class="text-xs text-gray-400 mb-3 leading-relaxed">${desc}</p>
      ${markets ? `<div class="text-xs text-gray-600 mb-2">Best for: ${markets}</div>` : ''}
      <details class="text-xs">
        <summary class="cursor-pointer text-gray-500 hover:text-gray-300">Parameters (${paramKeys.length}) ${combos > 1 ? `&mdash; ${combos} grid combos` : ''}</summary>
        <div class="mt-2 space-y-1 font-mono text-[11px]">${paramHtml}</div>
      </details>
      ${runInfo ? `<div class="mt-3 pt-2 border-t border-border text-xs text-gray-500 flex gap-3">
        <span>Signals: <b class="text-gray-300">${runInfo.signals}</b></span>
        <span>Priority: <b class="text-gray-300">${runInfo.priority}</b></span>
        <span>Errors: <b class="${runInfo.errors.length > 0 ? 'text-loss' : 'text-gray-300'}">${runInfo.errors.length}</b></span>
      </div>` : ''}
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

// ─── Strategy sub-tabs ───
let currentStratTab = 'loaded';
function switchStratTab(tab) {
  currentStratTab = tab;
  document.querySelectorAll('[id^="stab-"]').forEach(el => el.classList.add('hidden'));
  document.getElementById('stab-' + tab).classList.remove('hidden');
  document.querySelectorAll('[data-stab]').forEach(el => {
    el.className = el.dataset.stab === tab
      ? 'py-2 px-1 text-accent border-b-2 border-accent text-sm'
      : 'py-2 px-1 text-gray-500 hover:text-gray-300 text-sm';
  });
  if (tab === 'generator') loadTemplates();
}

// ─── Strategy Generator ───
let templates = {};
let selectedTemplate = null;

async function loadTemplates() {
  const data = await api('/strategies/templates');
  templates = data.templates || {};
  const list = document.getElementById('template-list');
  list.innerHTML = Object.entries(templates).map(([key, t]) => {
    const catColor = CATEGORY_COLORS[t.category] || 'text-gray-400';
    return `<div class="p-3 rounded border border-border cursor-pointer hover:border-accent transition-colors ${selectedTemplate === key ? 'border-accent bg-accent/5' : ''}" onclick="selectTemplate('${key}')">
      <div class="flex justify-between items-center">
        <span class="font-semibold text-sm">${t.label}</span>
        <span class="${catColor} text-xs">${t.category}</span>
      </div>
      <p class="text-xs text-gray-500 mt-1">${t.description}</p>
    </div>`;
  }).join('');
}

function selectTemplate(key) {
  selectedTemplate = key;
  loadTemplates();
  const t = templates[key];
  const container = document.getElementById('template-params');
  container.innerHTML = Object.entries(t.params).map(([pk, pv]) => {
    if (pv.type === 'select') {
      const opts = (pv.options || []).map(o => `<option value="${o}" ${o === pv.default ? 'selected' : ''}>${o}</option>`).join('');
      return `<div>
        <label class="text-xs text-gray-500">${pv.label}</label>
        <select data-param="${pk}" class="w-full bg-bg border border-border rounded px-2 py-1 text-sm mt-1">${opts}</select>
      </div>`;
    }
    return `<div>
      <label class="text-xs text-gray-500">${pv.label}</label>
      <input data-param="${pk}" type="${pv.type === 'int' || pv.type === 'float' ? 'number' : 'text'}"
        value="${pv.default}" step="${pv.type === 'float' ? '0.01' : '1'}"
        class="w-full bg-bg border border-border rounded px-2 py-1 text-sm mt-1"
        oninput="updateCodePreview()">
    </div>`;
  }).join('');
  updateCodePreview();
}

function getTemplateParamValues() {
  const vals = {};
  document.querySelectorAll('#template-params [data-param]').forEach(el => {
    vals[el.dataset.param] = el.value;
  });
  return vals;
}

function renderTemplateCode() {
  if (!selectedTemplate) return '';
  const t = templates[selectedTemplate];
  let code = t.code;
  const vals = getTemplateParamValues();
  for (const [k, v] of Object.entries(vals)) {
    code = code.replaceAll('{' + k + '}', v);
  }
  return code;
}

function updateCodePreview() {
  document.getElementById('gen-code-preview').textContent = renderTemplateCode();
}

async function deployStrategy() {
  if (!selectedTemplate) { alert('Select a template first'); return; }
  const vals = getTemplateParamValues();
  const code = renderTemplateCode();
  const symbols = getPickerSymbolsArray('gen-symbols-picker');
  const priority = parseInt(document.getElementById('gen-priority').value) || 50;

  const data = await post('/strategies/load-code', {
    code: code,
    name: vals.class_name || 'Generated',
    description: vals.description || '',
    symbols: symbols,
    priority: priority,
  });
  document.getElementById('gen-result').innerHTML = data.strategies
    ? `<span class="text-profit">Deployed: ${data.strategies.map(s => s.name).join(', ')}</span>`
    : `<span class="text-loss">Error: ${JSON.stringify(data.detail || data)}</span>`;
  loadStrategies();
}

async function batchDeploy() {
  if (!selectedTemplate) { alert('Select a template first'); return; }
  const t = templates[selectedTemplate];
  const vals = getTemplateParamValues();
  const symbols = getPickerSymbolsArray('gen-symbols-picker');
  const priority = parseInt(document.getElementById('gen-priority').value) || 50;
  const baseName = vals.class_name || 'Batch';

  // Find numeric params that have grid values in the template
  const gridParams = {};
  for (const [pk, pv] of Object.entries(t.params)) {
    if (pv.type === 'int' || pv.type === 'float') {
      gridParams[pk] = pv;
    }
  }

  // Generate all combinations of the 2 most impactful numeric params
  const paramNames = Object.keys(gridParams).slice(0, 2);
  let combos = [{}];
  for (const pn of paramNames) {
    const pv = gridParams[pn];
    const baseVal = parseFloat(vals[pn]) || pv.default;
    // Create 3 variations: 0.7x, 1x, 1.5x
    const variations = [
      Math.round(baseVal * 0.7 * 100) / 100,
      baseVal,
      Math.round(baseVal * 1.5 * 100) / 100,
    ];
    const newCombos = [];
    for (const c of combos) {
      for (const v of variations) {
        newCombos.push({...c, [pn]: v});
      }
    }
    combos = newCombos;
  }

  const results = [];
  const batchEl = document.getElementById('batch-result');
  batchEl.innerHTML = `<span class="text-warn">Deploying ${combos.length} strategies...</span>`;

  for (let i = 0; i < combos.length; i++) {
    const combo = combos[i];
    const suffix = Object.values(combo).join('_');
    const overrides = {...vals, ...Object.fromEntries(Object.entries(combo).map(([k, v]) => [k, String(v)]))};
    overrides.class_name = baseName + '_' + suffix.replace(/\\./g, 'd');
    let code = t.code;
    for (const [k, v] of Object.entries(overrides)) {
      code = code.replaceAll('{' + k + '}', v);
    }
    try {
      const data = await post('/strategies/load-code', {
        code: code,
        name: overrides.class_name,
        description: `${vals.description} [${Object.entries(combo).map(([k,v]) => k+'='+v).join(', ')}]`,
        symbols: symbols,
        priority: priority,
      });
      if (data.strategies) results.push(...data.strategies.map(s => s.name));
    } catch (e) {
      results.push('ERROR: ' + e);
    }
  }

  batchEl.innerHTML = `<span class="text-profit">Deployed ${results.length} strategies: ${results.join(', ')}</span>`;
  loadStrategies();
}

// ─── Control actions ───
async function startEngine() {
  const exchange = document.getElementById('engine-exchange').value;
  const symbols = getPickerSymbols('engine-symbols-picker');
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

// ─── System Health ───
async function refreshHealth() {
  try {
    const h = await api('/health');
    if (!h) return;

    // Engine indicator
    const engDot = document.getElementById('hb-engine');
    engDot.className = `w-2 h-2 rounded-full ${h.engine_running ? 'bg-profit' : 'bg-danger'}`;
    engDot.parentElement.title = h.engine_running
      ? `Engine running: ${h.strategies_running} strategies`
      : 'Engine stopped — go to Control tab to start';

    // Exchange indicator
    const exDot = document.getElementById('hb-exchange');
    const exName = document.getElementById('hb-exchange-name');
    if (h.exchange && h.exchange !== 'none') {
      exDot.className = 'w-2 h-2 rounded-full bg-profit';
      exName.textContent = h.exchange;
      exDot.parentElement.title = `Connected to ${h.exchange}`;
    } else {
      exDot.className = 'w-2 h-2 rounded-full bg-danger';
      exName.textContent = 'none';
      exDot.parentElement.title = 'No exchange connected';
    }

    // DB indicator
    const dbDot = document.getElementById('hb-db');
    if (h.db === 'connected') {
      dbDot.className = 'w-2 h-2 rounded-full bg-profit';
      dbDot.parentElement.title = 'Database connected (PostgreSQL)';
    } else {
      dbDot.className = 'w-2 h-2 rounded-full bg-warn';
      dbDot.parentElement.title = 'No database — data wont persist. Add PostgreSQL in Railway.';
    }

    // Data freshness
    const dataDot = document.getElementById('hb-data');
    if (h.data_status === 'ok') {
      dataDot.className = 'w-2 h-2 rounded-full bg-profit';
      dataDot.parentElement.title = `Data fresh (${h.data_age_sec}s old)`;
    } else if (h.data_status === 'stale') {
      dataDot.className = 'w-2 h-2 rounded-full bg-warn';
      dataDot.parentElement.title = `Data stale (${h.data_age_sec}s old)`;
    } else if (h.data_status === 'critical') {
      dataDot.className = 'w-2 h-2 rounded-full bg-danger pulse';
      dataDot.parentElement.title = `Data critically old (${h.data_age_sec}s)!`;
    } else {
      dataDot.className = 'w-2 h-2 rounded-full bg-gray-600';
      dataDot.parentElement.title = 'No data yet';
    }

    // Alert banner — show only last 3 unique alerts from the past 10 minutes
    const banner = document.getElementById('alert-banner');
    if (h.alerts && h.alerts.length > 0) {
      const recent = h.alerts.filter(a => (Date.now()/1000 - a.ts) < 600);
      // Deduplicate by component
      const seen = new Set();
      const unique = [];
      for (const a of recent.reverse()) {
        const k = a.component + ':' + a.level;
        if (!seen.has(k)) { seen.add(k); unique.push(a); }
      }
      if (unique.length > 0) {
        const show = unique.slice(0, 3);
        const hasErr = show.some(a => a.level === 'error');
        const html = show.map(a => {
          const cls = a.level === 'error' ? 'text-loss font-bold' : 'text-warn';
          const tag = a.level === 'error' ? 'ERR' : 'WARN';
          return `<span class="${cls} mr-4">${tag} [${a.component}]: ${a.message}</span>`;
        }).join('');
        banner.innerHTML = html;
        banner.className = 'px-6 py-2 text-xs border-b border-border ' +
          (hasErr ? 'bg-danger/10' : 'bg-warn/10');
      } else {
        banner.className = 'hidden';
      }
    } else {
      banner.className = 'hidden';
    }
  } catch (e) {
    // Health endpoint failed
  }
}

// ─── Logs ───
let logWs = null;
let logEntries = [];
let logAutoScroll = true;
const LOG_LEVELS = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3, CRITICAL: 4 };
const LOG_ICONS = { DEBUG: '  ', INFO: 'ℹ ', WARNING: '⚠ ', ERROR: '✖ ', CRITICAL: '🔥' };

function connectLogWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  logWs = new WebSocket(`${proto}://${location.host}/ws/logs`);
  logWs.onopen = () => {
    appendLogEntry({ ts: Date.now()/1000, level: 'INFO', logger: 'ui', msg: '--- Connected to log stream ---' });
  };
  logWs.onclose = () => {
    appendLogEntry({ ts: Date.now()/1000, level: 'WARNING', logger: 'ui', msg: '--- Log stream disconnected, reconnecting... ---' });
    setTimeout(connectLogWS, 3000);
  };
  logWs.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === 'logs' && msg.entries) {
        msg.entries.forEach(entry => appendLogEntry(entry));
      }
    } catch {}
  };
}

function appendLogEntry(entry) {
  logEntries.push(entry);
  if (logEntries.length > 5000) logEntries = logEntries.slice(-4000);
  document.getElementById('log-count').textContent = logEntries.length + ' entries';

  // Check filters
  if (!passesFilter(entry)) return;

  const container = document.getElementById('log-container');
  const div = document.createElement('div');
  div.className = `log-line log-${entry.level}`;
  const ts = new Date(entry.ts * 1000).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3 });
  const icon = LOG_ICONS[entry.level] || '  ';
  const levelPad = (entry.level + '    ').slice(0, 7);

  // Highlight key words
  let msg = escapeHtml(entry.msg);
  msg = msg.replace(/(LONG|BUY|Paper OPEN)/g, '<span style="color:#00ff88;font-weight:bold">$1</span>');
  msg = msg.replace(/(SHORT|SELL)/g, '<span style="color:#ff4444;font-weight:bold">$1</span>');
  msg = msg.replace(/(Paper CLOSE)/g, '<span style="color:#ff9800;font-weight:bold">$1</span>');
  msg = msg.replace(/(Signal:)/g, '<span style="color:#00bfff;font-weight:bold">$1</span>');
  msg = msg.replace(/(=== Cycle #\d+ ===)/g, '<span style="color:#b388ff;font-weight:bold">$1</span>');
  msg = msg.replace(/(Fetching OHLCV:)/g, '<span style="color:#80deea">$1</span>');
  msg = msg.replace(/(Fetched \d+ candles:)/g, '<span style="color:#80deea">$1</span>');
  msg = msg.replace(/(P&L=[+-]?\d+\.\d+%)/g, (match) => {
    const isPos = !match.includes('-');
    return `<span style="color:${isPos ? '#00ff88' : '#ff4444'};font-weight:bold">${match}</span>`;
  });

  div.innerHTML = `<span style="color:#555">${ts}</span> ${icon}<span style="color:#666">${levelPad}</span> ${msg}`;
  container.appendChild(div);

  // Limit DOM nodes
  while (container.children.length > 2000) {
    container.removeChild(container.firstChild);
  }

  if (logAutoScroll) {
    container.scrollTop = container.scrollHeight;
  }
}

function passesFilter(entry) {
  const levelFilter = document.getElementById('log-level-filter').value;
  const searchFilter = document.getElementById('log-search').value.toLowerCase();

  if (levelFilter !== 'all' && LOG_LEVELS[entry.level] < LOG_LEVELS[levelFilter]) return false;
  if (searchFilter && !entry.msg.toLowerCase().includes(searchFilter)) return false;
  return true;
}

function filterLogs() {
  // Re-render all logs with current filters
  const container = document.getElementById('log-container');
  container.innerHTML = '';
  logEntries.forEach(entry => {
    if (passesFilter(entry)) {
      // Re-use appendLogEntry but avoid double-push
      const div = document.createElement('div');
      div.className = `log-line log-${entry.level}`;
      const ts = new Date(entry.ts * 1000).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit', fractionalSecondDigits: 3 });
      const icon = LOG_ICONS[entry.level] || '  ';
      const levelPad = (entry.level + '    ').slice(0, 7);
      let msg = escapeHtml(entry.msg);
      msg = msg.replace(/(LONG|BUY|Paper OPEN)/g, '<span style="color:#00ff88;font-weight:bold">$1</span>');
      msg = msg.replace(/(SHORT|SELL)/g, '<span style="color:#ff4444;font-weight:bold">$1</span>');
      msg = msg.replace(/(Paper CLOSE)/g, '<span style="color:#ff9800;font-weight:bold">$1</span>');
      msg = msg.replace(/(Signal:)/g, '<span style="color:#00bfff;font-weight:bold">$1</span>');
      msg = msg.replace(/(=== Cycle #\d+ ===)/g, '<span style="color:#b388ff;font-weight:bold">$1</span>');
      msg = msg.replace(/(Fetching OHLCV:)/g, '<span style="color:#80deea">$1</span>');
      msg = msg.replace(/(Fetched \d+ candles:)/g, '<span style="color:#80deea">$1</span>');
      div.innerHTML = `<span style="color:#555">${ts}</span> ${icon}<span style="color:#666">${levelPad}</span> ${msg}`;
      container.appendChild(div);
    }
  });
  if (logAutoScroll) container.scrollTop = container.scrollHeight;
}

function toggleAutoScroll() {
  logAutoScroll = document.getElementById('log-auto').checked;
}

function clearLogs() {
  logEntries = [];
  document.getElementById('log-container').innerHTML = '<div class="text-gray-600 text-xs">Logs cleared</div>';
  document.getElementById('log-count').textContent = '0 entries';
}

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ─── Data Integrity ───
let _dataSummaryCache = null;

function fmtMs(ms) {
  if (!ms) return '—';
  return new Date(ms).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

function fmtDatetime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' +
    d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });
}

// ─── Exploration Tab ───
async function loadExploreTab() {
  const [stats, lb, symbols] = await Promise.all([
    api('/explore/stats'),
    api('/explore/leaderboard?limit=50'),
    api('/explore/symbols'),
  ]);

  // Status cards
  const statusEl = document.getElementById('explore-status');
  const detailEl = document.getElementById('explore-status-detail');
  if (stats.running) {
    statusEl.textContent = 'running';
    statusEl.className = 'text-2xl font-bold text-accent';
    const avail = stats.available_symbols || {};
    const totalSyms = Object.values(avail).reduce((a,b) => a+b, 0);
    detailEl.textContent = `${Object.keys(avail).length} exchanges · ${totalSyms} symbols`;
  } else {
    statusEl.textContent = stats.message ? 'stopped' : 'stopped';
    statusEl.className = 'text-2xl font-bold text-warn';
    detailEl.textContent = stats.message || 'Set AUTO_START_EXPLORER=true';
  }

  document.getElementById('explore-total-results').textContent = (stats.total_results || 0).toLocaleString();
  document.getElementById('explore-unique-symbols').textContent = stats.unique_symbols || 0;
  document.getElementById('explore-unique-strategies').textContent = stats.unique_strategies || 0;
  document.getElementById('explore-workers').textContent = stats.workers_online || 0;
  document.getElementById('explore-promoted').textContent = stats.total_promoted || 0;

  // Pipeline
  document.getElementById('explore-pending').textContent = stats.tasks_pending || 0;
  document.getElementById('explore-running').textContent = stats.tasks_running || 0;
  document.getElementById('explore-done').textContent = (stats.tasks_done || 0).toLocaleString();
  document.getElementById('explore-failed').textContent = stats.tasks_failed || 0;

  // Leaderboard
  renderExploreLeaderboard(lb);

  // Symbols
  if (symbols.symbols && Object.keys(symbols.symbols).length > 0) {
    let html = '';
    for (const [ex, syms] of Object.entries(symbols.symbols)) {
      html += `<div class="mb-2"><span class="text-accent font-bold">${ex}</span> <span class="text-gray-600">(${syms.length} symbols)</span><br/><span class="text-gray-500">${syms.slice(0, 30).join(', ')}${syms.length > 30 ? ` ... +${syms.length-30} more` : ''}</span></div>`;
    }
    document.getElementById('explore-symbols-list').innerHTML = html;
  }
}

async function loadExploreLeaderboard() {
  const sort = document.getElementById('explore-sort').value;
  const data = await api(`/explore/leaderboard?sort_by=${sort}&limit=50`);
  renderExploreLeaderboard(data);
}

function renderExploreLeaderboard(data) {
  const body = document.getElementById('explore-lb-body');
  const empty = document.getElementById('explore-lb-empty');
  if (!data.leaderboard || data.leaderboard.length === 0) {
    body.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');
  body.innerHTML = data.leaderboard.map((r, i) => {
    const pnlCls = r.pnl_pct >= 0 ? 'text-profit' : 'text-loss';
    const sharpeCls = r.sharpe >= 1 ? 'text-profit' : r.sharpe >= 0 ? 'text-gray-400' : 'text-loss';
    const paramStr = Object.entries(r.params || {}).map(([k,v]) => `${k}=${v}`).join(', ');
    const badge = r.promoted ? '<span class="bg-accent/20 text-accent px-1 rounded">PROMOTED</span>' : '<span class="text-gray-600">tested</span>';
    return `<tr class="border-b border-border/50 hover:bg-border/20">
      <td class="py-2 px-2 text-gray-500">${i+1}</td>
      <td class="py-2 px-2 font-bold">${r.strategy}</td>
      <td class="py-2 px-2 text-accent">${r.symbol}</td>
      <td class="py-2 px-2">${r.timeframe}</td>
      <td class="py-2 px-2 text-right ${sharpeCls} font-mono">${r.sharpe.toFixed(2)}</td>
      <td class="py-2 px-2 text-right ${pnlCls} font-mono">${r.pnl_pct >= 0 ? '+' : ''}${r.pnl_pct.toFixed(1)}%</td>
      <td class="py-2 px-2 text-right">${r.win_rate.toFixed(0)}%</td>
      <td class="py-2 px-2 text-right">${r.profit_factor.toFixed(2)}</td>
      <td class="py-2 px-2 text-right">${r.trades}</td>
      <td class="py-2 px-2 text-right text-warn">${r.max_dd.toFixed(1)}%</td>
      <td class="py-2 px-2 text-gray-500 max-w-[200px] truncate" title="${paramStr}">${paramStr || '—'}</td>
      <td class="py-2 px-2 text-center">${badge}</td>
    </tr>`;
  }).join('');
}

async function explorerAction(action, btn) {
  // Show loading state on the clicked button
  const allBtns = document.querySelectorAll('[onclick^="explorerAction"]');
  allBtns.forEach(b => b.disabled = true);
  const statusEl = document.getElementById('explore-status');
  const detailEl = document.getElementById('explore-status-detail');
  const origStatus = statusEl.textContent;
  const origDetail = detailEl.textContent;

  const opts = { method: 'POST' };
  let result;

  if (action === 'start') {
    statusEl.textContent = 'starting...';
    statusEl.className = 'text-2xl font-bold text-warn pulse';
    detailEl.textContent = 'Connecting to exchanges & discovering symbols...';
    result = await api('/explore/start', opts);
  } else if (action === 'stop') {
    statusEl.textContent = 'stopping...';
    result = await api('/explore/stop', opts);
  } else if (action === 'generate') {
    detailEl.textContent = 'Generating tasks... (discovering symbols if needed)';
    statusEl.className = 'text-2xl font-bold text-warn pulse';
    result = await api('/explore/generate?count=50', opts);
  } else if (action === 'refresh-symbols') {
    detailEl.textContent = 'Connecting to exchanges...';
    statusEl.className = 'text-2xl font-bold text-warn pulse';
    result = await api('/explore/refresh-symbols', opts);
  }

  // Show result message
  if (result && result.message) {
    detailEl.textContent = result.message;
  } else if (result && result.error) {
    detailEl.textContent = 'Error: ' + (result.detail || result.error);
    statusEl.className = 'text-2xl font-bold text-danger';
  }

  allBtns.forEach(b => b.disabled = false);

  // Refresh the tab data after a short delay
  setTimeout(() => loadExploreTab(), 1500);
}


async function loadDataSummary() {
  const [res, collectorRes] = await Promise.all([
    api('/data/candles/summary'),
    api('/data/collector/status'),
  ]);

  // Collector status card
  const cEl = document.getElementById('data-collector-status');
  const cDetail = document.getElementById('data-collector-detail');
  const collectorPairs = (collectorRes && collectorRes.pairs) || {};
  if (collectorRes && collectorRes.running) {
    cEl.textContent = 'running';
    cEl.className = 'text-2xl font-bold text-accent';
    const pairCount = Object.keys(collectorPairs).length;
    cDetail.textContent = `${pairCount} pairs · smart intervals`;
  } else {
    cEl.textContent = 'stopped';
    cEl.className = 'text-2xl font-bold text-warn';
    cDetail.textContent = collectorRes.message || 'waiting...';
  }

  if (res.error) {
    document.getElementById('data-db-status').textContent = 'offline';
    document.getElementById('data-db-status').className = 'text-2xl font-bold text-danger';
    document.getElementById('data-series-empty').classList.remove('hidden');
    document.getElementById('data-series-table').innerHTML = '';
    return;
  }

  _dataSummaryCache = res;

  document.getElementById('data-total-candles').textContent = (res.total_candles || 0).toLocaleString();
  document.getElementById('data-total-symbols').textContent = (res.symbols || []).length;
  document.getElementById('data-total-tf').textContent = (res.timeframes || []).length;
  document.getElementById('data-db-status').textContent = 'online';
  document.getElementById('data-db-status').className = 'text-2xl font-bold text-accent';

  // Populate filter dropdowns
  const symSelect = document.getElementById('gap-symbol');
  const tfSelect = document.getElementById('gap-tf');
  const curSym = symSelect.value;
  const curTf = tfSelect.value;
  symSelect.innerHTML = '<option value="">All symbols</option>';
  tfSelect.innerHTML = '<option value="">All timeframes</option>';
  (res.symbols || []).forEach(s => {
    symSelect.innerHTML += `<option value="${s}" ${s===curSym?'selected':''}>${s}</option>`;
  });
  (res.timeframes || []).forEach(t => {
    tfSelect.innerHTML += `<option value="${t}" ${t===curTf?'selected':''}>${t}</option>`;
  });

  // Render table
  const tbody = document.getElementById('data-series-table');
  if (!res.series || res.series.length === 0) {
    tbody.innerHTML = '';
    document.getElementById('data-series-empty').classList.remove('hidden');
    return;
  }
  document.getElementById('data-series-empty').classList.add('hidden');

  // Build lookup for collector intervals
  const TF_INTERVALS = {'1m':15,'3m':45,'5m':60,'15m':300,'30m':600,'1h':900,'2h':1800,'4h':3600,'6h':3600,'8h':3600,'12h':3600,'1d':3600,'3d':7200,'1w':14400};

  function relTime(isoStr, warnAfterSec) {
    if (!isoStr) return ['—', 'text-gray-600'];
    const ago = (Date.now() - new Date(isoStr).getTime()) / 1000;
    let label, cls;
    if (ago < 60) { label = Math.round(ago) + 's ago'; cls = 'text-accent'; }
    else if (ago < 3600) { label = Math.round(ago/60) + 'm ago'; cls = 'text-accent'; }
    else if (ago < 86400) { label = Math.round(ago/3600) + 'h ago'; cls = 'text-gray-400'; }
    else { label = Math.round(ago/86400) + 'd ago'; cls = 'text-gray-500'; }
    // Warn if stale beyond expected
    if (warnAfterSec && ago > warnAfterSec) cls = ago > warnAfterSec * 5 ? 'text-danger' : 'text-warn';
    return [label, cls];
  }

  tbody.innerHTML = res.series.map(s => {
    const days = s.first_timestamp_ms && s.last_timestamp_ms
      ? ((s.last_timestamp_ms - s.first_timestamp_ms) / 86400000).toFixed(1)
      : '—';
    const intSec = TF_INTERVALS[s.timeframe] || 60;
    const intLabel = intSec >= 3600 ? (intSec/3600)+'h' : intSec >= 60 ? (intSec/60)+'m' : intSec+'s';
    // Last Checked = when collector last fetched (from collector stats, always fresh)
    const [checkedStr, checkedCls] = relTime(s.last_checked, intSec * 3);
    // Data Changed = when actual OHLCV data last changed in DB
    const [changedStr, changedCls] = relTime(s.last_collected, null);
    return `<tr class="border-b border-border/50 hover:bg-border/20">
      <td class="py-2 px-2 font-bold text-accent">${s.symbol}</td>
      <td class="py-2 px-2">${s.timeframe}</td>
      <td class="py-2 px-2 text-right font-mono">${s.candle_count.toLocaleString()}</td>
      <td class="py-2 px-2 text-gray-400">${fmtMs(s.first_timestamp_ms)}</td>
      <td class="py-2 px-2 text-gray-400">${fmtMs(s.last_timestamp_ms)}</td>
      <td class="py-2 px-2 text-gray-400">${days}</td>
      <td class="py-2 px-2 ${checkedCls}" title="${s.last_checked || ''}">${checkedStr}</td>
      <td class="py-2 px-2 ${changedCls}" title="${fmtDatetime(s.last_collected)}">${changedStr}</td>
      <td class="py-2 px-2 text-gray-600">${intLabel}</td>
    </tr>`;
  }).join('');
}

async function runGapCheck() {
  const sym = document.getElementById('gap-symbol').value;
  const tf = document.getElementById('gap-tf').value;
  const btn = document.getElementById('gap-check-btn');
  const container = document.getElementById('gap-results');
  const empty = document.getElementById('gap-empty');

  btn.textContent = 'Checking...';
  btn.disabled = true;

  const params = new URLSearchParams();
  if (sym) params.set('symbol', sym);
  if (tf) params.set('timeframe', tf);

  const res = await api('/data/candles/check-gaps?' + params);
  btn.textContent = 'Run Check';
  btn.disabled = false;

  if (res.error) {
    container.innerHTML = `<div class="text-danger text-xs">${res.error}</div>`;
    empty.classList.add('hidden');
    return;
  }

  if (!res.results || res.results.length === 0) {
    container.innerHTML = '';
    empty.textContent = 'No data found for selected filters';
    empty.classList.remove('hidden');
    return;
  }

  empty.classList.add('hidden');

  container.innerHTML = res.results.map(r => {
    if (r.error) {
      return `<div class="border border-warn/30 rounded p-3">
        <span class="text-warn font-bold">${r.symbol} ${r.timeframe}</span>: ${r.error}
      </div>`;
    }

    const statusColors = {
      ok: 'text-accent', has_gaps: 'text-warn', has_duplicates: 'text-warn',
      gaps_and_duplicates: 'text-danger', insufficient_data: 'text-gray-500'
    };
    const statusLabels = {
      ok: 'OK — No gaps', has_gaps: 'Gaps found', has_duplicates: 'Duplicates found',
      gaps_and_duplicates: 'Gaps + Duplicates', insufficient_data: 'Not enough data'
    };
    const cls = statusColors[r.status] || 'text-gray-400';
    const label = statusLabels[r.status] || r.status;
    const pct = r.expected_candles ? ((r.total_candles / r.expected_candles) * 100).toFixed(1) : '—';

    let gapHtml = '';
    if (r.gaps && r.gaps.length > 0) {
      const gapRows = r.gaps.slice(0, 20).map(g => {
        return `<tr class="border-b border-border/30">
          <td class="py-1 px-2">${fmtMs(g.after_ms)}</td>
          <td class="py-1 px-2">${fmtMs(g.before_ms)}</td>
          <td class="py-1 px-2 text-right text-warn font-mono">${g.missing_candles}</td>
          <td class="py-1 px-2 text-right text-gray-500">${g.gap_duration_min}m</td>
        </tr>`;
      }).join('');
      const moreText = r.total_gaps > 20 ? `<div class="text-gray-600 text-xs mt-1">... and ${r.total_gaps - 20} more gaps</div>` : '';
      gapHtml = `<details class="mt-2">
        <summary class="text-xs text-gray-500 cursor-pointer hover:text-gray-300">Show ${r.total_gaps} gap(s)</summary>
        <table class="w-full text-xs mt-2">
          <thead><tr class="text-gray-600 border-b border-border">
            <th class="text-left py-1 px-2">After</th>
            <th class="text-left py-1 px-2">Before</th>
            <th class="text-right py-1 px-2">Missing</th>
            <th class="text-right py-1 px-2">Duration</th>
          </tr></thead>
          <tbody>${gapRows}</tbody>
        </table>
        ${moreText}
      </details>`;
    }

    let dupeHtml = '';
    if (r.duplicate_timestamps > 0) {
      dupeHtml = `<span class="ml-3 text-warn text-xs">${r.duplicate_timestamps} duplicate timestamp(s)</span>`;
    }

    return `<div class="border ${r.status === 'ok' ? 'border-accent/20' : 'border-warn/30'} rounded-lg p-3">
      <div class="flex items-center justify-between">
        <div>
          <span class="font-bold text-accent">${r.symbol}</span>
          <span class="text-gray-500 ml-1">${r.timeframe}</span>
          <span class="ml-3 ${cls} text-xs font-bold">${label}</span>
          ${dupeHtml}
        </div>
        <div class="text-xs text-gray-500">
          ${(r.total_candles || 0).toLocaleString()} / ${(r.expected_candles || 0).toLocaleString()} candles
          <span class="ml-1 font-mono ${parseFloat(pct) >= 99 ? 'text-accent' : parseFloat(pct) >= 95 ? 'text-warn' : 'text-danger'}">(${pct}%)</span>
        </div>
      </div>
      <div class="text-xs text-gray-500 mt-1">
        ${fmtMs(r.first_ms)} — ${fmtMs(r.last_ms)}
        ${r.missing_count > 0 ? ` · <span class="text-warn">${r.missing_count} missing candles</span>` : ''}
      </div>
      ${gapHtml}
    </div>`;
  }).join('');
}

// ─── Symbol Picker ───
// Reusable multi-select symbol picker with exchange selector, quote currency
// filter tabs, and text fallback input.

const _symbolPickers = {};

const EXCHANGES = ['binance','bybit','okx','kucoin','gate'];

const TOP_BASES = [
  'BTC','ETH','BNB','SOL','XRP','DOGE','ADA','AVAX','DOT','LINK',
  'MATIC','UNI','SHIB','LTC','ATOM','FIL','APT','ARB','OP','NEAR',
];

function createSymbolPicker(containerId, defaultSymbols = 'BTC/USDT,ETH/USDT') {
  const container = document.getElementById(containerId);
  if (!container) return;
  const id = containerId;
  _symbolPickers[id] = {
    selected: new Set(defaultSymbols.split(',').map(s => s.trim()).filter(Boolean)),
    byQuote: {},          // { USDT: [...], BTC: [...], ... }
    quotes: [],           // ['USDT','BTC','ETH',...]
    activeQuote: 'USDT',  // current filter tab
    exchange: '',         // loaded exchange name
    filter: '',
    total: 0,
  };

  const exOpts = EXCHANGES.map(e => `<option value="${e}">${e[0].toUpperCase()+e.slice(1)}</option>`).join('');

  container.innerHTML = `
    <input type="text" id="${id}-text" value="${defaultSymbols}"
      class="w-full bg-bg border border-border rounded px-2 py-1.5 text-sm mb-2"
      placeholder="BTC/USDT, ETH/USDT, SOL/BTC, ..."
      oninput="_onSymTextInput('${id}')">
    <div class="sym-picker-actions mb-1">
      <select id="${id}-exchange" class="sym-search" style="width:auto">
        ${exOpts}
      </select>
      <button class="sym-picker-btn" onclick="_loadExchangeSymbols('${id}')">Load</button>
      <span class="text-gray-700">|</span>
      <button class="sym-picker-btn" onclick="_symSelectAll('${id}')">Select visible</button>
      <button class="sym-picker-btn" onclick="_symSelectNone('${id}')">Clear</button>
      <button class="sym-picker-btn" onclick="_symSelectTop('${id}')">Top 20</button>
      <input type="text" class="sym-search" id="${id}-search" placeholder="Search..."
        oninput="_symFilter('${id}')">
      <span class="text-xs text-gray-500" id="${id}-count">${_symbolPickers[id].selected.size} selected</span>
    </div>
    <div id="${id}-quote-tabs" class="flex gap-1 mb-1 flex-wrap"></div>
    <div class="sym-grid" id="${id}-grid"></div>
  `;

  _renderQuoteTabs(id);
  _renderSymChips(id);
}

function _renderQuoteTabs(pickerId) {
  const state = _symbolPickers[pickerId];
  const tabsEl = document.getElementById(pickerId + '-quote-tabs');
  if (!tabsEl) return;
  const quotes = state.quotes;
  if (quotes.length === 0) { tabsEl.innerHTML = ''; return; }

  tabsEl.innerHTML = quotes.map(q => {
    const count = (state.byQuote[q] || []).length;
    const active = q === state.activeQuote;
    const cls = active
      ? 'sym-picker-btn' + ' !border-accent !text-accent'
      : 'sym-picker-btn';
    return `<button class="${cls}" onclick="_symSetQuote('${pickerId}','${q}')">${q} <span class="text-gray-600">(${count})</span></button>`;
  }).join('');
}

function _symSetQuote(pickerId, quote) {
  _symbolPickers[pickerId].activeQuote = quote;
  _renderQuoteTabs(pickerId);
  _renderSymChips(pickerId);
}

function _renderSymChips(pickerId) {
  const state = _symbolPickers[pickerId];
  const grid = document.getElementById(pickerId + '-grid');
  if (!grid) return;

  // Source symbols: from active quote tab, or all selected if nothing loaded
  let pool = [];
  if (state.quotes.length > 0) {
    pool = state.byQuote[state.activeQuote] || [];
  }
  // Always include currently selected symbols that match active quote
  const merged = new Set([...pool, ...[...state.selected].filter(s => {
    if (state.quotes.length === 0) return true;
    const q = s.includes('/') ? s.split('/')[1] : '';
    return q === state.activeQuote || state.quotes.length === 0;
  })]);
  let syms = [...merged].sort();

  // Apply text filter
  const filter = (state.filter || '').toUpperCase();
  if (filter) {
    syms = syms.filter(s => s.toUpperCase().includes(filter));
  }

  if (syms.length === 0 && !filter && state.quotes.length === 0) {
    const selected = [...state.selected].sort();
    if (selected.length === 0) {
      grid.innerHTML = '<div class="text-gray-600 text-xs py-2">Type symbols above or select exchange and click "Load"</div>';
      return;
    }
    syms = selected;
  }

  if (syms.length === 0) {
    grid.innerHTML = '<div class="text-gray-600 text-xs py-2">No matches</div>';
    return;
  }

  grid.innerHTML = syms.map(s => {
    const sel = state.selected.has(s) ? 'selected' : '';
    // Show short label: base currency for standard pairs
    const parts = s.split('/');
    const label = parts.length === 2 ? parts[0] : s;
    return `<span class="sym-chip ${sel}" onclick="_symToggle('${pickerId}','${s}')" title="${s}">${label}</span>`;
  }).join('');
}

function _symToggle(pickerId, sym) {
  const state = _symbolPickers[pickerId];
  if (state.selected.has(sym)) state.selected.delete(sym);
  else state.selected.add(sym);
  _syncSymPicker(pickerId);
}

function _syncSymPicker(pickerId) {
  const state = _symbolPickers[pickerId];
  const textInput = document.getElementById(pickerId + '-text');
  const countEl = document.getElementById(pickerId + '-count');
  if (textInput) textInput.value = [...state.selected].join(', ');
  if (countEl) {
    const visibleQuote = state.activeQuote;
    const visibleCount = (state.byQuote[visibleQuote] || []).length;
    const selInQuote = [...state.selected].filter(s => {
      if (!s.includes('/')) return false;
      return s.split('/')[1] === visibleQuote;
    }).length;
    countEl.textContent = state.total > 0
      ? `${state.selected.size} selected (${selInQuote} ${visibleQuote}) / ${state.total} total`
      : `${state.selected.size} selected`;
  }
  _renderSymChips(pickerId);
}

function _onSymTextInput(pickerId) {
  const state = _symbolPickers[pickerId];
  const raw = document.getElementById(pickerId + '-text').value;
  const syms = raw.split(/[,;\s]+/).map(s => s.trim().toUpperCase()).filter(Boolean);
  const normalized = syms.map(s => s.includes('/') ? s : s + '/USDT');
  state.selected = new Set(normalized);
  _syncSymPicker(pickerId);
}

async function _loadExchangeSymbols(pickerId) {
  const state = _symbolPickers[pickerId];
  const grid = document.getElementById(pickerId + '-grid');
  const countEl = document.getElementById(pickerId + '-count');
  const exSelect = document.getElementById(pickerId + '-exchange');
  const exchange = exSelect ? exSelect.value : '';
  grid.innerHTML = '<div class="text-warn text-xs py-2 pulse">Connecting to ' + (exchange || 'exchange') + '...</div>';

  const data = await api(`/exchange/symbols?exchange=${encodeURIComponent(exchange)}`);

  if (data.by_quote && Object.keys(data.by_quote).length > 0) {
    state.byQuote = data.by_quote;
    state.quotes = data.quotes || Object.keys(data.by_quote);
    state.exchange = data.exchange || exchange;
    state.total = data.total || 0;
    // Default to USDT tab if available, else first
    state.activeQuote = state.quotes.includes('USDT') ? 'USDT' : state.quotes[0];
  } else {
    // Fallback
    const fallback = TOP_BASES.map(b => b + '/USDT');
    state.byQuote = { 'USDT': fallback };
    state.quotes = ['USDT'];
    state.total = fallback.length;
    state.activeQuote = 'USDT';
  }

  if (countEl) countEl.textContent = `${state.selected.size} selected / ${state.total} total on ${state.exchange}`;
  _renderQuoteTabs(pickerId);
  _renderSymChips(pickerId);
}

function _symSelectAll(pickerId) {
  const state = _symbolPickers[pickerId];
  // Select all visible (current quote tab + filter)
  const pool = state.byQuote[state.activeQuote] || [];
  const filter = (state.filter || '').toUpperCase();
  const filtered = filter ? pool.filter(s => s.toUpperCase().includes(filter)) : pool;
  filtered.forEach(s => state.selected.add(s));
  _syncSymPicker(pickerId);
}

function _symSelectNone(pickerId) {
  _symbolPickers[pickerId].selected.clear();
  _syncSymPicker(pickerId);
}

function _symSelectTop(pickerId) {
  const state = _symbolPickers[pickerId];
  // Pick top 20 by market cap from current quote tab
  const pool = state.byQuote[state.activeQuote] || [];
  const top = pool.length > 0
    ? TOP_BASES.map(b => b + '/' + state.activeQuote).filter(s => pool.includes(s)).slice(0, 20)
    : TOP_BASES.map(b => b + '/USDT');
  // If fewer than 20 found, fill from pool
  if (top.length < 20) {
    for (const s of pool) {
      if (top.length >= 20) break;
      if (!top.includes(s)) top.push(s);
    }
  }
  state.selected = new Set(top);
  _syncSymPicker(pickerId);
}

function _symFilter(pickerId) {
  _symbolPickers[pickerId].filter = document.getElementById(pickerId + '-search').value;
  _renderSymChips(pickerId);
}

function getPickerSymbols(pickerId) {
  const state = _symbolPickers[pickerId];
  if (!state) {
    const el = document.getElementById(pickerId + '-text');
    return el ? el.value : 'BTC/USDT,ETH/USDT';
  }
  return [...state.selected].join(',');
}

function getPickerSymbolsArray(pickerId) {
  return getPickerSymbols(pickerId).split(',').map(s => s.trim()).filter(Boolean);
}

// ─── Signal / Position Detail Modal ───

function closeDetailModal() {
  document.getElementById('detail-modal').classList.add('hidden');
}

// Close on Escape
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDetailModal(); });

async function showSignalDetail(signalId) {
  const data = await api(`/paper/signal/${signalId}`);
  if (data.error) return;
  renderDetailModal(data, 'signal');
}

async function showPositionDetail(positionId) {
  const data = await api(`/paper/position/${positionId}`);
  if (data.error) return;
  renderDetailModal(data, 'position');
}

function renderDetailModal(data, type) {
  const modal = document.getElementById('detail-modal');
  const content = document.getElementById('detail-modal-content');
  const meta = data.metadata || {};
  const dirColor = data.direction === 'long' ? 'text-profit' : 'text-loss';
  const dirBg = data.direction === 'long' ? 'bg-profit/10' : 'bg-loss/10';

  // Header
  let html = `
    <div class="flex items-center gap-3 mb-4">
      <span class="${dirBg} ${dirColor} font-bold uppercase px-3 py-1 rounded text-sm">${data.direction}</span>
      <span class="text-accent text-lg font-bold">${data.symbol}</span>
      <span class="text-gray-500 text-sm">@ ${(data.price || data.entry_price || 0).toFixed(2)}</span>
    </div>
  `;

  // Strategy info
  const stratName = data.strategy_name || data.strategy_id || '?';
  const ts = data.timestamp ? new Date(data.timestamp * 1000).toLocaleString() : (data.opened_at || '');
  html += `
    <div class="grid grid-cols-2 gap-3 mb-4 text-xs">
      <div class="bg-bg rounded p-3">
        <div class="text-gray-500 mb-1">Strategy</div>
        <div class="font-semibold">${stratName}</div>
        <div class="text-gray-600 mt-1">${data.strategy_id || ''}</div>
      </div>
      <div class="bg-bg rounded p-3">
        <div class="text-gray-500 mb-1">Time</div>
        <div class="font-semibold">${ts}</div>
        <div class="text-gray-600 mt-1">Strength: <span class="text-accent">${(data.strength || 0).toFixed(3)}</span></div>
      </div>
    </div>
  `;

  // Price levels
  html += `<div class="grid grid-cols-3 gap-3 mb-4 text-xs">`;
  if (data.entry_price != null) {
    html += `<div class="bg-bg rounded p-3 text-center"><div class="text-gray-500">Entry</div><div class="font-bold text-sm">${data.entry_price.toFixed(2)}</div></div>`;
  }
  if (data.stop_loss != null) {
    html += `<div class="bg-bg rounded p-3 text-center"><div class="text-gray-500">Stop Loss</div><div class="font-bold text-sm text-loss">${data.stop_loss.toFixed(2)}</div></div>`;
  }
  if (data.take_profit != null) {
    html += `<div class="bg-bg rounded p-3 text-center"><div class="text-gray-500">Take Profit</div><div class="font-bold text-sm text-profit">${data.take_profit.toFixed(2)}</div></div>`;
  }
  html += `</div>`;

  // Position-specific P&L
  if (type === 'position') {
    const hasClosed = data.exit_price != null;
    const pnl = hasClosed ? data.realized_pnl_pct : data.unrealized_pnl_pct;
    const pnlColor = (pnl || 0) >= 0 ? 'text-profit' : 'text-loss';
    const pnlLabel = hasClosed ? 'Realized P&L' : 'Unrealized P&L';
    html += `<div class="grid grid-cols-3 gap-3 mb-4 text-xs">`;
    if (hasClosed) {
      html += `<div class="bg-bg rounded p-3 text-center"><div class="text-gray-500">Exit</div><div class="font-bold text-sm">${data.exit_price.toFixed(2)}</div></div>`;
      html += `<div class="bg-bg rounded p-3 text-center"><div class="text-gray-500">${pnlLabel}</div><div class="font-bold text-sm ${pnlColor}">${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}%</div></div>`;
      html += `<div class="bg-bg rounded p-3 text-center"><div class="text-gray-500">Close Reason</div><div class="font-bold text-sm uppercase ${data.close_reason === 'tp' ? 'text-profit' : data.close_reason === 'sl' ? 'text-loss' : 'text-warn'}">${data.close_reason}</div></div>`;
    } else {
      html += `<div class="bg-bg rounded p-3 text-center"><div class="text-gray-500">Current</div><div class="font-bold text-sm">${(data.current_price || 0).toFixed(2)}</div></div>`;
      html += `<div class="bg-bg rounded p-3 text-center"><div class="text-gray-500">${pnlLabel}</div><div class="font-bold text-sm ${pnlColor}">${(pnl||0) >= 0 ? '+' : ''}${(pnl||0).toFixed(2)}%</div></div>`;
      html += `<div class="bg-bg rounded p-3 text-center"><div class="text-gray-500">Status</div><div class="font-bold text-sm text-accent">OPEN</div></div>`;
    }
    html += `</div>`;
  }

  // Reason / argumentation
  if (meta.reason) {
    html += `
      <div class="mb-4">
        <div class="text-xs text-gray-500 mb-2 font-semibold uppercase">Signal Reasoning</div>
        <div class="bg-bg rounded p-4 text-sm leading-relaxed text-gray-200 border-l-2 ${data.direction === 'long' ? 'border-profit' : 'border-loss'}">${meta.reason}</div>
      </div>
    `;
  }

  // Indicator values
  const indicatorKeys = Object.keys(meta).filter(k => !['reason', 'candles'].includes(k));
  if (indicatorKeys.length > 0) {
    html += `<div class="mb-4"><div class="text-xs text-gray-500 mb-2 font-semibold uppercase">Indicator Values</div><div class="bg-bg rounded p-3">`;
    indicatorKeys.forEach(k => {
      let val = meta[k];
      let cls = 'text-gray-200';
      // Color-code RSI
      if (k === 'rsi') {
        cls = val < 30 ? 'text-profit' : val > 70 ? 'text-loss' : val < 45 ? 'text-green-300' : val > 55 ? 'text-red-300' : 'text-gray-200';
      }
      if (typeof val === 'number') val = val % 1 === 0 ? val : val.toFixed(4);
      html += `<div class="indicator-row text-xs"><span class="indicator-label">${k}</span><span class="indicator-value ${cls}">${val}</span></div>`;
    });
    html += `</div></div>`;
  }

  // Candle table
  if (meta.candles && meta.candles.length > 0) {
    html += `<div class="mb-4"><div class="text-xs text-gray-500 mb-2 font-semibold uppercase">Recent Candles (${meta.candles.length})</div>`;

    // ASCII mini-chart
    html += renderMiniCandleChart(meta.candles, data);

    // Table
    html += `<div class="overflow-x-auto mt-2"><table class="w-full text-xs"><thead><tr class="text-gray-500 border-b border-border">
      <th class="text-left py-1 px-2">Time</th>
      <th class="text-right py-1 px-2">Open</th>
      <th class="text-right py-1 px-2">High</th>
      <th class="text-right py-1 px-2">Low</th>
      <th class="text-right py-1 px-2">Close</th>
      <th class="text-right py-1 px-2">Vol</th>
      <th class="text-right py-1 px-2">Chg %</th>
    </tr></thead><tbody>`;
    meta.candles.forEach(c => {
      const change = c.o > 0 ? ((c.c - c.o) / c.o * 100) : 0;
      const chgColor = change >= 0 ? 'candle-green' : 'candle-red';
      const barChar = change >= 0 ? '+' : '-';
      const tStr = c.t ? c.t.replace(/T/, ' ').slice(0, 19) : '';
      html += `<tr class="border-b border-border/20">
        <td class="py-1 px-2 text-gray-500">${tStr}</td>
        <td class="py-1 px-2 text-right">${c.o}</td>
        <td class="py-1 px-2 text-right text-profit">${c.h}</td>
        <td class="py-1 px-2 text-right text-loss">${c.l}</td>
        <td class="py-1 px-2 text-right font-bold ${chgColor}">${c.c}</td>
        <td class="py-1 px-2 text-right text-gray-500">${c.v ? c.v.toLocaleString() : '—'}</td>
        <td class="py-1 px-2 text-right ${chgColor}">${change >= 0 ? '+' : ''}${change.toFixed(2)}%</td>
      </tr>`;
    });
    html += `</tbody></table></div></div>`;
  }

  content.innerHTML = html;
  modal.classList.remove('hidden');
}

function renderMiniCandleChart(candles, signalData) {
  // SVG candle chart
  const w = 660, h = 120, pad = 20;
  const prices = candles.flatMap(c => [c.h, c.l]);
  const minP = Math.min(...prices);
  const maxP = Math.max(...prices);
  const range = maxP - minP || 1;
  const candleW = Math.min(40, Math.floor((w - pad * 2) / candles.length) - 4);
  const gap = Math.floor((w - pad * 2) / candles.length);

  const yScale = (p) => pad + (h - 2 * pad) * (1 - (p - minP) / range);

  let svg = `<svg width="${w}" height="${h + 24}" class="w-full" viewBox="0 0 ${w} ${h + 24}" preserveAspectRatio="xMidYMid meet">`;
  // Grid lines
  for (let i = 0; i <= 4; i++) {
    const p = minP + range * i / 4;
    const y = yScale(p);
    svg += `<line x1="${pad}" y1="${y}" x2="${w - pad}" y2="${y}" stroke="#1e1e2e" stroke-width="1"/>`;
    svg += `<text x="${w - pad + 4}" y="${y + 3}" fill="#555" font-size="9">${p.toFixed(1)}</text>`;
  }
  // Candles
  candles.forEach((c, i) => {
    const x = pad + i * gap + gap / 2;
    const isGreen = c.c >= c.o;
    const color = isGreen ? '#00ff88' : '#ff4444';
    const bodyTop = yScale(Math.max(c.o, c.c));
    const bodyBot = yScale(Math.min(c.o, c.c));
    const bodyH = Math.max(1, bodyBot - bodyTop);
    // Wick
    svg += `<line x1="${x}" y1="${yScale(c.h)}" x2="${x}" y2="${yScale(c.l)}" stroke="${color}" stroke-width="1"/>`;
    // Body
    svg += `<rect x="${x - candleW/2}" y="${bodyTop}" width="${candleW}" height="${bodyH}" fill="${isGreen ? color : color}" rx="1" opacity="${isGreen ? '0.8' : '0.8'}"/>`;
  });

  // Mark SL/TP/entry lines
  const entryP = signalData.price || signalData.entry_price;
  if (entryP && entryP >= minP && entryP <= maxP) {
    const y = yScale(entryP);
    svg += `<line x1="${pad}" y1="${y}" x2="${w - pad}" y2="${y}" stroke="#00bfff" stroke-width="1" stroke-dasharray="4,3"/>`;
    svg += `<text x="${pad}" y="${y - 4}" fill="#00bfff" font-size="9">Entry ${entryP.toFixed(1)}</text>`;
  }
  if (signalData.stop_loss && signalData.stop_loss >= minP && signalData.stop_loss <= maxP) {
    const y = yScale(signalData.stop_loss);
    svg += `<line x1="${pad}" y1="${y}" x2="${w - pad}" y2="${y}" stroke="#ff4444" stroke-width="1" stroke-dasharray="4,3"/>`;
    svg += `<text x="${pad}" y="${y - 4}" fill="#ff4444" font-size="9">SL ${signalData.stop_loss.toFixed(1)}</text>`;
  }
  if (signalData.take_profit && signalData.take_profit >= minP && signalData.take_profit <= maxP) {
    const y = yScale(signalData.take_profit);
    svg += `<line x1="${pad}" y1="${y}" x2="${w - pad}" y2="${y}" stroke="#00ff88" stroke-width="1" stroke-dasharray="4,3"/>`;
    svg += `<text x="${pad}" y="${y - 4}" fill="#00ff88" font-size="9">TP ${signalData.take_profit.toFixed(1)}</text>`;
  }

  svg += '</svg>';
  return `<div class="bg-bg rounded p-2 overflow-hidden">${svg}</div>`;
}

// ─── Clock ───
function updateClock() {
  document.getElementById('clock').textContent = new Date().toLocaleTimeString();
}

// ─── Init ───
connectWS();
connectLogWS();
refreshDashboard();
refreshHealth();
setInterval(refreshDashboard, 5000);
setInterval(refreshHealth, 10000);
setInterval(updateClock, 1000);
updateClock();

// Initialize symbol pickers
createSymbolPicker('engine-symbols-picker', 'BTC/USDT,ETH/USDT');
createSymbolPicker('gen-symbols-picker', 'BTC/USDT,ETH/USDT');

// Load initial logs
(async () => {
  const data = await api('/logs?limit=500');
  if (data.logs) data.logs.forEach(entry => appendLogEntry(entry));
})();
</script>
</body>
</html>"""
