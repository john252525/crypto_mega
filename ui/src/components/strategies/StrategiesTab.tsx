'use client';

import { useEffect, useState, useCallback } from 'react';
import { api, post } from '@/lib/api';
import type { StrategyInfo, StrategyTemplate } from '@/lib/types';

// ---------------------------------------------------------------------------
// Sub-tab type
// ---------------------------------------------------------------------------

type SubTab = 'loaded' | 'generator' | 'howto';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function statusBadge(status: string) {
  const map: Record<string, string> = {
    running: 'bg-[#00ff88]/10 text-[#00ff88]',
    idle: 'bg-gray-700/40 text-gray-400',
    paused: 'bg-[#ff9800]/10 text-[#ff9800]',
    stopped: 'bg-gray-700/40 text-gray-500',
    error: 'bg-[#ff4444]/10 text-[#ff4444]',
    pending: 'bg-[#00bfff]/10 text-[#00bfff]',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium uppercase ${map[status] ?? 'bg-gray-700 text-gray-300'}`}>
      {status}
    </span>
  );
}

const CATEGORY_COLORS: Record<string, string> = {
  trend: 'bg-[#00bfff]/10 text-[#00bfff]',
  reversion: 'bg-[#a855f7]/10 text-[#a855f7]',
  momentum: 'bg-[#00ff88]/10 text-[#00ff88]',
  breakout: 'bg-[#ff9800]/10 text-[#ff9800]',
  volatility: 'bg-[#ff4444]/10 text-[#ff4444]',
  ml: 'bg-[#ec4899]/10 text-[#ec4899]',
};

function categoryBadge(cat: string) {
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${CATEGORY_COLORS[cat] ?? 'bg-gray-700 text-gray-300'}`}>
      {cat}
    </span>
  );
}

function riskBadge(level: string) {
  const map: Record<string, string> = {
    low: 'bg-[#00ff88]/10 text-[#00ff88]',
    medium: 'bg-[#ff9800]/10 text-[#ff9800]',
    high: 'bg-[#ff4444]/10 text-[#ff4444]',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${map[level] ?? 'bg-gray-700 text-gray-300'}`}>
      {level} risk
    </span>
  );
}

// ---------------------------------------------------------------------------
// StatCard
// ---------------------------------------------------------------------------

function StatCard({ label, value, accent }: { label: string; value: string | number; accent?: string }) {
  return (
    <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-4">
      <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-xl font-bold ${accent ?? 'text-white'}`}>{value}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Strategy Card (Loaded Strategies sub-tab)
// ---------------------------------------------------------------------------

function StrategyCard({ s }: { s: StrategyInfo }) {
  const [expanded, setExpanded] = useState(false);

  const params = s.parameters ?? {};
  const category = (params.category as string) ?? 'unknown';
  const risk = (params.risk_level as string) ?? 'medium';
  const description = s.description || 'No description provided.';
  const bestTimeframes = s.timeframes?.length ? s.timeframes.join(', ') : '-';
  const bestMarkets = s.symbols?.length ? s.symbols.join(', ') : 'All';
  const signalsCount = (params.signals_count as number) ?? 0;
  const errors = (params.errors as number) ?? 0;
  const defaults = (params.defaults as Record<string, unknown>) ?? {};
  const grid = (params.grid as Record<string, unknown>) ?? {};

  return (
    <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5 flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h3 className="text-white font-semibold text-sm truncate">{s.name}</h3>
        <div className="flex items-center gap-2">
          {statusBadge(s.status)}
          {categoryBadge(category)}
          {riskBadge(risk)}
        </div>
      </div>

      <p className="text-gray-400 text-xs leading-relaxed">{description}</p>

      {/* Meta */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <span className="text-gray-500">Timeframes</span>
        <span className="text-gray-300">{bestTimeframes}</span>
        <span className="text-gray-500">Markets</span>
        <span className="text-gray-300 truncate">{bestMarkets}</span>
      </div>

      {/* Running info */}
      {s.status === 'running' && (
        <div className="flex items-center gap-4 text-xs">
          <span className="text-gray-500">Signals: <span className="text-[#00bfff]">{signalsCount}</span></span>
          <span className="text-gray-500">Priority: <span className="text-white">{s.priority}</span></span>
          {errors > 0 && <span className="text-[#ff4444]">Errors: {errors}</span>}
        </div>
      )}

      {/* Collapsible parameters */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-xs text-[#00bfff] hover:text-[#00bfff]/80 text-left flex items-center gap-1"
      >
        <span className={`transition-transform ${expanded ? 'rotate-90' : ''}`}>&#9654;</span>
        Parameters
      </button>

      {expanded && (
        <div className="bg-[#0a0a0f] rounded-lg p-3 text-xs space-y-2 overflow-auto max-h-48">
          {Object.keys(defaults).length > 0 && (
            <div>
              <p className="text-gray-500 mb-1 font-medium">Defaults</p>
              <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
                {Object.entries(defaults).map(([k, v]) => (
                  <div key={k} className="contents">
                    <span className="text-gray-400">{k}</span>
                    <span className="text-gray-300 truncate">{String(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {Object.keys(grid).length > 0 && (
            <div>
              <p className="text-gray-500 mb-1 font-medium">Grid Values</p>
              <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
                {Object.entries(grid).map(([k, v]) => (
                  <div key={k} className="contents">
                    <span className="text-gray-400">{k}</span>
                    <span className="text-gray-300 truncate">{JSON.stringify(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {Object.keys(defaults).length === 0 && Object.keys(grid).length === 0 && (
            <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
              {Object.entries(params).map(([k, v]) => (
                <div key={k} className="contents">
                  <span className="text-gray-400">{k}</span>
                  <span className="text-gray-300 truncate">{JSON.stringify(v)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loaded Strategies Sub-Tab
// ---------------------------------------------------------------------------

function LoadedStrategies() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dirPath, setDirPath] = useState('');
  const [loadMsg, setLoadMsg] = useState<string | null>(null);

  const fetch_ = useCallback(async () => {
    try {
      const data = await api<StrategyInfo[]>('/strategies');
      setStrategies(data);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch strategies');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetch_(); }, [fetch_]);
  useEffect(() => {
    const iv = setInterval(fetch_, 15_000);
    return () => clearInterval(iv);
  }, [fetch_]);

  const handleLoadDir = async () => {
    if (!dirPath.trim()) return;
    setLoadMsg(null);
    try {
      const res = await post<{ status: string }>('/strategies/load-directory', { path: dirPath.trim() });
      setLoadMsg(`Loaded: ${res.status}`);
      fetch_();
    } catch (err: unknown) {
      setLoadMsg(err instanceof Error ? err.message : 'Failed to load directory');
    }
  };

  if (loading) return <p className="text-gray-500 text-sm py-8 text-center">Loading strategies...</p>;
  if (error) return <p className="text-[#ff4444] text-sm py-8 text-center">{error}</p>;

  return (
    <div className="space-y-6">
      {strategies.length === 0 ? (
        <p className="text-gray-500 text-sm text-center py-8">No strategies loaded yet.</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {strategies.map((s) => (
            <StrategyCard key={s.id} s={s} />
          ))}
        </div>
      )}

      {/* Load from directory */}
      <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5 space-y-3">
        <h3 className="text-white text-sm font-semibold">Load from Directory</h3>
        <div className="flex gap-2">
          <input
            value={dirPath}
            onChange={(e) => setDirPath(e.target.value)}
            placeholder="/path/to/strategies"
            className="flex-1 bg-[#0a0a0f] border border-[#1e1e2e] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-[#00bfff]/50"
          />
          <button
            onClick={handleLoadDir}
            className="px-4 py-2 bg-[#00bfff]/10 text-[#00bfff] rounded-lg text-sm font-medium hover:bg-[#00bfff]/20 transition-colors"
          >
            Load
          </button>
        </div>
        {loadMsg && <p className="text-xs text-gray-400">{loadMsg}</p>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Strategy Generator Sub-Tab
// ---------------------------------------------------------------------------

function StrategyGenerator() {
  const [templates, setTemplates] = useState<StrategyTemplate[]>([]);
  const [selected, setSelected] = useState<StrategyTemplate | null>(null);
  const [paramValues, setParamValues] = useState<Record<string, string>>({});
  const [symbol, setSymbol] = useState('');
  const [priority, setPriority] = useState(5);
  const [deploying, setDeploying] = useState(false);
  const [deployMsg, setDeployMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await api<StrategyTemplate[]>('/strategies/templates');
        setTemplates(data);
        setError(null);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to fetch templates');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const selectTemplate = (t: StrategyTemplate) => {
    setSelected(t);
    setParamValues({});
    setDeployMsg(null);
  };

  // Extract parameters from template code: lines like # PARAM: name = default
  const extractParams = (code: string): { name: string; default_: string }[] => {
    const params: { name: string; default_: string }[] = [];
    const regex = /# *PARAM:\s*(\w+)\s*=\s*(.+)/g;
    let m;
    while ((m = regex.exec(code)) !== null) {
      params.push({ name: m[1], default_: m[2].trim() });
    }
    return params;
  };

  const templateParams = selected ? extractParams(selected.code) : [];

  const buildCode = (): string => {
    if (!selected) return '';
    let code = selected.code;
    for (const p of templateParams) {
      const val = paramValues[p.name] ?? p.default_;
      code = code.replace(new RegExp(`(# *PARAM:\\s*${p.name}\\s*=\\s*)(.+)`, 'g'), `$1${val}`);
    }
    return code;
  };

  const handleDeploy = async () => {
    if (!selected) return;
    setDeploying(true);
    setDeployMsg(null);
    try {
      const code = buildCode();
      const res = await post<{ status: string; strategy_id: string }>('/strategies/load-code', {
        code,
        name: selected.name,
        symbol: symbol || undefined,
        priority,
      });
      setDeployMsg(`Deployed: ${res.strategy_id}`);
    } catch (err: unknown) {
      setDeployMsg(err instanceof Error ? err.message : 'Deploy failed');
    } finally {
      setDeploying(false);
    }
  };

  const handleBatchDeploy = async () => {
    if (!selected || templateParams.length === 0) return;
    setDeploying(true);
    setDeployMsg(null);
    try {
      // Generate grid combos from comma-separated param values
      const paramArrays = templateParams.map((p) => {
        const val = paramValues[p.name] ?? p.default_;
        return val.split(',').map((v) => v.trim());
      });

      // Cartesian product
      const combos = paramArrays.reduce<string[][]>(
        (acc, arr) => acc.flatMap((combo) => arr.map((v) => [...combo, v])),
        [[]],
      );

      let deployed = 0;
      for (const combo of combos.slice(0, 50)) {
        let code = selected.code;
        templateParams.forEach((p, i) => {
          code = code.replace(new RegExp(`(# *PARAM:\\s*${p.name}\\s*=\\s*)(.+)`, 'g'), `$1${combo[i]}`);
        });
        await post('/strategies/load-code', {
          code,
          name: `${selected.name}_${combo.join('_')}`,
          symbol: symbol || undefined,
          priority,
        });
        deployed++;
      }
      setDeployMsg(`Batch deployed ${deployed} strategies`);
    } catch (err: unknown) {
      setDeployMsg(err instanceof Error ? err.message : 'Batch deploy failed');
    } finally {
      setDeploying(false);
    }
  };

  if (loading) return <p className="text-gray-500 text-sm py-8 text-center">Loading templates...</p>;
  if (error) return <p className="text-[#ff4444] text-sm py-8 text-center">{error}</p>;

  return (
    <div className="space-y-6">
      {/* Template picker */}
      <div>
        <h3 className="text-white text-sm font-semibold mb-3">Select Template</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {templates.map((t) => (
            <button
              key={t.name}
              onClick={() => selectTemplate(t)}
              className={`text-left bg-[#12121a] border rounded-xl p-4 transition-colors ${
                selected?.name === t.name
                  ? 'border-[#00bfff] bg-[#00bfff]/5'
                  : 'border-[#1e1e2e] hover:border-[#1e1e2e]/80'
              }`}
            >
              <p className="text-white text-sm font-medium">{t.name}</p>
              <p className="text-gray-500 text-xs mt-1 line-clamp-2">{t.description}</p>
            </button>
          ))}
        </div>
      </div>

      {selected && (
        <>
          {/* Parameter editor */}
          {templateParams.length > 0 && (
            <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5 space-y-3">
              <h3 className="text-white text-sm font-semibold">Parameters</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {templateParams.map((p) => (
                  <div key={p.name}>
                    <label className="text-xs text-gray-500 block mb-1">{p.name}</label>
                    <input
                      value={paramValues[p.name] ?? p.default_}
                      onChange={(e) => setParamValues((prev) => ({ ...prev, [p.name]: e.target.value }))}
                      className="w-full bg-[#0a0a0f] border border-[#1e1e2e] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#00bfff]/50"
                    />
                  </div>
                ))}
              </div>
              <p className="text-xs text-gray-600">Tip: Use comma-separated values for batch deploy grid.</p>
            </div>
          )}

          {/* Deploy section */}
          <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5 space-y-3">
            <h3 className="text-white text-sm font-semibold">Deploy</h3>
            <div className="flex flex-wrap gap-3 items-end">
              <div>
                <label className="text-xs text-gray-500 block mb-1">Symbol</label>
                <input
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  placeholder="BTC/USDT"
                  className="bg-[#0a0a0f] border border-[#1e1e2e] rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-[#00bfff]/50 w-40"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500 block mb-1">Priority</label>
                <input
                  type="number"
                  value={priority}
                  onChange={(e) => setPriority(Number(e.target.value))}
                  className="bg-[#0a0a0f] border border-[#1e1e2e] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#00bfff]/50 w-20"
                />
              </div>
              <button
                onClick={handleDeploy}
                disabled={deploying}
                className="px-4 py-2 bg-[#00ff88]/10 text-[#00ff88] rounded-lg text-sm font-medium hover:bg-[#00ff88]/20 transition-colors disabled:opacity-50"
              >
                {deploying ? 'Deploying...' : 'Deploy'}
              </button>
              {templateParams.length > 0 && (
                <button
                  onClick={handleBatchDeploy}
                  disabled={deploying}
                  className="px-4 py-2 bg-[#ff9800]/10 text-[#ff9800] rounded-lg text-sm font-medium hover:bg-[#ff9800]/20 transition-colors disabled:opacity-50"
                >
                  {deploying ? 'Deploying...' : 'Batch Deploy'}
                </button>
              )}
            </div>
            {deployMsg && <p className="text-xs text-gray-400">{deployMsg}</p>}
          </div>

          {/* Code preview */}
          <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5 space-y-3">
            <h3 className="text-white text-sm font-semibold">Code Preview</h3>
            <pre className="bg-[#0a0a0f] rounded-lg p-4 text-xs text-gray-300 overflow-auto max-h-80 whitespace-pre-wrap font-mono">
              {buildCode()}
            </pre>
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// How-To Guide Sub-Tab
// ---------------------------------------------------------------------------

function HowToGuide() {
  return (
    <div className="space-y-6 max-w-4xl">
      {/* Quick Start */}
      <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5 space-y-3">
        <h3 className="text-white text-sm font-semibold">Quick Start</h3>
        <ol className="list-decimal list-inside text-gray-400 text-sm space-y-2">
          <li>Go to the <span className="text-[#00bfff]">Generator</span> tab and pick a template.</li>
          <li>Adjust parameters to match your risk tolerance and target market.</li>
          <li>Set the symbol and priority, then hit <span className="text-[#00ff88]">Deploy</span>.</li>
          <li>Monitor performance on the <span className="text-[#00bfff]">Leaderboard</span> tab.</li>
          <li>Promote top performers to live trading when ready.</li>
        </ol>
      </div>

      {/* Strategy Categories */}
      <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5 space-y-3">
        <h3 className="text-white text-sm font-semibold">Strategy Categories</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="bg-[#0a0a0f] rounded-lg p-4 border border-[#1e1e2e]">
            <div className="flex items-center gap-2 mb-2">
              {categoryBadge('trend')}
              <span className="text-white text-sm font-medium">Trend Following</span>
            </div>
            <p className="text-gray-500 text-xs">Ride sustained price movements using moving averages, ADX, and momentum indicators. Best in trending markets with clear directional bias.</p>
          </div>
          <div className="bg-[#0a0a0f] rounded-lg p-4 border border-[#1e1e2e]">
            <div className="flex items-center gap-2 mb-2">
              {categoryBadge('reversion')}
              <span className="text-white text-sm font-medium">Mean Reversion</span>
            </div>
            <p className="text-gray-500 text-xs">Profit from price returning to mean. Uses Bollinger Bands, RSI extremes, and z-scores. Works in range-bound markets with clear support/resistance.</p>
          </div>
          <div className="bg-[#0a0a0f] rounded-lg p-4 border border-[#1e1e2e]">
            <div className="flex items-center gap-2 mb-2">
              {categoryBadge('momentum')}
              <span className="text-white text-sm font-medium">Momentum</span>
            </div>
            <p className="text-gray-500 text-xs">Capture acceleration in price action. Uses ROC, MACD divergence, and volume confirmation. Performs well during high-volatility regimes.</p>
          </div>
          <div className="bg-[#0a0a0f] rounded-lg p-4 border border-[#1e1e2e]">
            <div className="flex items-center gap-2 mb-2">
              {categoryBadge('breakout')}
              <span className="text-white text-sm font-medium">Breakout</span>
            </div>
            <p className="text-gray-500 text-xs">Detect and trade price breakouts from consolidation zones. Uses ATR, volume spikes, and range compression. Best after periods of low volatility.</p>
          </div>
        </div>
      </div>

      {/* Writing Custom Strategies */}
      <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5 space-y-3">
        <h3 className="text-white text-sm font-semibold">Writing Custom Strategies</h3>
        <p className="text-gray-400 text-sm">
          Create a Python file that subclasses <code className="text-[#00bfff] bg-[#00bfff]/5 px-1 rounded">BaseStrategy</code> and
          implements the <code className="text-[#00bfff] bg-[#00bfff]/5 px-1 rounded">analyze()</code> method.
        </p>
        <pre className="bg-[#0a0a0f] rounded-lg p-4 text-xs text-gray-300 overflow-auto font-mono whitespace-pre">{`from crypto_mega.strategies.base import BaseStrategy, Signal

class MyStrategy(BaseStrategy):
    name = "my_custom_strategy"
    description = "A custom strategy example"

    # PARAM: fast_period = 10
    # PARAM: slow_period = 30
    # PARAM: rsi_threshold = 30

    async def analyze(self, symbol: str, timeframe: str) -> Signal | None:
        candles = await self.get_candles(symbol, timeframe, limit=100)

        fast_ma = candles["close"].rolling(self.p.fast_period).mean()
        slow_ma = candles["close"].rolling(self.p.slow_period).mean()
        rsi = self.indicators.rsi(candles["close"], 14)

        if fast_ma.iloc[-1] > slow_ma.iloc[-1] and rsi.iloc[-1] < self.p.rsi_threshold:
            return self.signal_long(
                symbol=symbol,
                strength=0.8,
                stop_loss=candles["close"].iloc[-1] * 0.98,
                take_profit=candles["close"].iloc[-1] * 1.04,
            )

        return None`}</pre>
      </div>

      {/* Pro Tips */}
      <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5 space-y-3">
        <h3 className="text-white text-sm font-semibold">Pro Tips</h3>
        <ul className="text-gray-400 text-sm space-y-2">
          <li className="flex gap-2">
            <span className="text-[#00ff88]">&#9679;</span>
            Use the <strong className="text-white">Batch Deploy</strong> feature with comma-separated parameter values to explore a grid of configurations quickly.
          </li>
          <li className="flex gap-2">
            <span className="text-[#00bfff]">&#9679;</span>
            Start with <strong className="text-white">low priority</strong> (1-3) for experimental strategies and increase only after validating on the leaderboard.
          </li>
          <li className="flex gap-2">
            <span className="text-[#ff9800]">&#9679;</span>
            Always define <strong className="text-white">stop_loss</strong> in your signals. The risk manager enforces position limits, but strategy-level stops are more precise.
          </li>
          <li className="flex gap-2">
            <span className="text-[#a855f7]">&#9679;</span>
            Use the <strong className="text-white">Explore</strong> tab to auto-generate and test hundreds of strategy variants overnight.
          </li>
          <li className="flex gap-2">
            <span className="text-[#ff4444]">&#9679;</span>
            Monitor your strategy&apos;s <strong className="text-white">max drawdown</strong> closely. A Sharpe above 1.5 with drawdown under 15% is a good baseline for promotion.
          </li>
        </ul>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main StrategiesTab
// ---------------------------------------------------------------------------

export default function StrategiesTab() {
  const [subTab, setSubTab] = useState<SubTab>('loaded');

  const tabs: { key: SubTab; label: string }[] = [
    { key: 'loaded', label: 'Loaded Strategies' },
    { key: 'generator', label: 'Strategy Generator' },
    { key: 'howto', label: 'How-To Guide' },
  ];

  return (
    <div className="space-y-6">
      {/* Sub-tab navigation */}
      <div className="flex gap-1 bg-[#12121a] border border-[#1e1e2e] rounded-xl p-1 w-fit">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setSubTab(t.key)}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              subTab === t.key
                ? 'bg-[#00bfff]/10 text-[#00bfff]'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {subTab === 'loaded' && <LoadedStrategies />}
      {subTab === 'generator' && <StrategyGenerator />}
      {subTab === 'howto' && <HowToGuide />}
    </div>
  );
}
