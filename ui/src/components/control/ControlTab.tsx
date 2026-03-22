'use client';

import { useState } from 'react';
import { post } from '@/lib/api';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const EXCHANGES = ['binance', 'bybit', 'okx', 'kucoin', 'gate'] as const;

// ---------------------------------------------------------------------------
// Shared card wrapper
// ---------------------------------------------------------------------------

function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg bg-[#12121a] border border-[#1e1e2e] p-5 flex flex-col gap-4">
      <h3 className="text-sm font-semibold text-white tracking-wide uppercase">
        {title}
      </h3>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Label helper
// ---------------------------------------------------------------------------

function Label({ text, children }: { text: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-gray-400">
      {text}
      {children}
    </label>
  );
}

// ---------------------------------------------------------------------------
// Shared styles
// ---------------------------------------------------------------------------

const inputCls =
  'bg-[#0a0a0f] border border-[#1e1e2e] text-gray-300 text-sm rounded px-2 py-1.5 w-full focus:outline-none focus:border-[#00bfff]';

const selectCls =
  'bg-[#0a0a0f] border border-[#1e1e2e] text-gray-300 text-sm rounded px-2 py-1.5 w-full focus:outline-none focus:border-[#00bfff]';

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ControlTab() {
  // Engine Control state
  const [engineExchange, setEngineExchange] = useState('binance');
  const [symbols, setSymbols] = useState('BTC/USDT,ETH/USDT');
  const [interval, setInterval_] = useState(60);
  const [engineMsg, setEngineMsg] = useState('');

  // Emergency state
  const [killMsg, setKillMsg] = useState('');

  // Exchange Connection state
  const [connExchange, setConnExchange] = useState('binance');
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');
  const [sandbox, setSandbox] = useState(true);
  const [connMsg, setConnMsg] = useState('');

  // Promote state
  const [promoteId, setPromoteId] = useState('');
  const [promoteMsg, setPromoteMsg] = useState('');

  // -----------------------------------------------------------------------
  // Engine handlers
  // -----------------------------------------------------------------------

  const startEngine = async () => {
    setEngineMsg('Starting...');
    try {
      const params = new URLSearchParams({
        interval: String(interval),
        symbols,
        exchange: engineExchange,
      });
      const res = await post<{ status: string }>(`/engine/start?${params}`);
      setEngineMsg(res.status ?? 'Engine started');
    } catch (err: unknown) {
      setEngineMsg(`Error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const stopEngine = async () => {
    setEngineMsg('Stopping...');
    try {
      const res = await post<{ status: string }>('/engine/stop');
      setEngineMsg(res.status ?? 'Engine stopped');
    } catch (err: unknown) {
      setEngineMsg(`Error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  // -----------------------------------------------------------------------
  // Kill switch handlers
  // -----------------------------------------------------------------------

  const activateKill = async () => {
    setKillMsg('Activating...');
    try {
      const res = await post<{ status: string }>('/risk/kill-switch/activate');
      setKillMsg(res.status ?? 'Kill switch activated');
    } catch (err: unknown) {
      setKillMsg(`Error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  const deactivateKill = async () => {
    setKillMsg('Deactivating...');
    try {
      const res = await post<{ status: string }>('/risk/kill-switch/deactivate');
      setKillMsg(res.status ?? 'Kill switch deactivated');
    } catch (err: unknown) {
      setKillMsg(`Error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  // -----------------------------------------------------------------------
  // Exchange connection handler
  // -----------------------------------------------------------------------

  const connectExchange = async () => {
    setConnMsg('Connecting...');
    try {
      const res = await post<{ status: string }>('/exchange/connect', {
        exchange: connExchange,
        api_key: apiKey,
        api_secret: apiSecret,
        sandbox,
      });
      setConnMsg(res.status ?? 'Connected');
    } catch (err: unknown) {
      setConnMsg(`Error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  // -----------------------------------------------------------------------
  // Promote handler
  // -----------------------------------------------------------------------

  const promoteStrategy = async () => {
    if (!promoteId.trim()) {
      setPromoteMsg('Please enter a strategy ID');
      return;
    }
    setPromoteMsg('Promoting...');
    try {
      const res = await post<{ status: string }>(
        `/paper/promote/${promoteId.trim()}`,
      );
      setPromoteMsg(res.status ?? 'Promoted successfully');
    } catch (err: unknown) {
      setPromoteMsg(`Error: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* ---- Engine Control ---- */}
      <Card title="Engine Control">
        <Label text="Exchange">
          <select
            value={engineExchange}
            onChange={(e) => setEngineExchange(e.target.value)}
            className={selectCls}
          >
            {EXCHANGES.map((ex) => (
              <option key={ex} value={ex}>
                {ex}
              </option>
            ))}
          </select>
        </Label>

        <Label text="Symbols (comma-separated)">
          <input
            type="text"
            value={symbols}
            onChange={(e) => setSymbols(e.target.value)}
            className={inputCls}
          />
        </Label>

        <Label text="Interval (seconds)">
          <input
            type="number"
            value={interval}
            onChange={(e) => setInterval_(Number(e.target.value))}
            min={1}
            className={inputCls}
          />
        </Label>

        <div className="flex gap-2 mt-1">
          <button
            onClick={startEngine}
            className="flex-1 py-2 rounded text-sm font-semibold bg-[#00ff88]/10 text-[#00ff88] border border-[#00ff88]/30 hover:bg-[#00ff88]/20 transition-colors"
          >
            Start Signal Engine
          </button>
          <button
            onClick={stopEngine}
            className="flex-1 py-2 rounded text-sm font-semibold bg-[#ff4444]/10 text-[#ff4444] border border-[#ff4444]/30 hover:bg-[#ff4444]/20 transition-colors"
          >
            Stop Engine
          </button>
        </div>

        {engineMsg && (
          <p className="text-xs text-gray-400 bg-[#0a0a0f] rounded px-2 py-1.5 break-all">
            {engineMsg}
          </p>
        )}
      </Card>

      {/* ---- Emergency Controls ---- */}
      <Card title="Emergency Controls">
        <p className="text-xs text-gray-500">
          The kill switch immediately halts all trading, cancels pending orders,
          and prevents new positions from being opened.
        </p>
        <div className="flex flex-col gap-2 mt-1">
          <button
            onClick={activateKill}
            className="w-full py-3 rounded text-sm font-bold uppercase tracking-wider bg-[#ff4444]/20 text-[#ff4444] border-2 border-[#ff4444]/50 hover:bg-[#ff4444]/30 transition-colors"
          >
            ACTIVATE KILL SWITCH
          </button>
          <button
            onClick={deactivateKill}
            className="w-full py-2 rounded text-sm font-medium bg-[#1e1e2e] text-gray-400 border border-[#1e1e2e] hover:text-white hover:bg-[#2a2a3a] transition-colors"
          >
            Deactivate Kill Switch
          </button>
        </div>

        {killMsg && (
          <p className="text-xs text-gray-400 bg-[#0a0a0f] rounded px-2 py-1.5 break-all">
            {killMsg}
          </p>
        )}
      </Card>

      {/* ---- Exchange Connection ---- */}
      <Card title="Exchange Connection">
        <Label text="Exchange">
          <select
            value={connExchange}
            onChange={(e) => setConnExchange(e.target.value)}
            className={selectCls}
          >
            {EXCHANGES.map((ex) => (
              <option key={ex} value={ex}>
                {ex}
              </option>
            ))}
          </select>
        </Label>

        <Label text="API Key">
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="Enter API key"
            className={inputCls}
          />
        </Label>

        <Label text="API Secret">
          <input
            type="password"
            value={apiSecret}
            onChange={(e) => setApiSecret(e.target.value)}
            placeholder="Enter API secret"
            className={inputCls}
          />
        </Label>

        <label className="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={sandbox}
            onChange={(e) => setSandbox(e.target.checked)}
            className="accent-[#00bfff]"
          />
          Sandbox / Testnet mode
        </label>

        <button
          onClick={connectExchange}
          className="w-full py-2 rounded text-sm font-semibold bg-[#00bfff]/10 text-[#00bfff] border border-[#00bfff]/30 hover:bg-[#00bfff]/20 transition-colors"
        >
          Connect Exchange
        </button>

        {connMsg && (
          <p className="text-xs text-gray-400 bg-[#0a0a0f] rounded px-2 py-1.5 break-all">
            {connMsg}
          </p>
        )}
      </Card>

      {/* ---- Promote to Live Trading ---- */}
      <Card title="Promote to Live Trading">
        <p className="text-xs text-gray-500">
          Promote a paper-trading strategy to live trading. The strategy must have
          a positive track record and pass risk checks before it can be promoted.
          Once promoted, the strategy will begin executing real trades on the
          connected exchange.
        </p>

        <div className="flex gap-2 items-end">
          <Label text="Strategy ID">
            <input
              type="text"
              value={promoteId}
              onChange={(e) => setPromoteId(e.target.value)}
              placeholder="e.g. strat_abc123"
              className={inputCls}
            />
          </Label>
          <button
            onClick={promoteStrategy}
            className="shrink-0 px-4 py-1.5 rounded text-sm font-semibold bg-[#ff9800]/10 text-[#ff9800] border border-[#ff9800]/30 hover:bg-[#ff9800]/20 transition-colors"
          >
            Promote
          </button>
        </div>

        {promoteMsg && (
          <p className="text-xs text-gray-400 bg-[#0a0a0f] rounded px-2 py-1.5 break-all">
            {promoteMsg}
          </p>
        )}
      </Card>
    </div>
  );
}
