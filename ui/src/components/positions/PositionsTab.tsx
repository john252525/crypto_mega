'use client';

import { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import { fmtPrice, fmtPnl, fmtDate } from '@/lib/format';
import type { OpenPosition, ClosedPosition } from '@/lib/types';
import PositionDetailModal from './PositionDetailModal';

// ---------------------------------------------------------------------------
// Helpers
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

function pnlCell(pct: number) {
  const color = pct > 0 ? 'text-[#00ff88]' : pct < 0 ? 'text-[#ff4444]' : 'text-gray-400';
  return <span className={`font-mono ${color}`}>{fmtPnl(pct)}</span>;
}

function closeReasonBadge(reason: string) {
  const map: Record<string, string> = {
    tp: 'bg-[#00ff88]/10 text-[#00ff88]',
    sl: 'bg-[#ff4444]/10 text-[#ff4444]',
    signal: 'bg-[#ff9800]/10 text-[#ff9800]',
    manual: 'bg-[#00bfff]/10 text-[#00bfff]',
    timeout: 'bg-gray-700/50 text-gray-400',
  };
  return (
    <span
      className={`px-2 py-0.5 rounded text-xs font-medium uppercase ${map[reason] ?? 'bg-gray-700 text-gray-300'}`}
    >
      {reason}
    </span>
  );
}

// ---------------------------------------------------------------------------
// PositionsTab
// ---------------------------------------------------------------------------

type SubTab = 'open' | 'closed';

export default function PositionsTab() {
  const [subTab, setSubTab] = useState<SubTab>('open');

  const [openPositions, setOpenPositions] = useState<OpenPosition[]>([]);
  const [closedPositions, setClosedPositions] = useState<ClosedPosition[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPositionId, setSelectedPositionId] = useState<string | null>(null);

  const fetchOpen = useCallback(async () => {
    try {
      const data = await api<OpenPosition[]>('/paper/positions/open');
      setOpenPositions(data);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch open positions');
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchClosed = useCallback(async () => {
    try {
      const data = await api<ClosedPosition[]>('/paper/positions/closed?limit=200');
      setClosedPositions(data);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch closed positions');
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch based on active sub-tab
  useEffect(() => {
    setLoading(true);
    if (subTab === 'open') {
      fetchOpen();
    } else {
      fetchClosed();
    }
  }, [subTab, fetchOpen, fetchClosed]);

  // Poll every 10s
  useEffect(() => {
    const interval = setInterval(() => {
      if (subTab === 'open') fetchOpen();
      else fetchClosed();
    }, 10_000);
    return () => clearInterval(interval);
  }, [subTab, fetchOpen, fetchClosed]);

  const count = subTab === 'open' ? openPositions.length : closedPositions.length;

  return (
    <div className="space-y-4">
      {/* Header with sub-tabs */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-white">Positions</h2>
          <div className="flex ml-4 bg-[#0a0a0f] border border-[#1e1e2e] rounded-lg overflow-hidden">
            <button
              onClick={() => setSubTab('open')}
              className={`px-4 py-1.5 text-xs font-medium transition-colors ${
                subTab === 'open'
                  ? 'bg-[#1e1e2e] text-[#00bfff]'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              Open
            </button>
            <button
              onClick={() => setSubTab('closed')}
              className={`px-4 py-1.5 text-xs font-medium transition-colors ${
                subTab === 'closed'
                  ? 'bg-[#1e1e2e] text-[#00bfff]'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              Closed
            </button>
          </div>
        </div>
        <span className="text-xs text-gray-500">
          {count} position{count !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-[#ff4444]/10 border border-[#ff4444]/30 text-[#ff4444] rounded-lg px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl overflow-hidden">
        {loading && count === 0 ? (
          <div className="p-12 text-center text-gray-500 text-sm">Loading positions...</div>
        ) : count === 0 ? (
          <div className="p-12 text-center">
            <p className="text-gray-500 text-sm">
              No {subTab} positions
            </p>
            <p className="text-gray-600 text-xs mt-1">
              {subTab === 'open'
                ? 'Open positions will appear here when strategies enter trades.'
                : 'Closed positions will appear here after trades are completed.'}
            </p>
          </div>
        ) : subTab === 'open' ? (
          /* Open positions table */
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 text-xs uppercase tracking-wider border-b border-[#1e1e2e]">
                  <th className="text-left px-4 py-3">Strategy</th>
                  <th className="text-left px-4 py-3">Symbol</th>
                  <th className="text-left px-4 py-3">Dir</th>
                  <th className="text-right px-4 py-3">Entry</th>
                  <th className="text-right px-4 py-3">Current</th>
                  <th className="text-right px-4 py-3">P&L %</th>
                  <th className="text-right px-4 py-3">SL</th>
                  <th className="text-right px-4 py-3">TP</th>
                </tr>
              </thead>
              <tbody>
                {openPositions.map((pos) => (
                  <tr
                    key={pos.id}
                    onClick={() => setSelectedPositionId(pos.id)}
                    className="border-b border-[#1e1e2e]/50 last:border-0 hover:bg-[#1e1e2e]/30 transition-colors cursor-pointer"
                  >
                    <td className="px-4 py-3 text-gray-400 truncate max-w-[140px]">
                      {pos.strategy_name}
                    </td>
                    <td className="px-4 py-3 text-[#00bfff] font-medium">{pos.symbol}</td>
                    <td className="px-4 py-3">{directionBadge(pos.direction)}</td>
                    <td className="px-4 py-3 text-right text-gray-300 font-mono">
                      {fmtPrice(pos.entry_price)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-300 font-mono">
                      {fmtPrice(pos.current_price)}
                    </td>
                    <td className="px-4 py-3 text-right">{pnlCell(pos.unrealized_pnl_pct)}</td>
                    <td className="px-4 py-3 text-right text-[#ff4444] font-mono">
                      {pos.stop_loss != null ? fmtPrice(pos.stop_loss) : '-'}
                    </td>
                    <td className="px-4 py-3 text-right text-[#00ff88] font-mono">
                      {pos.take_profit != null ? fmtPrice(pos.take_profit) : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          /* Closed positions table */
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 text-xs uppercase tracking-wider border-b border-[#1e1e2e]">
                  <th className="text-left px-4 py-3">Strategy</th>
                  <th className="text-left px-4 py-3">Symbol</th>
                  <th className="text-left px-4 py-3">Dir</th>
                  <th className="text-right px-4 py-3">Entry</th>
                  <th className="text-right px-4 py-3">Exit</th>
                  <th className="text-right px-4 py-3">P&L %</th>
                  <th className="text-center px-4 py-3">Reason</th>
                  <th className="text-right px-4 py-3">Closed At</th>
                </tr>
              </thead>
              <tbody>
                {closedPositions.map((pos) => (
                  <tr
                    key={pos.id}
                    onClick={() => setSelectedPositionId(pos.id)}
                    className="border-b border-[#1e1e2e]/50 last:border-0 hover:bg-[#1e1e2e]/30 transition-colors cursor-pointer"
                  >
                    <td className="px-4 py-3 text-gray-400 truncate max-w-[140px]">
                      {pos.strategy_name}
                    </td>
                    <td className="px-4 py-3 text-[#00bfff] font-medium">{pos.symbol}</td>
                    <td className="px-4 py-3">{directionBadge(pos.direction)}</td>
                    <td className="px-4 py-3 text-right text-gray-300 font-mono">
                      {fmtPrice(pos.entry_price)}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-300 font-mono">
                      {pos.exit_price != null ? fmtPrice(pos.exit_price) : '-'}
                    </td>
                    <td className="px-4 py-3 text-right">{pnlCell(pos.realized_pnl_pct)}</td>
                    <td className="px-4 py-3 text-center">{closeReasonBadge(pos.close_reason)}</td>
                    <td className="px-4 py-3 text-right text-gray-500 text-xs font-mono">
                      {fmtDate(pos.closed_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Position detail modal */}
      {selectedPositionId && (
        <PositionDetailModal
          positionId={selectedPositionId}
          onClose={() => setSelectedPositionId(null)}
        />
      )}
    </div>
  );
}
