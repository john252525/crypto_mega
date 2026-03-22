'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { api } from '@/lib/api';
import type { LogEntry } from '@/lib/types';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_DOM_ENTRIES = 2000;
const MAX_MEMORY_ENTRIES = 5000;
const WS_RECONNECT_DELAY = 3000;

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: '#555555',
  INFO: '#8bc34a',
  WARNING: '#ff9800',
  ERROR: '#f44336',
  CRITICAL: '#ff0000',
};

const LEVEL_OPTIONS = ['All', 'DEBUG', 'INFO', 'WARNING', 'ERROR'] as const;

// ---------------------------------------------------------------------------
// Syntax highlighting for log messages
// ---------------------------------------------------------------------------

function highlightMessage(msg: string): React.ReactNode {
  // Split the message into tokens and apply highlighting rules.
  // We use a single regex that captures all patterns of interest.
  const regex =
    /(LONG|BUY|Paper OPEN|SHORT|SELL|Paper CLOSE|Signal:|[+-]?\d+\.\d+%?)/g;

  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(msg)) !== null) {
    // Push preceding plain text
    if (match.index > lastIndex) {
      parts.push(msg.slice(lastIndex, match.index));
    }

    const token = match[0];

    if (token === 'LONG' || token === 'BUY' || token === 'Paper OPEN') {
      parts.push(
        <span key={match.index} style={{ color: '#00ff88', fontWeight: 700 }}>
          {token}
        </span>,
      );
    } else if (token === 'SHORT' || token === 'SELL') {
      parts.push(
        <span key={match.index} style={{ color: '#ff4444', fontWeight: 700 }}>
          {token}
        </span>,
      );
    } else if (token === 'Paper CLOSE') {
      parts.push(
        <span key={match.index} style={{ color: '#ff9800', fontWeight: 700 }}>
          {token}
        </span>,
      );
    } else if (token === 'Signal:') {
      parts.push(
        <span key={match.index} style={{ color: '#00bfff', fontWeight: 700 }}>
          {token}
        </span>,
      );
    } else {
      // Numeric P&L value
      const num = parseFloat(token);
      if (!isNaN(num)) {
        parts.push(
          <span
            key={match.index}
            style={{ color: num >= 0 ? '#00ff88' : '#ff4444', fontWeight: 600 }}
          >
            {token}
          </span>,
        );
      } else {
        parts.push(token);
      }
    }

    lastIndex = match.index + token.length;
  }

  // Remaining tail
  if (lastIndex < msg.length) {
    parts.push(msg.slice(lastIndex));
  }

  return parts.length > 0 ? parts : msg;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function LogsTab() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const [levelFilter, setLevelFilter] = useState<string>('All');
  const [search, setSearch] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // -----------------------------------------------------------------------
  // Initial fetch
  // -----------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    api<LogEntry[]>('/logs?limit=500').then((data) => {
      if (!cancelled) setLogs(data);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  // -----------------------------------------------------------------------
  // WebSocket real-time streaming
  // -----------------------------------------------------------------------
  const connectWs = useCallback(() => {
    if (typeof window === 'undefined') return;
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${proto}://${location.host}/ws/logs`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const entry: LogEntry = JSON.parse(event.data);
        setLogs((prev) => {
          const next = [...prev, entry];
          if (next.length > MAX_MEMORY_ENTRIES) {
            return next.slice(next.length - MAX_MEMORY_ENTRIES);
          }
          return next;
        });
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      wsRef.current = null;
      reconnectTimer.current = setTimeout(connectWs, WS_RECONNECT_DELAY);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    connectWs();
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    };
  }, [connectWs]);

  // -----------------------------------------------------------------------
  // Auto-scroll
  // -----------------------------------------------------------------------
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  // -----------------------------------------------------------------------
  // Filtered + capped entries
  // -----------------------------------------------------------------------
  const filtered = useMemo(() => {
    let result = logs;
    if (levelFilter !== 'All') {
      result = result.filter((l) => l.level === levelFilter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter((l) => l.message.toLowerCase().includes(q));
    }
    // Cap DOM entries
    if (result.length > MAX_DOM_ENTRIES) {
      result = result.slice(result.length - MAX_DOM_ENTRIES);
    }
    return result;
  }, [logs, levelFilter, search]);

  // -----------------------------------------------------------------------
  // Handlers
  // -----------------------------------------------------------------------
  const handleClear = () => setLogs([]);

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------
  return (
    <div className="flex flex-col h-full gap-3">
      {/* Controls bar */}
      <div className="flex flex-wrap items-center gap-3 rounded-lg bg-[#12121a] border border-[#1e1e2e] px-4 py-2">
        {/* Auto-scroll */}
        <label className="flex items-center gap-1.5 text-sm text-gray-400 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
            className="accent-[#00ff88]"
          />
          Auto-scroll
        </label>

        {/* Level filter */}
        <select
          value={levelFilter}
          onChange={(e) => setLevelFilter(e.target.value)}
          className="bg-[#0a0a0f] border border-[#1e1e2e] text-gray-300 text-sm rounded px-2 py-1 focus:outline-none focus:border-[#00bfff]"
        >
          {LEVEL_OPTIONS.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>

        {/* Text search */}
        <input
          type="text"
          placeholder="Search logs..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="bg-[#0a0a0f] border border-[#1e1e2e] text-gray-300 text-sm rounded px-2 py-1 w-48 focus:outline-none focus:border-[#00bfff]"
        />

        {/* Clear */}
        <button
          onClick={handleClear}
          className="text-sm px-3 py-1 rounded bg-[#1e1e2e] text-gray-400 hover:text-white hover:bg-[#2a2a3a] transition-colors"
        >
          Clear
        </button>

        {/* Entry count */}
        <span className="ml-auto text-xs text-gray-500">
          {filtered.length} entries ({logs.length} in memory)
        </span>
      </div>

      {/* Log container */}
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto rounded-lg bg-[#0a0a0f] border border-[#1e1e2e] p-3 font-mono text-xs leading-5"
      >
        {filtered.length === 0 && (
          <div className="text-gray-600 text-center py-8">
            No log entries to display.
          </div>
        )}
        {filtered.map((entry, i) => {
          const levelColor = LEVEL_COLORS[entry.level] ?? '#888';
          const ts = entry.timestamp
            ? new Date(entry.timestamp).toLocaleTimeString()
            : '';
          return (
            <div key={i} className="whitespace-pre-wrap break-all">
              <span className="text-gray-500">{ts}</span>{' '}
              <span style={{ color: levelColor, fontWeight: 600 }}>
                [{entry.level}]
              </span>{' '}
              <span className="text-gray-300">
                {highlightMessage(entry.message)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
