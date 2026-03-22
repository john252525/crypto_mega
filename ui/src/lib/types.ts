// ---------------------------------------------------------------------------
// TypeScript interfaces mirroring the Python data shapes from
// crypto_mega/utils/types.py and crypto_mega/paper/tracker.py
// ---------------------------------------------------------------------------

/** Signal direction — matches Python SignalDirection enum values. */
export type SignalDirection = "long" | "short" | "close" | "hold";

/** Order type — matches Python OrderType enum values. */
export type OrderType = "market" | "limit" | "stop_loss" | "take_profit";

/** Strategy runtime status. */
export type StrategyStatus =
  | "pending"
  | "running"
  | "paused"
  | "stopped"
  | "error";

/** Candle timeframe strings. */
export type TimeFrame = "1m" | "5m" | "15m" | "30m" | "1h" | "4h" | "1d" | "1w";

// ---------------------------------------------------------------------------
// Signal
// ---------------------------------------------------------------------------

export interface Signal {
  id: string;
  strategy_id: string;
  strategy_name: string;
  symbol: string;
  direction: SignalDirection;
  strength: number;
  price: number;
  stop_loss: number | null;
  take_profit: number | null;
  metadata: Record<string, unknown>;
  timestamp: number; // unix epoch seconds
}

// ---------------------------------------------------------------------------
// Positions
// ---------------------------------------------------------------------------

/** Open paper position (returned by /paper/positions/open). */
export interface OpenPosition {
  id: string;
  strategy_id: string;
  strategy_name: string;
  symbol: string;
  direction: SignalDirection;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  stop_loss: number | null;
  take_profit: number | null;
  strength: number;
  opened_at: string; // ISO datetime
  signal_id: string;
  metadata: Record<string, unknown>;
}

/** Closed paper position (returned by /paper/positions/closed). */
export interface ClosedPosition {
  id: string;
  strategy_id: string;
  strategy_name: string;
  symbol: string;
  direction: SignalDirection;
  entry_price: number;
  exit_price: number | null;
  realized_pnl: number;
  realized_pnl_pct: number;
  close_reason: string; // "sl" | "tp" | "signal" | "manual" | "timeout"
  opened_at: string;
  closed_at: string;
  stop_loss: number | null;
  take_profit: number | null;
  strength: number;
  signal_id: string;
  metadata: Record<string, unknown>;
}

/** Union of open and closed position shapes. */
export type Position = OpenPosition | ClosedPosition;

// ---------------------------------------------------------------------------
// Leaderboard
// ---------------------------------------------------------------------------

export interface LeaderboardEntry {
  strategy_id: string;
  strategy_name: string;
  total_signals: number;
  open_positions: number;
  closed_positions: number;
  wins: number;
  losses: number;
  total_pnl: number;
  total_pnl_pct: number;
  unrealized_pnl: number;
  max_drawdown: number;
  best_trade_pnl_pct: number;
  worst_trade_pnl_pct: number;
  avg_trade_pnl_pct: number;
  win_rate: number;
  profit_factor: number;
  sharpe_ratio: number;
  avg_hold_time_min: number;
  last_signal_at: number;
  promoted: boolean;
  equity_curve: number[];
}

// ---------------------------------------------------------------------------
// Health / Risk / Status
// ---------------------------------------------------------------------------

export interface HealthStatus {
  engine_running: boolean;
  strategies_running: number;
  exchange: string;
  db: boolean;
  data_status: string;
  data_age_sec: number;
  alerts: string[];
}

export interface RiskStatus {
  equity: number;
  drawdown_pct: number;
  kill_switch: boolean;
  daily_trades: number;
  open_positions: number;
}

export interface MonitorStats {
  total_strategies: number;
  running_strategies: number;
  total_signals: number;
  open_positions: number;
  closed_positions: number;
  total_pnl: number;
  uptime: number;
}

// ---------------------------------------------------------------------------
// Strategies
// ---------------------------------------------------------------------------

export interface StrategyInfo {
  id: string;
  name: string;
  description: string;
  symbols: string[];
  timeframes: TimeFrame[];
  parameters: Record<string, unknown>;
  priority: number;
  auto_execute: boolean;
  max_signals_per_hour: number;
  status: StrategyStatus;
}

export interface StrategyTemplate {
  name: string;
  description: string;
  code: string;
}

// ---------------------------------------------------------------------------
// Explore
// ---------------------------------------------------------------------------

export interface ExploreStats {
  running: boolean;
  total_generated: number;
  total_promoted: number;
  queue_size: number;
}

export interface ExploreResult {
  strategy_id: string;
  strategy_name: string;
  total_pnl_pct: number;
  win_rate: number;
  sharpe_ratio: number;
  profit_factor: number;
  closed_positions: number;
  promoted: boolean;
}

export interface ExplorePromotion {
  strategy_id: string;
  strategy_name: string;
  promoted_at: string;
  reason: string;
}

// ---------------------------------------------------------------------------
// Data / Candles
// ---------------------------------------------------------------------------

export interface OHLCV {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CandleSeries {
  symbol: string;
  timeframe: TimeFrame;
  candles: OHLCV[];
}

export interface CandleSummary {
  symbol: string;
  timeframe: string;
  count: number;
  start: string;
  end: string;
}

export interface GapResult {
  symbol: string;
  timeframe: string;
  gaps: { start: string; end: string; missing: number }[];
}

export interface DataHealth {
  status: string;
  age_sec: number;
  symbols: number;
}

export interface CollectorStatus {
  running: boolean;
  symbols: string[];
  timeframes: string[];
  last_update: string;
}

// ---------------------------------------------------------------------------
// Execution
// ---------------------------------------------------------------------------

export interface PendingOrder {
  signal_id: string;
  strategy_id: string;
  symbol: string;
  direction: SignalDirection;
  price: number;
  strength: number;
  timestamp: number;
}

export interface TradeRecord {
  id: string;
  signal_id: string;
  strategy_id: string;
  symbol: string;
  direction: SignalDirection;
  entry_price: number;
  exit_price: number | null;
  quantity: number;
  pnl: number;
  pnl_pct: number;
  fees: number;
  opened_at: string;
  closed_at: string | null;
  exchange_order_id: string;
}

// ---------------------------------------------------------------------------
// Backtest
// ---------------------------------------------------------------------------

export interface BacktestTask {
  task_id: string;
  status: "pending" | "running" | "completed" | "error";
  progress: number;
  result: BacktestResult | null;
}

export interface BacktestResult {
  total_trades: number;
  win_rate: number;
  total_pnl_pct: number;
  sharpe_ratio: number;
  max_drawdown: number;
  profit_factor: number;
  equity_curve: number[];
}

// ---------------------------------------------------------------------------
// Resources / Workers
// ---------------------------------------------------------------------------

export interface ResourceInfo {
  strategy_id: string;
  priority: number;
  cpu_pct: number;
  mem_mb: number;
}

export interface WorkerInfo {
  id: string;
  status: string;
  task: string;
  uptime: number;
}

// ---------------------------------------------------------------------------
// System
// ---------------------------------------------------------------------------

export interface SystemAlert {
  level: "info" | "warning" | "error" | "critical";
  message: string;
  timestamp: string;
}

export interface LogEntry {
  level: string;
  message: string;
  logger: string;
  timestamp: string;
}
