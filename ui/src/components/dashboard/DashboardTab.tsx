'use client';

import { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import { fmtPnl, fmtPrice, fmtTime, pnlColor } from '@/lib/format';
import type { Signal, LeaderboardEntry, RiskStatus, MonitorStats } from '@/lib/types';

// ---------------------------------------------------------------------------
// Types for API responses
// ---------------------------------------------------------------------------

interface StatusResponse {
  engine_running: boolean;
  strategies_running: number;
  open_positions: number;
  total_signals_24h: number;
  total_pnl: number;
}

// ---------------------------------------------------------------------------
// Inline helpers
// ---------------------------------------------------------------------------

function directionBadge(dir: string) {
  const colors: Record<string, string> = {
    long: 'bg-[#00ff88]/10 text-[#00ff88]',
    short: 'bg-[#ff4444]/10 text-[#ff4444]',
    close: 'bg-[#ff9800]/10 text-[#ff9800]',
    hold: 'bg-[#00bfff]/10 text-[#00bfff]',
  };
  return (
    <span
      className={`px-2 py-0.5 rounded text-xs font-medium uppercase ${colors[dir] ?? 'bg-gray-700 text-gray-300'}`}
    >
      {dir}
    </span>
  );
}

function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string | number;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5">
      <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">{label}</p>
      <p className={`text-2xl font-bold ${accent ?? 'text-white'}`}>{value}</p>
      {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DashboardTab
// ---------------------------------------------------------------------------

interface DashboardTabProps {
  onSignalClick?: (signal: Signal) => void;
}

export default function DashboardTab({ onSignalClick }: DashboardTabProps) {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [risk, setRisk] = useState<RiskStatus | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = useCallback(async () => {
    try {
      const [s, r, lb, sig] = await Promise.all([
        api<StatusResponse>('/status'),
        api<RiskStatus>('/risk'),
        api<LeaderboardEntry[]>('/paper/leaderboard?limit=5'),
        api<Signal[]>('/paper/signals?limit=20'),
      ]);
      setStatus(s);
      setRisk(r);
      setLeaderboard(lb);
      setSignals(sig);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch dashboard data');
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 5000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  // ---- Derived values ----
  const recentSignals = signals.slice(0, 10);

  return (
    <div className="space-y-6">
      {/* Error banner */}
      {error && (
        <div className="bg-[#ff4444]/10 border border-[#ff4444]/30 text-[#ff4444] rounded-lg px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {/* ---- Stat cards ---- */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Strategies Running"
          value={status?.strategies_running ?? '-'}
          sub={status?.engine_running ? 'Engine active' : 'Engine stopped'}
          accent={status?.engine_running ? 'text-[#00ff88]' : 'text-[#ff4444]'}
        />
        <StatCard
          label="Open Positions"
          value={status?.open_positions ?? '-'}
          accent="text-[#00bfff]"
        />
        <StatCard
          label="Total Paper P&L"
          value={status ? fmtPnl(status.total_pnl) : '-'}
          accent={status ? pnlColor(status.total_pnl) : undefined}
        />
        <StatCard
          label="Signals (24h)"
          value={status?.total_signals_24h ?? '-'}
          accent="text-white"
        />
      </div>

      {/* ---- Middle row: Risk + Recent Signals ---- */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Risk card */}
        <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
            Risk Monitor
          </h3>
          {risk ? (
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-gray-400 text-sm">Equity</span>
                <span className="text-white font-medium">{fmtPrice(risk.equity)}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-400 text-sm">Drawdown</span>
                <span className={`font-medium ${risk.drawdown_pct > 10 ? 'text-[#ff4444]' : risk.drawdown_pct > 5 ? 'text-[#ff9800]' : 'text-[#00ff88]'}`}>
                  {risk.drawdown_pct.toFixed(2)}%
                </span>
              </div>
              {/* Drawdown bar */}
              <div className="w-full bg-[#1e1e2e] rounded-full h-2">
                <div
                  className={`h-2 rounded-full ${risk.drawdown_pct > 10 ? 'bg-[#ff4444]' : risk.drawdown_pct > 5 ? 'bg-[#ff9800]' : 'bg-[#00ff88]'}`}
                  style={{ width: `${Math.min(risk.drawdown_pct, 100)}%` }}
                />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-400 text-sm">Kill Switch</span>
                <span
                  className={`px-2 py-0.5 rounded text-xs font-medium ${
                    risk.kill_switch
                      ? 'bg-[#ff4444]/20 text-[#ff4444]'
                      : 'bg-[#00ff88]/20 text-[#00ff88]'
                  }`}
                >
                  {risk.kill_switch ? 'ACTIVE' : 'OFF'}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-400 text-sm">Daily Trades</span>
                <span className="text-white font-medium">{risk.daily_trades}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-400 text-sm">Open Positions</span>
                <span className="text-white font-medium">{risk.open_positions}</span>
              </div>
            </div>
          ) : (
            <p className="text-gray-500 text-sm">Loading risk data...</p>
          )}
        </div>

        {/* Recent Signals */}
        <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
            Recent Signals
          </h3>
          {recentSignals.length > 0 ? (
            <div className="space-y-2 max-h-80 overflow-y-auto">
              {recentSignals.map((sig) => (
                <button
                  key={sig.id}
                  onClick={() => onSignalClick?.(sig)}
                  className="w-full flex items-center justify-between px-3 py-2 rounded-lg hover:bg-[#1e1e2e] transition-colors text-left"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    {directionBadge(sig.direction)}
                    <div className="min-w-0">
                      <p className="text-sm text-white font-medium truncate">
                        {sig.symbol}
                      </p>
                      <p className="text-xs text-gray-500 truncate">
                        {sig.strategy_name}
                      </p>
                    </div>
                  </div>
                  <div className="text-right flex-shrink-0 ml-3">
                    <p className="text-sm text-white">{fmtPrice(sig.price)}</p>
                    <p className="text-xs text-gray-500">{fmtTime(sig.timestamp)}</p>
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <p className="text-gray-500 text-sm">No recent signals</p>
          )}
        </div>
      </div>

      {/* ---- Mini Leaderboard ---- */}
      <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
          Top Strategies
        </h3>
        {leaderboard.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 text-xs uppercase tracking-wider border-b border-[#1e1e2e]">
                  <th className="text-left pb-3 pr-4">#</th>
                  <th className="text-left pb-3 pr-4">Strategy</th>
                  <th className="text-right pb-3 pr-4">P&L %</th>
                  <th className="text-right pb-3 pr-4">Win Rate</th>
                  <th className="text-right pb-3">Trades</th>
                </tr>
              </thead>
              <tbody>
                {leaderboard.map((entry, idx) => (
                  <tr
                    key={entry.strategy_id}
                    className="border-b border-[#1e1e2e]/50 last:border-0"
                  >
                    <td className="py-2 pr-4 text-gray-500">{idx + 1}</td>
                    <td className="py-2 pr-4">
                      <p className="text-white font-medium">{entry.strategy_name}</p>
                    </td>
                    <td className={`py-2 pr-4 text-right font-medium ${pnlColor(entry.total_pnl_pct)}`}>
                      {entry.total_pnl_pct >= 0 ? '+' : ''}
                      {entry.total_pnl_pct.toFixed(2)}%
                    </td>
                    <td className="py-2 pr-4 text-right text-gray-300">
                      {(entry.win_rate * 100).toFixed(1)}%
                    </td>
                    <td className="py-2 text-right text-gray-300">
                      {entry.wins + entry.losses}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-gray-500 text-sm">No strategy data yet</p>
        )}
      </div>
    </div>
  );
}
