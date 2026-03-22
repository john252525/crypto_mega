'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import { api } from '@/lib/api';
import { fmtPrice, fmtTime } from '@/lib/format';
import type { Signal } from '@/lib/types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Candle {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface SignalDetailModalProps {
  signalId: string;
  onClose: () => void;
}

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
      <div className="w-24 h-1.5 bg-[#1e1e2e] rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400">{pct.toFixed(0)}%</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SVG Candle Chart
// ---------------------------------------------------------------------------

function CandleChart({
  candles,
  entryPrice,
  sl,
  tp,
}: {
  candles: Candle[];
  entryPrice: number;
  sl: number | null;
  tp: number | null;
}) {
  if (!candles || candles.length === 0) {
    return (
      <div className="flex items-center justify-center text-gray-600 text-xs h-[200px]">
        No candle data
      </div>
    );
  }

  const svgWidth = 700;
  const svgHeight = 220;
  const pad = { top: 16, bottom: 16, left: 60, right: 16 };
  const chartW = svgWidth - pad.left - pad.right;
  const chartH = svgHeight - pad.top - pad.bottom;

  // Price range
  const allPrices: number[] = [];
  for (const c of candles) {
    allPrices.push(c.high, c.low);
  }
  if (entryPrice != null) allPrices.push(entryPrice);
  if (sl != null) allPrices.push(sl);
  if (tp != null) allPrices.push(tp);

  const minP = Math.min(...allPrices);
  const maxP = Math.max(...allPrices);
  const range = maxP - minP || 1;

  const priceToY = (p: number) => pad.top + ((maxP - p) / range) * chartH;

  const candleCount = candles.length;
  const candleW = chartW / candleCount;
  const bodyW = Math.max(candleW * 0.6, 1);

  return (
    <svg
      width="100%"
      viewBox={`0 0 ${svgWidth} ${svgHeight}`}
      className="rounded-lg bg-[#0a0a0f]"
    >
      {/* Grid lines */}
      {[0.2, 0.4, 0.6, 0.8].map((frac) => {
        const price = minP + range * frac;
        const y = priceToY(price);
        return (
          <g key={`grid-${frac}`}>
            <line x1={pad.left} y1={y} x2={svgWidth - pad.right} y2={y} stroke="#1e1e2e" strokeWidth={0.5} />
            <text x={pad.left - 4} y={y + 3} textAnchor="end" fill="#555" fontSize={8} fontFamily="monospace">
              {fmtPrice(price)}
            </text>
          </g>
        );
      })}

      {/* Candlesticks */}
      {candles.map((c, i) => {
        const x = pad.left + i * candleW;
        const cx = x + candleW / 2;
        const isUp = c.close >= c.open;
        const color = isUp ? '#00ff88' : '#ff4444';
        const wickTop = priceToY(c.high);
        const wickBot = priceToY(c.low);
        const bodyTop = priceToY(Math.max(c.open, c.close));
        const bodyBot = priceToY(Math.min(c.open, c.close));
        const bh = Math.max(bodyBot - bodyTop, 0.5);
        return (
          <g key={`c-${i}`}>
            <line x1={cx} y1={wickTop} x2={cx} y2={wickBot} stroke={color} strokeWidth={0.8} />
            <rect x={cx - bodyW / 2} y={bodyTop} width={bodyW} height={bh} fill={color} opacity={0.9} />
          </g>
        );
      })}

      {/* Entry line (blue dashed) */}
      {entryPrice != null && (
        <g>
          <line
            x1={pad.left}
            y1={priceToY(entryPrice)}
            x2={svgWidth - pad.right}
            y2={priceToY(entryPrice)}
            stroke="#00bfff"
            strokeWidth={1}
            strokeDasharray="6,3"
          />
          <text
            x={svgWidth - pad.right + 2}
            y={priceToY(entryPrice) + 3}
            fill="#00bfff"
            fontSize={8}
            fontFamily="monospace"
          >
            Entry
          </text>
        </g>
      )}

      {/* SL line (red dashed) */}
      {sl != null && (
        <g>
          <line
            x1={pad.left}
            y1={priceToY(sl)}
            x2={svgWidth - pad.right}
            y2={priceToY(sl)}
            stroke="#ff4444"
            strokeWidth={1}
            strokeDasharray="6,3"
          />
          <text
            x={svgWidth - pad.right + 2}
            y={priceToY(sl) + 3}
            fill="#ff4444"
            fontSize={8}
            fontFamily="monospace"
          >
            SL
          </text>
        </g>
      )}

      {/* TP line (green dashed) */}
      {tp != null && (
        <g>
          <line
            x1={pad.left}
            y1={priceToY(tp)}
            x2={svgWidth - pad.right}
            y2={priceToY(tp)}
            stroke="#00ff88"
            strokeWidth={1}
            strokeDasharray="6,3"
          />
          <text
            x={svgWidth - pad.right + 2}
            y={priceToY(tp) + 3}
            fill="#00ff88"
            fontSize={8}
            fontFamily="monospace"
          >
            TP
          </text>
        </g>
      )}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// SignalDetailModal
// ---------------------------------------------------------------------------

export default function SignalDetailModal({ signalId, onClose }: SignalDetailModalProps) {
  const [signal, setSignal] = useState<Signal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await api<Signal>(`/paper/signal/${signalId}`);
        setSignal(data);
        setError(null);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to fetch signal detail');
      } finally {
        setLoading(false);
      }
    })();
  }, [signalId]);

  // Escape key
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Prevent body scroll
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  const handleOverlayClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === overlayRef.current) onClose();
    },
    [onClose],
  );

  // Extract metadata fields
  const reason = signal?.metadata?.reason as string | undefined;
  const candlesRaw = signal?.metadata?.candles as Candle[] | undefined;
  const candles = Array.isArray(candlesRaw) ? candlesRaw : [];
  const indicatorKeys = signal
    ? Object.keys(signal.metadata).filter((k) => k !== 'reason' && k !== 'candles')
    : [];

  return (
    <div
      ref={overlayRef}
      onClick={handleOverlayClick}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
    >
      <div className="w-full max-w-[760px] max-h-[85vh] overflow-y-auto bg-[#12121a] border border-[#1e1e2e] rounded-lg shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-[#1e1e2e]">
          <h2 className="text-sm font-semibold text-gray-200">Signal Detail</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-gray-300 text-xs transition-colors"
          >
            [ESC]
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-5">
          {loading && (
            <div className="text-center text-gray-500 text-sm py-8">Loading signal...</div>
          )}

          {error && (
            <div className="bg-[#ff4444]/10 border border-[#ff4444]/30 text-[#ff4444] rounded-lg px-4 py-3 text-sm">
              {error}
            </div>
          )}

          {signal && !loading && (
            <>
              {/* (a) Header: direction + symbol + price */}
              <div className="flex items-center gap-3">
                {directionBadge(signal.direction)}
                <span className="text-[#00bfff] font-semibold text-lg">{signal.symbol}</span>
                <span className="text-gray-300 font-mono text-lg">{fmtPrice(signal.price)}</span>
              </div>

              {/* (b) Strategy info + time + strength */}
              <div className="bg-[#0a0a0f] border border-[#1e1e2e] rounded-lg p-4 flex flex-wrap gap-x-8 gap-y-2">
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider">Strategy</p>
                  <p className="text-sm text-gray-200">{signal.strategy_name}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider">Time</p>
                  <p className="text-sm text-gray-300 font-mono">{fmtTime(signal.timestamp)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider">Strength</p>
                  {strengthBar(signal.strength)}
                </div>
              </div>

              {/* (c) Price levels */}
              <div className="grid grid-cols-3 gap-3">
                <div className="bg-[#0a0a0f] border border-[#1e1e2e] rounded-lg p-3">
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Entry</p>
                  <p className="text-sm text-[#00bfff] font-mono font-medium">{fmtPrice(signal.price)}</p>
                </div>
                <div className="bg-[#0a0a0f] border border-[#1e1e2e] rounded-lg p-3">
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Stop Loss</p>
                  <p className="text-sm text-[#ff4444] font-mono font-medium">
                    {signal.stop_loss != null ? fmtPrice(signal.stop_loss) : '-'}
                  </p>
                </div>
                <div className="bg-[#0a0a0f] border border-[#1e1e2e] rounded-lg p-3">
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Take Profit</p>
                  <p className="text-sm text-[#00ff88] font-mono font-medium">
                    {signal.take_profit != null ? fmtPrice(signal.take_profit) : '-'}
                  </p>
                </div>
              </div>

              {/* (d) Signal Reasoning */}
              {reason && (
                <div className="border-l-2 border-[#00bfff] bg-[#0a0a0f] rounded-r-lg p-4">
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Signal Reasoning</p>
                  <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">{reason}</p>
                </div>
              )}

              {/* (e) Indicator values table */}
              {indicatorKeys.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Indicator Values</p>
                  <div className="bg-[#0a0a0f] border border-[#1e1e2e] rounded-lg overflow-hidden">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-gray-500 text-xs uppercase tracking-wider border-b border-[#1e1e2e]">
                          <th className="text-left px-4 py-2">Indicator</th>
                          <th className="text-right px-4 py-2">Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        {indicatorKeys.map((key) => (
                          <tr key={key} className="border-b border-[#1e1e2e]/50 last:border-0">
                            <td className="px-4 py-2 text-gray-400">{key}</td>
                            <td className="px-4 py-2 text-right text-gray-300 font-mono">
                              {typeof signal.metadata[key] === 'number'
                                ? (signal.metadata[key] as number).toFixed(4)
                                : String(signal.metadata[key])}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* (f) Candle chart */}
              {candles.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Price Chart</p>
                  <CandleChart
                    candles={candles}
                    entryPrice={signal.price}
                    sl={signal.stop_loss}
                    tp={signal.take_profit}
                  />
                </div>
              )}

              {/* (g) Candle table */}
              {candles.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">Candle Data</p>
                  <div className="bg-[#0a0a0f] border border-[#1e1e2e] rounded-lg overflow-hidden overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-gray-500 uppercase tracking-wider border-b border-[#1e1e2e]">
                          <th className="text-left px-3 py-2">Time</th>
                          <th className="text-right px-3 py-2">Open</th>
                          <th className="text-right px-3 py-2">High</th>
                          <th className="text-right px-3 py-2">Low</th>
                          <th className="text-right px-3 py-2">Close</th>
                          <th className="text-right px-3 py-2">Volume</th>
                          <th className="text-right px-3 py-2">Change %</th>
                        </tr>
                      </thead>
                      <tbody>
                        {candles.map((c, i) => {
                          const changePct = c.open !== 0 ? ((c.close - c.open) / c.open) * 100 : 0;
                          const changeColor = changePct >= 0 ? 'text-[#00ff88]' : 'text-[#ff4444]';
                          return (
                            <tr
                              key={i}
                              className="border-b border-[#1e1e2e]/50 last:border-0"
                            >
                              <td className="px-3 py-1.5 text-gray-500 font-mono">
                                {fmtTime(c.timestamp)}
                              </td>
                              <td className="px-3 py-1.5 text-right text-gray-300 font-mono">
                                {fmtPrice(c.open)}
                              </td>
                              <td className="px-3 py-1.5 text-right text-gray-300 font-mono">
                                {fmtPrice(c.high)}
                              </td>
                              <td className="px-3 py-1.5 text-right text-gray-300 font-mono">
                                {fmtPrice(c.low)}
                              </td>
                              <td className="px-3 py-1.5 text-right text-gray-300 font-mono">
                                {fmtPrice(c.close)}
                              </td>
                              <td className="px-3 py-1.5 text-right text-gray-400 font-mono">
                                {c.volume.toLocaleString()}
                              </td>
                              <td className={`px-3 py-1.5 text-right font-mono ${changeColor}`}>
                                {changePct >= 0 ? '+' : ''}
                                {changePct.toFixed(2)}%
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
