// ---------------------------------------------------------------------------
// Shared constants: color maps, symbols, log levels
// ---------------------------------------------------------------------------

/** Strategy category -> Tailwind color class (bg / text). */
export const CATEGORY_COLORS: Record<string, string> = {
  trend: "text-green-400",
  "mean-reversion": "text-purple-400",
  momentum: "text-blue-400",
  breakout: "text-orange-400",
  scalping: "text-yellow-400",
  custom: "text-gray-400",
} as const;

/** Background variants for pills / badges. */
export const CATEGORY_BG: Record<string, string> = {
  trend: "bg-green-500/20 text-green-400",
  "mean-reversion": "bg-purple-500/20 text-purple-400",
  momentum: "bg-blue-500/20 text-blue-400",
  breakout: "bg-orange-500/20 text-orange-400",
  scalping: "bg-yellow-500/20 text-yellow-400",
  custom: "bg-gray-500/20 text-gray-400",
} as const;

/** Risk level color classes. */
export const RISK_COLORS: Record<string, string> = {
  low: "text-green-400",
  medium: "text-yellow-400",
  high: "text-red-400",
} as const;

/** Log levels and matching Tailwind text colors. */
export const LOG_LEVELS: Record<string, string> = {
  DEBUG: "text-gray-500",
  INFO: "text-blue-400",
  WARNING: "text-yellow-400",
  ERROR: "text-red-400",
  CRITICAL: "text-red-500 font-bold",
} as const;

/** Log level icons (plain text, no emoji). */
export const LOG_ICONS: Record<string, string> = {
  DEBUG: "[D]",
  INFO: "[I]",
  WARNING: "[W]",
  ERROR: "[E]",
  CRITICAL: "[!]",
} as const;

/** Top 20 crypto symbols for quick-select lists and default watchlists. */
export const TOP_SYMBOLS: string[] = [
  "BTC/USDT",
  "ETH/USDT",
  "BNB/USDT",
  "SOL/USDT",
  "XRP/USDT",
  "ADA/USDT",
  "DOGE/USDT",
  "AVAX/USDT",
  "DOT/USDT",
  "LINK/USDT",
  "MATIC/USDT",
  "UNI/USDT",
  "ATOM/USDT",
  "LTC/USDT",
  "FIL/USDT",
  "APT/USDT",
  "ARB/USDT",
  "OP/USDT",
  "NEAR/USDT",
  "SUI/USDT",
] as const;

/** Direction label colors. */
export const DIRECTION_COLORS: Record<string, string> = {
  long: "text-green-400",
  short: "text-red-400",
  close: "text-gray-400",
  hold: "text-gray-500",
} as const;

/** Close-reason readable labels. */
export const CLOSE_REASONS: Record<string, string> = {
  sl: "Stop Loss",
  tp: "Take Profit",
  signal: "Signal",
  manual: "Manual",
  timeout: "Timeout",
} as const;
