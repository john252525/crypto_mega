// ---------------------------------------------------------------------------
// Formatting utilities for prices, PnL, timestamps
// ---------------------------------------------------------------------------

/**
 * Format a PnL percentage with a sign prefix.
 * Example: fmtPnl(1.234) -> "+1.23%", fmtPnl(-0.5) -> "-0.50%"
 */
export function fmtPnl(pct: number): string {
  const sign = pct >= 0 ? "+" : "";
  return `${sign}${pct.toFixed(2)}%`;
}

/**
 * Format a price with sensible decimal places.
 * - >= 1000     -> 2 decimals  (65432.10)
 * - >= 1        -> 4 decimals  (1.2345)
 * - >= 0.01     -> 6 decimals  (0.012345)
 * - < 0.01      -> 8 decimals  (0.00001234)
 */
export function fmtPrice(price: number): string {
  const abs = Math.abs(price);
  if (abs >= 1000) return price.toFixed(2);
  if (abs >= 1) return price.toFixed(4);
  if (abs >= 0.01) return price.toFixed(6);
  return price.toFixed(8);
}

/**
 * Format a unix timestamp (seconds) to a time string (HH:MM:SS).
 */
export function fmtTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString("en-US", { hour12: false });
}

/**
 * Format an ISO datetime string to a readable date.
 * Example: "2024-03-15T10:30:00" -> "Mar 15, 2024 10:30"
 */
export function fmtDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/**
 * Format an ISO datetime string to a relative time string.
 * Examples: "5m ago", "2h ago", "3d ago"
 */
export function fmtRelTime(iso: string): string {
  const now = Date.now();
  const then = new Date(iso).getTime();
  const diffSec = Math.max(0, Math.floor((now - then) / 1000));

  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  const diffDay = Math.floor(diffHr / 24);
  return `${diffDay}d ago`;
}

/**
 * Return a Tailwind text-color class based on whether the value is
 * positive (green), negative (red), or zero (gray).
 */
export function pnlColor(val: number): string {
  if (val > 0) return "text-green-400";
  if (val < 0) return "text-red-400";
  return "text-gray-400";
}
