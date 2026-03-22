'use client';

import { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import type { CandleSummary, CollectorStatus, GapResult } from '@/lib/types';

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

/** Format ISO date string to relative time with freshness color. */
function relativeTime(iso: string | null | undefined): { text: string; color: string } {
  if (!iso) return { text: '-', color: 'text-gray-500' };
  const now = Date.now();
  const then = new Date(iso).getTime();
  if (isNaN(then)) return { text: '-', color: 'text-gray-500' };
  const diffSec = Math.max(0, Math.floor((now - then) / 1000));

  let text: string;
  if (diffSec < 60) text = `${diffSec}s ago`;
  else if (diffSec < 3600) text = `${Math.floor(diffSec / 60)}m ago`;
  else if (diffSec < 86400) text = `${Math.floor(diffSec / 3600)}h ago`;
  else text = `${Math.floor(diffSec / 86400)}d ago`;

  // Color coding: fresh (<1h) = green, stale (1h-24h) = yellow, old (>24h) = red
  let color: string;
  if (diffSec < 3600) color = 'text-[#00ff88]';
  else if (diffSec < 86400) color = 'text-[#ff9800]';
  else color = 'text-[#ff4444]';

  return { text, color };
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '-';
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function daysBetween(from: string | null | undefined, to: string | null | undefined): string {
  if (!from || !to) return '-';
  const a = new Date(from).getTime();
  const b = new Date(to).getTime();
  if (isNaN(a) || isNaN(b)) return '-';
  return String(Math.max(0, Math.round((b - a) / 86400000)));
}

// ---------------------------------------------------------------------------
// Extended CandleSummary with optional fields the API may return
// ---------------------------------------------------------------------------

interface CandleSummaryExt extends CandleSummary {
  last_checked?: string;
  data_changed?: string;
  interval?: string;
}

// ---------------------------------------------------------------------------
// DataTab
// ---------------------------------------------------------------------------

export default function DataTab() {
  const [summaries, setSummaries] = useState<CandleSummaryExt[]>([]);
  const [collector, setCollector] = useState<CollectorStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Gap checker state
  const [gapSymbol, setGapSymbol] = useState('');
  const [gapTf, setGapTf] = useState('');
  const [gapResult, setGapResult] = useState<GapResult | null>(null);
  const [gapLoading, setGapLoading] = useState(false);
  const [gapError, setGapError] = useState<string | null>(null);
  const [gapExpanded, setGapExpanded] = useState(false);

  const fetchAll = useCallback(async () => {
    try {
      const [s, c] = await Promise.all([
        api<CandleSummaryExt[]>('/data/candles/summary'),
        api<CollectorStatus>('/data/collector/status'),
      ]);
      setSummaries(s);
      setCollector(c);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to fetch data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);
  useEffect(() => {
    const iv = setInterval(fetchAll, 30_000);
    return () => clearInterval(iv);
  }, [fetchAll]);

  // Derive unique symbols and timeframes for dropdowns
  const uniqueSymbols = [...new Set(summaries.map((s) => s.symbol))].sort();
  const uniqueTimeframes = [...new Set(summaries.map((s) => s.timeframe))].sort();

  // Set default gap checker values once data loads
  useEffect(() => {
    if (uniqueSymbols.length > 0 && !gapSymbol) setGapSymbol(uniqueSymbols[0]);
    if (uniqueTimeframes.length > 0 && !gapTf) setGapTf(uniqueTimeframes[0]);
  }, [uniqueSymbols, uniqueTimeframes, gapSymbol, gapTf]);

  const handleCheckGaps = async () => {
    if (!gapSymbol || !gapTf) return;
    setGapLoading(true);
    setGapError(null);
    setGapResult(null);
    setGapExpanded(false);
    try {
      const res = await api<GapResult>(
        `/data/candles/check-gaps?symbol=${encodeURIComponent(gapSymbol)}&timeframe=${gapTf}`,
      );
      setGapResult(res);
    } catch (err: unknown) {
      setGapError(err instanceof Error ? err.message : 'Gap check failed');
    } finally {
      setGapLoading(false);
    }
  };

  // Summary stats
  const totalCandles = summaries.reduce((a, s) => a + (s.count ?? 0), 0);
  const totalSymbols = uniqueSymbols.length;
  const totalTimeframes = uniqueTimeframes.length;
  const dbStatus = error ? 'Error' : 'Connected';
  const collectorStatus = collector?.running ? 'Running' : 'Stopped';

  if (loading) return <p className="text-gray-500 text-sm py-8 text-center">Loading data overview...</p>;

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
        <StatCard label="Total Candles" value={totalCandles.toLocaleString()} accent="text-[#00bfff]" />
        <StatCard label="Symbols" value={totalSymbols} />
        <StatCard label="Timeframes" value={totalTimeframes} />
        <StatCard
          label="DB Status"
          value={dbStatus}
          accent={dbStatus === 'Connected' ? 'text-[#00ff88]' : 'text-[#ff4444]'}
        />
        <StatCard
          label="Collector"
          value={collectorStatus}
          accent={collector?.running ? 'text-[#00ff88]' : 'text-gray-400'}
        />
      </div>

      {error && (
        <div className="bg-[#ff4444]/5 border border-[#ff4444]/20 rounded-xl p-4 text-[#ff4444] text-sm">
          {error}
        </div>
      )}

      {/* Candle Series Overview */}
      <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5 space-y-4">
        <h3 className="text-white text-sm font-semibold">Candle Series Overview</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 text-left border-b border-[#1e1e2e]">
                <th className="pb-2 pr-3 font-medium">Symbol</th>
                <th className="pb-2 pr-3 font-medium">TF</th>
                <th className="pb-2 pr-3 font-medium text-right">Candles</th>
                <th className="pb-2 pr-3 font-medium">From</th>
                <th className="pb-2 pr-3 font-medium">To</th>
                <th className="pb-2 pr-3 font-medium text-right">Days</th>
                <th className="pb-2 pr-3 font-medium">Last Checked</th>
                <th className="pb-2 pr-3 font-medium">Data Changed</th>
                <th className="pb-2 font-medium">Interval</th>
              </tr>
            </thead>
            <tbody>
              {summaries.length === 0 ? (
                <tr>
                  <td colSpan={9} className="text-gray-500 text-center py-8">No candle data found.</td>
                </tr>
              ) : (
                summaries.map((s, i) => {
                  const lastChecked = relativeTime(s.last_checked);
                  const dataChanged = relativeTime(s.data_changed);
                  return (
                    <tr key={`${s.symbol}-${s.timeframe}-${i}`} className="border-b border-[#1e1e2e]/50 hover:bg-[#0a0a0f]/50">
                      <td className="py-2 pr-3 text-white font-medium">{s.symbol}</td>
                      <td className="py-2 pr-3 text-gray-400">{s.timeframe}</td>
                      <td className="py-2 pr-3 text-right font-mono text-gray-300">{s.count?.toLocaleString() ?? '-'}</td>
                      <td className="py-2 pr-3 text-gray-400">{fmtDate(s.start)}</td>
                      <td className="py-2 pr-3 text-gray-400">{fmtDate(s.end)}</td>
                      <td className="py-2 pr-3 text-right font-mono text-gray-300">{daysBetween(s.start, s.end)}</td>
                      <td className={`py-2 pr-3 ${lastChecked.color}`}>{lastChecked.text}</td>
                      <td className={`py-2 pr-3 ${dataChanged.color}`}>{dataChanged.text}</td>
                      <td className="py-2 text-gray-400">{s.interval ?? '-'}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Gap Checker */}
      <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5 space-y-4">
        <h3 className="text-white text-sm font-semibold">Gap Checker</h3>
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="text-xs text-gray-500 block mb-1">Symbol</label>
            <select
              value={gapSymbol}
              onChange={(e) => setGapSymbol(e.target.value)}
              className="bg-[#0a0a0f] border border-[#1e1e2e] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#00bfff]/50 min-w-[160px]"
            >
              {uniqueSymbols.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Timeframe</label>
            <select
              value={gapTf}
              onChange={(e) => setGapTf(e.target.value)}
              className="bg-[#0a0a0f] border border-[#1e1e2e] rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-[#00bfff]/50 min-w-[100px]"
            >
              {uniqueTimeframes.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
          <button
            onClick={handleCheckGaps}
            disabled={gapLoading}
            className="px-4 py-2 bg-[#00bfff]/10 text-[#00bfff] rounded-lg text-sm font-medium hover:bg-[#00bfff]/20 transition-colors disabled:opacity-50"
          >
            {gapLoading ? 'Checking...' : 'Run Check'}
          </button>
        </div>

        {gapError && (
          <p className="text-[#ff4444] text-xs">{gapError}</p>
        )}

        {gapResult && (
          <div className="space-y-3">
            {/* Gap result summary */}
            <div className="flex flex-wrap gap-4 items-center">
              <span className={`px-2 py-0.5 rounded text-xs font-medium uppercase ${
                gapResult.gaps.length === 0
                  ? 'bg-[#00ff88]/10 text-[#00ff88]'
                  : 'bg-[#ff9800]/10 text-[#ff9800]'
              }`}>
                {gapResult.gaps.length === 0 ? 'No Gaps' : `${gapResult.gaps.length} Gap${gapResult.gaps.length > 1 ? 's' : ''}`}
              </span>
              {(() => {
                const match = summaries.find(
                  (s) => s.symbol === gapResult.symbol && s.timeframe === gapResult.timeframe,
                );
                const totalMissing = gapResult.gaps.reduce((a, g) => a + g.missing, 0);
                const totalCount = match?.count ?? 0;
                const coverage = totalCount > 0
                  ? (((totalCount - totalMissing) / totalCount) * 100).toFixed(1)
                  : '-';
                return (
                  <>
                    <span className="text-xs text-gray-500">
                      Candles: <span className="text-gray-300 font-mono">{totalCount.toLocaleString()}</span>
                    </span>
                    <span className="text-xs text-gray-500">
                      Coverage: <span className={`font-mono ${
                        coverage !== '-' && parseFloat(coverage) >= 99 ? 'text-[#00ff88]'
                          : coverage !== '-' && parseFloat(coverage) >= 95 ? 'text-[#ff9800]'
                          : 'text-[#ff4444]'
                      }`}>{coverage}%</span>
                    </span>
                  </>
                );
              })()}
            </div>

            {/* Expandable gap details */}
            {gapResult.gaps.length > 0 && (
              <>
                <button
                  onClick={() => setGapExpanded(!gapExpanded)}
                  className="text-xs text-[#00bfff] hover:text-[#00bfff]/80 flex items-center gap-1"
                >
                  <span className={`transition-transform ${gapExpanded ? 'rotate-90' : ''}`}>&#9654;</span>
                  Gap Details ({gapResult.gaps.length})
                </button>

                {gapExpanded && (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-gray-500 text-left border-b border-[#1e1e2e]">
                          <th className="pb-2 pr-3 font-medium">#</th>
                          <th className="pb-2 pr-3 font-medium">Gap Start</th>
                          <th className="pb-2 pr-3 font-medium">Gap End</th>
                          <th className="pb-2 pr-3 font-medium text-right">Missing Candles</th>
                        </tr>
                      </thead>
                      <tbody>
                        {gapResult.gaps.map((g, i) => (
                          <tr key={i} className="border-b border-[#1e1e2e]/50">
                            <td className="py-1.5 pr-3 text-gray-500">{i + 1}</td>
                            <td className="py-1.5 pr-3 text-gray-300 font-mono">{g.start}</td>
                            <td className="py-1.5 pr-3 text-gray-300 font-mono">{g.end}</td>
                            <td className="py-1.5 pr-3 text-right font-mono text-[#ff9800]">{g.missing}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* Collector info */}
      {collector && (
        <div className="bg-[#12121a] border border-[#1e1e2e] rounded-xl p-5 space-y-3">
          <h3 className="text-white text-sm font-semibold">Collector Details</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
            <div>
              <p className="text-gray-500 mb-0.5">Status</p>
              <p className={collector.running ? 'text-[#00ff88]' : 'text-gray-400'}>
                {collector.running ? 'Running' : 'Stopped'}
              </p>
            </div>
            <div>
              <p className="text-gray-500 mb-0.5">Symbols</p>
              <p className="text-gray-300">{collector.symbols?.length ?? 0}</p>
            </div>
            <div>
              <p className="text-gray-500 mb-0.5">Timeframes</p>
              <p className="text-gray-300">{collector.timeframes?.join(', ') ?? '-'}</p>
            </div>
            <div>
              <p className="text-gray-500 mb-0.5">Last Update</p>
              {(() => {
                const rt = relativeTime(collector.last_update);
                return <p className={rt.color}>{rt.text}</p>;
              })()}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
