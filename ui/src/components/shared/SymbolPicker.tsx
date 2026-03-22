"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

// ---------------------------------------------------------------------------
// Offline fallback: top base currencies
// ---------------------------------------------------------------------------
const TOP_BASES = [
  "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "DOT", "LINK",
  "MATIC", "UNI", "ATOM", "LTC", "FIL", "APT", "ARB", "OP", "NEAR", "SUI",
];

const EXCHANGES = ["binance", "bybit", "okx", "kucoin", "gate"] as const;
type Exchange = (typeof EXCHANGES)[number];

const QUOTE_CURRENCIES = ["USDT", "BTC", "ETH", "BUSD", "USDC", "USD"] as const;

interface SymbolPickerProps {
  value: string[];
  onChange: (symbols: string[]) => void;
  defaultValue?: string[];
}

export default function SymbolPicker({
  value,
  onChange,
  defaultValue = [],
}: SymbolPickerProps) {
  const [exchange, setExchange] = useState<Exchange>("binance");
  const [allSymbols, setAllSymbols] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [manualInput, setManualInput] = useState("");
  const [activeQuote, setActiveQuote] = useState<string>("USDT");

  // Load symbols from exchange
  const loadSymbols = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const symbols = await api<string[]>(
        `/exchange/symbols?exchange=${exchange}`,
      );
      setAllSymbols(symbols.sort());
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load symbols",
      );
      // Fallback: generate common pairs offline
      const fallback = TOP_BASES.map((b) => `${b}/${activeQuote}`);
      setAllSymbols(fallback);
    } finally {
      setLoading(false);
    }
  }, [exchange, activeQuote]);

  // Group symbols by quote currency
  const quoteCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const sym of allSymbols) {
      const quote = sym.split("/")[1] || "OTHER";
      counts[quote] = (counts[quote] || 0) + 1;
    }
    return counts;
  }, [allSymbols]);

  // Filter symbols by active quote + search
  const filteredSymbols = useMemo(() => {
    let filtered = allSymbols.filter((sym) => {
      const quote = sym.split("/")[1];
      return quote === activeQuote;
    });

    if (search.trim()) {
      const q = search.trim().toUpperCase();
      filtered = filtered.filter((sym) => sym.toUpperCase().includes(q));
    }

    return filtered;
  }, [allSymbols, activeQuote, search]);

  // Handlers
  const toggleSymbol = useCallback(
    (sym: string) => {
      if (value.includes(sym)) {
        onChange(value.filter((s) => s !== sym));
      } else {
        onChange([...value, sym]);
      }
    },
    [value, onChange],
  );

  const selectVisible = useCallback(() => {
    const merged = new Set([...value, ...filteredSymbols]);
    onChange(Array.from(merged));
  }, [value, filteredSymbols, onChange]);

  const clearAll = useCallback(() => {
    onChange([]);
  }, [onChange]);

  const selectTop20 = useCallback(() => {
    const top = TOP_BASES.slice(0, 20).map((b) => `${b}/${activeQuote}`);
    const existing = top.filter(
      (sym) => allSymbols.includes(sym) || allSymbols.length === 0,
    );
    onChange(existing.length > 0 ? existing : top);
  }, [activeQuote, allSymbols, onChange]);

  const handleManualAdd = useCallback(() => {
    if (!manualInput.trim()) return;
    const newSymbols = manualInput
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter((s) => s.length > 0);
    const merged = new Set([...value, ...newSymbols]);
    onChange(Array.from(merged));
    setManualInput("");
  }, [manualInput, value, onChange]);

  // Set default value on mount
  useEffect(() => {
    if (value.length === 0 && defaultValue.length > 0) {
      onChange(defaultValue);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-3">
      {/* Manual input row */}
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={manualInput}
          onChange={(e) => setManualInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleManualAdd()}
          placeholder="BTC/USDT, ETH/USDT, ..."
          className="flex-1 px-2 py-1.5 bg-bg border border-border rounded text-xs
                     text-gray-200 placeholder-gray-600 focus:outline-none
                     focus:border-accent/50"
        />
        <button onClick={handleManualAdd} className="btn-primary text-xs">
          Add
        </button>
      </div>

      {/* Exchange selector + load */}
      <div className="flex items-center gap-2">
        <select
          value={exchange}
          onChange={(e) => setExchange(e.target.value as Exchange)}
          className="px-2 py-1.5 bg-bg border border-border rounded text-xs
                     text-gray-200 focus:outline-none focus:border-accent/50"
        >
          {EXCHANGES.map((ex) => (
            <option key={ex} value={ex}>
              {ex}
            </option>
          ))}
        </select>
        <button
          onClick={loadSymbols}
          disabled={loading}
          className="btn-primary text-xs"
        >
          {loading ? "Loading..." : "Load"}
        </button>
        {error && (
          <span className="text-xs text-danger">{error}</span>
        )}
      </div>

      {/* Quote currency tabs */}
      {allSymbols.length > 0 && (
        <div className="flex items-center gap-1 flex-wrap">
          {QUOTE_CURRENCIES.map((quote) => {
            const count = quoteCounts[quote] || 0;
            if (count === 0 && quote !== activeQuote) return null;
            return (
              <button
                key={quote}
                onClick={() => setActiveQuote(quote)}
                className={`px-2 py-1 rounded text-xs transition-colors ${
                  activeQuote === quote
                    ? "bg-accent/20 text-accent border border-accent/30"
                    : "bg-border/50 text-gray-400 border border-transparent hover:text-gray-200"
                }`}
              >
                {quote}
                <span className="ml-1 text-gray-600">({count})</span>
              </button>
            );
          })}
        </div>
      )}

      {/* Search filter */}
      {allSymbols.length > 0 && (
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter symbols..."
          className="w-full px-2 py-1.5 bg-bg border border-border rounded text-xs
                     text-gray-200 placeholder-gray-600 focus:outline-none
                     focus:border-accent/50"
        />
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-2">
        <button onClick={selectVisible} className="btn-secondary text-xs">
          Select visible
        </button>
        <button onClick={selectTop20} className="btn-secondary text-xs">
          Top 20
        </button>
        <button onClick={clearAll} className="btn-danger text-xs">
          Clear
        </button>
        <span className="ml-auto text-xs text-gray-500">
          {value.length} selected
        </span>
      </div>

      {/* Symbol chip grid */}
      {allSymbols.length > 0 && (
        <div className="max-h-48 overflow-y-auto border border-border rounded p-2">
          <div className="flex flex-wrap gap-1">
            {filteredSymbols.map((sym) => {
              const isSelected = value.includes(sym);
              return (
                <button
                  key={sym}
                  onClick={() => toggleSymbol(sym)}
                  className={`px-2 py-0.5 rounded text-xs transition-colors ${
                    isSelected
                      ? "bg-accent/20 text-accent border border-accent/40"
                      : "bg-bg text-gray-500 border border-border hover:text-gray-300 hover:border-gray-500"
                  }`}
                >
                  {sym.split("/")[0]}
                </button>
              );
            })}
            {filteredSymbols.length === 0 && (
              <span className="text-xs text-gray-600">
                No symbols match filter
              </span>
            )}
          </div>
        </div>
      )}

      {/* Selected symbols display */}
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {value.map((sym) => (
            <span
              key={sym}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded
                         bg-accent/10 text-accent text-xs border border-accent/20"
            >
              {sym}
              <button
                onClick={() => toggleSymbol(sym)}
                className="text-accent/50 hover:text-accent ml-0.5"
              >
                x
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
