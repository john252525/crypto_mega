// ---------------------------------------------------------------------------
// Typed API client for the crypto_mega backend (FastAPI)
// ---------------------------------------------------------------------------

import type {
  BacktestTask,
  CandleSeries,
  CandleSummary,
  CollectorStatus,
  ClosedPosition,
  DataHealth,
  ExplorePromotion,
  ExploreStats,
  GapResult,
  HealthStatus,
  LeaderboardEntry,
  LogEntry,
  MonitorStats,
  OpenPosition,
  PendingOrder,
  ResourceInfo,
  RiskStatus,
  Signal,
  StrategyInfo,
  StrategyTemplate,
  SystemAlert,
  TradeRecord,
  WorkerInfo,
} from "./types";

// Empty string means same-origin (production behind a reverse proxy).
// Override with NEXT_PUBLIC_API_BASE for local dev pointing at a different port.
export const API_BASE =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_BASE ?? "")
    : (process.env.NEXT_PUBLIC_API_BASE ?? "");

// ---------------------------------------------------------------------------
// Core fetch helpers
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  constructor(
    public status: number,
    public statusText: string,
    public body: unknown,
  ) {
    super(`API ${status}: ${statusText}`);
    this.name = "ApiError";
  }
}

/** Typed GET (or any method) fetch wrapper. */
export async function api<T>(
  path: string,
  opts?: RequestInit,
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...opts?.headers,
    },
  });
  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = await res.text();
    }
    throw new ApiError(res.status, res.statusText, body);
  }
  return res.json() as Promise<T>;
}

/** Typed POST wrapper. */
export async function post<T>(
  path: string,
  body?: unknown,
): Promise<T> {
  return api<T>(path, {
    method: "POST",
    body: body != null ? JSON.stringify(body) : undefined,
  });
}

// ---------------------------------------------------------------------------
// Paper endpoints
// ---------------------------------------------------------------------------

export function fetchLeaderboard(sortBy = "total_pnl_pct", limit = 50) {
  return api<LeaderboardEntry[]>(
    `/paper/leaderboard?sort_by=${sortBy}&limit=${limit}`,
  );
}

export function fetchOpenPositions(strategyId?: string) {
  const qs = strategyId ? `?strategy_id=${strategyId}` : "";
  return api<OpenPosition[]>(`/paper/positions/open${qs}`);
}

export function fetchClosedPositions(strategyId?: string, limit = 100) {
  const params = new URLSearchParams();
  if (strategyId) params.set("strategy_id", strategyId);
  params.set("limit", String(limit));
  return api<ClosedPosition[]>(`/paper/positions/closed?${params}`);
}

export function fetchSignals(limit = 100) {
  return api<Signal[]>(`/paper/signals?limit=${limit}`);
}

export function fetchSignalDetail(signalId: string) {
  return api<Signal>(`/paper/signal/${signalId}`);
}

export function fetchPositionDetail(positionId: string) {
  return api<OpenPosition | ClosedPosition>(`/paper/position/${positionId}`);
}

export function fetchStrategyStats(strategyId: string) {
  return api<LeaderboardEntry>(`/paper/stats/${strategyId}`);
}

export function promoteStrategy(strategyId: string) {
  return post<{ status: string }>(`/paper/promote/${strategyId}`);
}

// ---------------------------------------------------------------------------
// Strategy endpoints
// ---------------------------------------------------------------------------

export function fetchStrategies() {
  return api<StrategyInfo[]>("/strategies");
}

export function fetchStrategyTemplates() {
  return api<StrategyTemplate[]>("/strategies/templates");
}

export function loadStrategyCode(code: string, name?: string) {
  return post<{ status: string; strategy_id: string }>(
    "/strategies/load-code",
    { code, name },
  );
}

export function loadStrategyFile(path: string) {
  return post<{ status: string }>("/strategies/load-file", { path });
}

export function loadStrategyDirectory(path: string) {
  return post<{ status: string }>("/strategies/load-directory", { path });
}

export function pauseStrategy(strategyId: string) {
  return post<{ status: string }>(`/strategies/${strategyId}/pause`);
}

export function resumeStrategy(strategyId: string) {
  return post<{ status: string }>(`/strategies/${strategyId}/resume`);
}

// ---------------------------------------------------------------------------
// Engine
// ---------------------------------------------------------------------------

export function startEngine() {
  return post<{ status: string }>("/engine/start");
}

export function stopEngine() {
  return post<{ status: string }>("/engine/stop");
}

// ---------------------------------------------------------------------------
// Exchange
// ---------------------------------------------------------------------------

export function connectExchange(config: Record<string, unknown>) {
  return post<{ status: string }>("/exchange/connect", config);
}

export function fetchExchangeSymbols() {
  return api<string[]>("/exchange/symbols");
}

// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------

export function fetchCollectorStatus() {
  return api<CollectorStatus>("/data/collector/status");
}

export function fetchDataHealth() {
  return api<DataHealth>("/data/health");
}

export function fetchCandleSummary() {
  return api<CandleSummary[]>("/data/candles/summary");
}

export function fetchCandleGaps(symbol: string, timeframe: string) {
  return api<GapResult>(
    `/data/candles/check-gaps?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}`,
  );
}

export function fetchCandles(
  symbol: string,
  timeframe: string,
  limit = 500,
) {
  const params = new URLSearchParams({
    symbol,
    timeframe,
    limit: String(limit),
  });
  return api<CandleSeries>(`/data/candles/batch?${params}`);
}

// ---------------------------------------------------------------------------
// Monitor / Health / Risk
// ---------------------------------------------------------------------------

export function fetchMonitorStats() {
  return api<MonitorStats>("/monitor/stats");
}

export function fetchMonitorAlerts() {
  return api<SystemAlert[]>("/monitor/alerts");
}

export function fetchRisk() {
  return api<RiskStatus>("/risk");
}

export function activateKillSwitch() {
  return post<{ status: string }>("/risk/kill-switch/activate");
}

export function deactivateKillSwitch() {
  return post<{ status: string }>("/risk/kill-switch/deactivate");
}

export function fetchHealth() {
  return api<HealthStatus>("/health");
}

export function fetchStatus() {
  return api<Record<string, unknown>>("/status");
}

// ---------------------------------------------------------------------------
// Execution
// ---------------------------------------------------------------------------

export function fetchPendingOrders() {
  return api<PendingOrder[]>("/execution/pending");
}

export function approveOrder(signalId: string) {
  return post<{ status: string }>("/execution/approve", {
    signal_id: signalId,
  });
}

export function approveStrategy(strategyId: string) {
  return post<{ status: string }>(
    `/execution/approve-strategy/${strategyId}`,
  );
}

export function fetchTrades(limit = 100) {
  return api<TradeRecord[]>(`/execution/trades?limit=${limit}`);
}

// ---------------------------------------------------------------------------
// Backtest
// ---------------------------------------------------------------------------

export function startBacktest(config: Record<string, unknown>) {
  return post<{ task_id: string }>("/backtest", config);
}

export function fetchBacktestTask(taskId: string) {
  return api<BacktestTask>(`/backtest/task/${taskId}`);
}

// ---------------------------------------------------------------------------
// Explore
// ---------------------------------------------------------------------------

export function fetchExploreStats() {
  return api<ExploreStats>("/explore/stats");
}

export function fetchExploreLeaderboard() {
  return api<LeaderboardEntry[]>("/explore/leaderboard");
}

export function startExplore(config?: Record<string, unknown>) {
  return post<{ status: string }>("/explore/start", config);
}

export function stopExplore() {
  return post<{ status: string }>("/explore/stop");
}

export function generateExploreStrategies(count = 5) {
  return post<{ status: string }>("/explore/generate", { count });
}

export function fetchExplorePromotions() {
  return api<ExplorePromotion[]>("/explore/promotions");
}

export function fetchExploreSymbols() {
  return api<string[]>("/explore/symbols");
}

export function refreshExploreSymbols() {
  return post<{ status: string }>("/explore/refresh-symbols");
}

// ---------------------------------------------------------------------------
// Resources / Workers
// ---------------------------------------------------------------------------

export function fetchResources() {
  return api<ResourceInfo[]>("/resources");
}

export function setResourcePriority(
  strategyId: string,
  priority: number,
) {
  return post<{ status: string }>("/resources/priority", {
    strategy_id: strategyId,
    priority,
  });
}

export function fetchWorkers() {
  return api<WorkerInfo[]>("/workers");
}

// ---------------------------------------------------------------------------
// System / Logs
// ---------------------------------------------------------------------------

export function fetchSystemAlerts() {
  return api<SystemAlert[]>("/system/alerts");
}

export function fetchLogs(limit = 200) {
  return api<LogEntry[]>(`/logs?limit=${limit}`);
}
