'use client';

import { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import { fmtPrice, fmtTime } from '@/lib/format';
import type { Signal } from '@/lib/types';
import SignalDetailModal from './SignalDetailModal';

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

function strengthBar(strength: number) {
  const pct = Math.min(Math.max(strength * 100, 0), 100);
  const color =
    pct >= 70 ? 'bg-[#00ff88]' : pct >= 40 ? 'bg-[#ff9800]' : 'bg-[#ff4444]';
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-[#1e1e2e] rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400">{pct.toFixed(0)}%</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SignalsTab
// ---------------------------------------------------------------------------

export default function SignalsTab() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSignalId, setSelectedSignalId] = useState<string | null>(null);

  const fetchSignals = useCallback(async () => {
    try {
      const data = await api<Signal[]>('/paper/signals?limit=200');
      // Sort reverse chronological
      data.sort((a, b) => b.timestamp - a.timestamp);
      setSignals(data);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch signals');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSignals();
  }, [fetchSignals]);

  // Poll every 10s
  useEffect(() => {
    const interval = setInterval(fetchSignals, 10_000);
    return () => clearInterval(interval);
  }, [fetchSignals]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-white">Signal Feed</h2>
        <span className="text-xs text-gray-500">
          {signals.length} signal{signals.length !== 1 ? 's' : ''}
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
        {loading && signals.length === 0 ? (
          <div className="p-12 text-center text-gray-500 text-sm">Loading signals...</div>
        ) : signals.length === 0 ? (
          <div className="p-12 text-center">
            <p className="text-gray-500 text-sm">No signals yet</p>
            <p className="text-gray-600 text-xs mt-1">
              Signals will appear here as strategies generate them.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 text-xs uppercase tracking-wider border-b border-[#1e1e2e]">
                  <th className="text-left px-4 py-3">Direction</th>
                  <th className="text-left px-4 py-3">Symbol</th>
                  <th className="text-right px-4 py-3">Price</th>
                  <th className="text-right px-4 py-3">SL</th>
                  <th className="text-right px-4 py-3">TP</th>
                  <th className="text-left px-4 py-3">Strategy</th>
                  <th className="text-center px-4 py-3">Strength</th>
                  <th className="text-right px-4 py-3">Time</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((signal) => (
                  <tr
                    key={signal.id}
                    onClick={() => setSelectedSignalId(signal.id)}
                    className="border-b border-[#1e1e2e]/50 last:border-0 hover:bg-[#1e1e2e]/30 transition-colors cursor-pointer"
                  >
                    <td className="px-4 py-3">{directionBadge(signal.direction)}</td>
                    <td className="px-4 py-3 text-[#00bfff] font-medium">{signal.symbol}</td>
                    <td className="px-4 py-3 text-right text-gray-300 font-mono">
                      {fmtPrice(signal.price)}
                    </td>
                    <td className="px-4 py-3 text-right text-[#ff4444] font-mono">
                      {signal.stop_loss != null ? fmtPrice(signal.stop_loss) : '-'}
                    </td>
                    <td className="px-4 py-3 text-right text-[#00ff88] font-mono">
                      {signal.take_profit != null ? fmtPrice(signal.take_profit) : '-'}
                    </td>
                    <td className="px-4 py-3 text-gray-400 truncate max-w-[160px]">
                      {signal.strategy_name}
                    </td>
                    <td className="px-4 py-3">{strengthBar(signal.strength)}</td>
                    <td className="px-4 py-3 text-right text-gray-500 text-xs font-mono">
                      {fmtTime(signal.timestamp)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Signal detail modal */}
      {selectedSignalId && (
        <SignalDetailModal
          signalId={selectedSignalId}
          onClose={() => setSelectedSignalId(null)}
        />
      )}
    </div>
  );
}
