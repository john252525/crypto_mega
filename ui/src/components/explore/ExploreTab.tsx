'use client';

import { useEffect, useState, useCallback } from 'react';
import { api, post } from '@/lib/api';
import type { ExploreStats, LeaderboardEntry } from '@/lib/types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ExploreLeaderboardEntry {
  strategy_name: string;
  symbol: string;
  timeframe: string;
  sharpe_ratio: number;
  total_pnl_pct: number;
  win_rate: number;
  profit_factor: number;
  closed_positions: number;
  max_drawdown: number;
  parameters: Record<string, unknown>;
  status: string;
}

interface ExploreSymbols {
  [exchange: string]: string[];
}

// ---------------------------------------------------------------------------
// Sort options
// ---------------------------------------------------------------------------

type SortKey = 'sharpe_ratio' | 'total_pnl_pct' | 'win_rate' | 'profit_factor' | 'closed_positions';

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'sharpe_ratio', label: 'Sharpe Ratio' },
  { value: 'total_pnl_pct', label: 'P&L %' },
  { value: 'win_rate', label: 'Win Rate' },
  { value: 'profit_factor', label: 'Profit Factor' },
  { value: 'closed_positions', label: 'Trades' },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function StatCard({
  label,
  value,
  accent,
}: {
  label: string;
  value: string | number;
  accent?: string;
}) {
  return (
    <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5">
      <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-2xl font-bold ${accent ?? 'text-white'}`}>{value}</p>
    </div>
  );
}

function statusBadge(status: string) {
  const map: Record<string, string> = {
    running: 'bg-[#00ff88]/10 text-[#00ff88]',
    completed: 'bg-[#00bfff]/10 text-[#00bfff]',
    promoted: 'bg-[#a855f7]/10 text-[#a855f7]',
    failed: 'bg-[#ff4444]/10 text-[#ff4444]',
    pending: 'bg-[#ff9800]/10 text-[#ff9800]',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium uppercase ${map[status] ?? 'bg-gray-700 text-gray-300'}`}>
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// ExploreTab
// ---------------------------------------------------------------------------

export default function ExploreTab() {
  const [stats, setStats] = useState<ExploreStats | null>(null);
  const [leaderboard, setLeaderboard] = useState<ExploreLeaderboardEntry[]>([]);
  const [symbols, setSymbols] = useState<ExploreSymbols | string[]>([]);
  const [sortBy, setSortBy] = useState<SortKey>('sharpe_ratio');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const [s, lb, sym] = await Promise.all([
        api<ExploreStats>('/explore/stats'),
        api<ExploreLeaderboardEntry[]>(`/explore/leaderboard?limit=50&sort_by=${sortBy}`),
        api<ExploreSymbols | string[]>('/explore/symbols'),
      ]);
      setStats(s);
      setLeaderboard(lb);
      setSymbols(sym);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch explore data');
    } finally {
      setLoading(false);
    }
  }, [sortBy]);

  useEffect(() => {
    setLoading(true);
    fetchAll();
  }, [fetchAll]);

  useEffect(() => {
    const iv = setInterval(fetchAll, 10_000);
    return () => clearInterval(iv);
  }, [fetchAll]);

  // Action handlers
  const handleAction = async (label: string, action: () => Promise<unknown>) => {
    setActionMsg(null);
    try {
      await action();
      setActionMsg(`${label}: success`);
      fetchAll();
    } catch (err: unknown) {
      setActionMsg(`${label}: ${err instanceof Error ? err.message : 'failed'}`);
    }
  };

  if (loading && !stats) return <p className="text-gray-500 text-sm py-8 text-center">Loading explorer...</p>;
  if (error && !stats) return <p className="text-[#ff4444] text-sm py-8 text-center">{error}</p>;

  // Derive pipeline counts from stats
  const pending = stats?.queue_size ?? 0;
  const totalResults = leaderboard.length;
  const promoted = stats?.total_promoted ?? 0;
  const symbolsTested = Array.isArray(symbols)
    ? symbols.length
    : Object.values(symbols as ExploreSymbols).flat().length;

  return (
    <div className="space-y-6">
      {/* Status cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
        <StatCard
          label="Explorer Status"
          value={stats?.running ? 'Running' : 'Stopped'}
          accent={stats?.running ? 'text-[#00ff88]' : 'text-gray-400'}
        />
        <StatCard label="Total Results" value={totalResults} accent="text-[#00bfff]" />
        <StatCard label="Symbols Tested" value={symbolsTested} />
        <StatCard label="Strategies Tested" value={stats?.total_generated ?? 0} />
        <StatCard label="Workers Online" value={pending > 0 ? 'Active' : 'Idle'} accent={pending > 0 ? 'text-[#00ff88]' : 'text-gray-400'} />
        <StatCard label="Promoted" value={promoted} accent="text-[#a855f7]" />
      </div>

      {/* Task Pipeline */}
      <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5 space-y-4">
        <h3 className="text-white text-sm font-semibold">Task Pipeline</h3>
        <div className="flex flex-wrap gap-4 items-center">
          <div className="flex gap-6 text-sm">
            <span className="text-gray-500">Pending: <span className="text-[#ff9800] font-medium">{pending}</span></span>
            <span className="text-gray-500">Running: <span className="text-[#00bfff] font-medium">{stats?.running ? 'Yes' : 'No'}</span></span>
            <span className="text-gray-500">Done: <span className="text-[#00ff88] font-medium">{stats?.total_generated ?? 0}</span></span>
            <span className="text-gray-500">Promoted: <span className="text-[#a855f7] font-medium">{promoted}</span></span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => handleAction('Start Explorer', () => post('/explore/start'))}
            className="px-3 py-1.5 bg-[#00ff88]/10 text-[#00ff88] rounded-lg text-xs font-medium hover:bg-[#00ff88]/20 transition-colors"
          >
            Start Explorer
          </button>
          <button
            onClick={() => handleAction('Stop', () => post('/explore/stop'))}
            className="px-3 py-1.5 bg-[#ff4444]/10 text-[#ff4444] rounded-lg text-xs font-medium hover:bg-[#ff4444]/20 transition-colors"
          >
            Stop
          </button>
          <button
            onClick={() => handleAction('Generate Tasks', () => post('/explore/generate?count=50'))}
            className="px-3 py-1.5 bg-[#00bfff]/10 text-[#00bfff] rounded-lg text-xs font-medium hover:bg-[#00bfff]/20 transition-colors"
          >
            Generate 50 Tasks
          </button>
          <button
            onClick={() => handleAction('Refresh Symbols', () => post('/explore/refresh-symbols'))}
            className="px-3 py-1.5 bg-[#ff9800]/10 text-[#ff9800] rounded-lg text-xs font-medium hover:bg-[#ff9800]/20 transition-colors"
          >
            Refresh Symbols
          </button>
        </div>
        {actionMsg && <p className="text-xs text-gray-400">{actionMsg}</p>}
      </div>

      {/* Exploration Leaderboard */}
      <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <h3 className="text-white text-sm font-semibold">Exploration Leaderboard</h3>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortKey)}
            className="bg-[#0a0a0f] border border-[#1e1e2e] rounded-lg px-3 py-1.5 text-xs text-gray-300 focus:outline-none focus:border-[#00bfff]/50"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 text-left border-b border-[#1e1e2e]">
                <th className="pb-2 pr-3 font-medium">#</th>
                <th className="pb-2 pr-3 font-medium">Strategy</th>
                <th className="pb-2 pr-3 font-medium">Symbol</th>
                <th className="pb-2 pr-3 font-medium">TF</th>
                <th className="pb-2 pr-3 font-medium text-right">Sharpe</th>
                <th className="pb-2 pr-3 font-medium text-right">P&L %</th>
                <th className="pb-2 pr-3 font-medium text-right">Win Rate</th>
                <th className="pb-2 pr-3 font-medium text-right">PF</th>
                <th className="pb-2 pr-3 font-medium text-right">Trades</th>
                <th className="pb-2 pr-3 font-medium text-right">Max DD</th>
                <th className="pb-2 pr-3 font-medium">Params</th>
                <th className="pb-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.length === 0 ? (
                <tr>
                  <td colSpan={12} className="text-gray-500 text-center py-8">No exploration results yet.</td>
                </tr>
              ) : (
                leaderboard.map((e, i) => (
                  <tr key={`${e.strategy_name}-${e.symbol}-${i}`} className="border-b border-[#1e1e2e]/50 hover:bg-[#0a0a0f]/50">
                    <td className="py-2 pr-3 text-gray-500">{i + 1}</td>
                    <td className="py-2 pr-3 text-white font-medium truncate max-w-[140px]">{e.strategy_name}</td>
                    <td className="py-2 pr-3 text-gray-300">{e.symbol}</td>
                    <td className="py-2 pr-3 text-gray-400">{e.timeframe}</td>
                    <td className={`py-2 pr-3 text-right font-mono ${e.sharpe_ratio >= 1.5 ? 'text-[#00ff88]' : e.sharpe_ratio >= 0 ? 'text-gray-300' : 'text-[#ff4444]'}`}>
                      {e.sharpe_ratio?.toFixed(2) ?? '-'}
                    </td>
                    <td className={`py-2 pr-3 text-right font-mono ${e.total_pnl_pct >= 0 ? 'text-[#00ff88]' : 'text-[#ff4444]'}`}>
                      {e.total_pnl_pct >= 0 ? '+' : ''}{e.total_pnl_pct?.toFixed(2) ?? '-'}%
                    </td>
                    <td className={`py-2 pr-3 text-right font-mono ${e.win_rate >= 0.55 ? 'text-[#00ff88]' : 'text-gray-300'}`}>
                      {(e.win_rate * 100)?.toFixed(1) ?? '-'}%
                    </td>
                    <td className={`py-2 pr-3 text-right font-mono ${e.profit_factor >= 1.5 ? 'text-[#00ff88]' : e.profit_factor >= 1 ? 'text-gray-300' : 'text-[#ff4444]'}`}>
                      {e.profit_factor?.toFixed(2) ?? '-'}
                    </td>
                    <td className="py-2 pr-3 text-right font-mono text-gray-300">{e.closed_positions ?? '-'}</td>
                    <td className={`py-2 pr-3 text-right font-mono ${e.max_drawdown > 20 ? 'text-[#ff4444]' : e.max_drawdown > 10 ? 'text-[#ff9800]' : 'text-gray-300'}`}>
                      {e.max_drawdown?.toFixed(1) ?? '-'}%
                    </td>
                    <td className="py-2 pr-3 text-gray-500 truncate max-w-[120px]" title={JSON.stringify(e.parameters)}>
                      {e.parameters ? Object.entries(e.parameters).map(([k, v]) => `${k}=${v}`).join(', ') : '-'}
                    </td>
                    <td className="py-2">{statusBadge(e.status ?? 'completed')}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Available Symbols */}
      <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5 space-y-4">
        <h3 className="text-white text-sm font-semibold">Available Symbols</h3>
        {Array.isArray(symbols) ? (
          <div className="flex flex-wrap gap-2">
            {(symbols as string[]).map((s) => (
              <span key={s} className="px-2 py-1 bg-[#0a0a0f] border border-[#1e1e2e] rounded text-xs text-gray-300">
                {s}
              </span>
            ))}
            {(symbols as string[]).length === 0 && (
              <p className="text-gray-500 text-xs">No symbols available. Click &quot;Refresh Symbols&quot; above.</p>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            {Object.entries(symbols as ExploreSymbols).map(([exchange, syms]) => (
              <div key={exchange}>
                <p className="text-[#00bfff] text-xs font-medium mb-1 uppercase">{exchange}</p>
                <div className="flex flex-wrap gap-2">
                  {syms.map((s) => (
                    <span key={s} className="px-2 py-1 bg-[#0a0a0f] border border-[#1e1e2e] rounded text-xs text-gray-300">
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            ))}
            {Object.keys(symbols as ExploreSymbols).length === 0 && (
              <p className="text-gray-500 text-xs">No symbols available. Click &quot;Refresh Symbols&quot; above.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
