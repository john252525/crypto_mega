'use client';

import { useEffect, useState, useCallback } from 'react';
import { api, post } from '@/lib/api';
import { fmtPnl, pnlColor } from '@/lib/format';
import type { LeaderboardEntry } from '@/lib/types';

// ---------------------------------------------------------------------------
// Sort options
// ---------------------------------------------------------------------------

type SortKey = 'total_pnl_pct' | 'sharpe_ratio' | 'win_rate' | 'profit_factor' | 'trades';

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: 'total_pnl_pct', label: 'P&L %' },
  { value: 'sharpe_ratio', label: 'Sharpe' },
  { value: 'win_rate', label: 'Win Rate' },
  { value: 'profit_factor', label: 'Profit Factor' },
  { value: 'trades', label: 'Trades' },
];

// ---------------------------------------------------------------------------
// Sparkline SVG
// ---------------------------------------------------------------------------

function Sparkline({ data }: { data: number[] }) {
  if (!data || data.length < 2) return <span className="text-gray-600">-</span>;
  const w = 80, h = 24;
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const points = data
    .map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * h}`)
    .join(' ');
  const color = data[data.length - 1] >= data[0] ? '#00ff88' : '#ff4444';
  return (
    <svg width={w} height={h} className="inline-block">
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// LeaderboardTab
// ---------------------------------------------------------------------------

export default function LeaderboardTab() {
  const [sortBy, setSortBy] = useState<SortKey>('total_pnl_pct');
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [promoting, setPromoting] = useState<string | null>(null);

  const fetchLeaderboard = useCallback(async (sort: SortKey) => {
    try {
      const data = await api<LeaderboardEntry[]>(`/paper/leaderboard?sort_by=${sort}`);
      setEntries(data);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch leaderboard');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    fetchLeaderboard(sortBy);
  }, [sortBy, fetchLeaderboard]);

  // Poll every 10s
  useEffect(() => {
    const interval = setInterval(() => fetchLeaderboard(sortBy), 10_000);
    return () => clearInterval(interval);
  }, [sortBy, fetchLeaderboard]);

  const handlePromote = async (strategyId: string) => {
    setPromoting(strategyId);
    try {
      await post(`/paper/promote/${strategyId}`);
      // Refresh after promotion
      await fetchLeaderboard(sortBy);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to promote strategy');
    } finally {
      setPromoting(null);
    }
  };

  return (
    <div className="space-y-4">
      {/* Header + Sort */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">Strategy Leaderboard</h2>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500 uppercase tracking-wider">Sort by</span>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as SortKey)}
            className="bg-[#12121a] border border-[#1e1e2e] rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-[#00bfff] transition-colors"
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-[#ff4444]/10 border border-[#ff4444]/30 text-[#ff4444] rounded-lg px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl overflow-hidden">
        {loading && entries.length === 0 ? (
          <div className="p-12 text-center text-gray-500 text-sm">Loading leaderboard...</div>
        ) : entries.length === 0 ? (
          <div className="p-12 text-center">
            <p className="text-gray-500 text-sm">No strategies tracked yet</p>
            <p className="text-gray-600 text-xs mt-1">
              Strategies will appear here once they generate signals.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 text-xs uppercase tracking-wider border-b border-[#1e1e2e]">
                  <th className="text-left px-4 py-3">#</th>
                  <th className="text-left px-4 py-3">Strategy</th>
                  <th className="text-right px-4 py-3">P&L %</th>
                  <th className="text-right px-4 py-3">Trades</th>
                  <th className="text-right px-4 py-3">Win Rate</th>
                  <th className="text-right px-4 py-3">Sharpe</th>
                  <th className="text-right px-4 py-3">PF</th>
                  <th className="text-right px-4 py-3">Max DD</th>
                  <th className="text-right px-4 py-3">Open</th>
                  <th className="text-center px-4 py-3">Equity</th>
                  <th className="text-center px-4 py-3">Action</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry, idx) => {
                  const totalTrades = entry.wins + entry.losses;
                  return (
                    <tr
                      key={entry.strategy_id}
                      className="border-b border-[#1e1e2e]/50 last:border-0 hover:bg-[#1e1e2e]/30 transition-colors"
                    >
                      {/* Rank */}
                      <td className="px-4 py-3 text-gray-500 font-medium">{idx + 1}</td>

                      {/* Strategy */}
                      <td className="px-4 py-3">
                        <p className="text-white font-medium">{entry.strategy_name}</p>
                        <p className="text-xs text-gray-600 font-mono truncate max-w-[140px]">
                          {entry.strategy_id}
                        </p>
                      </td>

                      {/* P&L % */}
                      <td className={`px-4 py-3 text-right font-medium ${pnlColor(entry.total_pnl_pct)}`}>
                        {entry.total_pnl_pct >= 0 ? '+' : ''}
                        {entry.total_pnl_pct.toFixed(2)}%
                      </td>

                      {/* Trades */}
                      <td className="px-4 py-3 text-right text-gray-300">{totalTrades}</td>

                      {/* Win Rate */}
                      <td className="px-4 py-3 text-right text-gray-300">
                        {(entry.win_rate * 100).toFixed(1)}%
                      </td>

                      {/* Sharpe */}
                      <td
                        className={`px-4 py-3 text-right font-medium ${
                          entry.sharpe_ratio >= 2
                            ? 'text-[#00ff88]'
                            : entry.sharpe_ratio >= 1
                              ? 'text-[#00bfff]'
                              : entry.sharpe_ratio >= 0
                                ? 'text-gray-300'
                                : 'text-[#ff4444]'
                        }`}
                      >
                        {entry.sharpe_ratio.toFixed(2)}
                      </td>

                      {/* Profit Factor */}
                      <td className="px-4 py-3 text-right text-gray-300">
                        {entry.profit_factor.toFixed(2)}
                      </td>

                      {/* Max DD */}
                      <td className="px-4 py-3 text-right text-[#ff4444]">
                        {entry.max_drawdown.toFixed(2)}%
                      </td>

                      {/* Open Positions */}
                      <td className="px-4 py-3 text-right text-gray-300">
                        {entry.open_positions}
                      </td>

                      {/* Equity Curve Sparkline */}
                      <td className="px-4 py-3 text-center">
                        <Sparkline data={entry.equity_curve} />
                      </td>

                      {/* Action */}
                      <td className="px-4 py-3 text-center">
                        {entry.promoted ? (
                          <span className="text-xs text-[#00ff88] font-medium px-2 py-1 rounded bg-[#00ff88]/10">
                            Promoted
                          </span>
                        ) : (
                          <button
                            onClick={() => handlePromote(entry.strategy_id)}
                            disabled={promoting === entry.strategy_id}
                            className="text-xs font-medium px-3 py-1 rounded border border-[#00bfff]/40 text-[#00bfff] hover:bg-[#00bfff]/10 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                          >
                            {promoting === entry.strategy_id ? 'Promoting...' : 'Promote'}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
