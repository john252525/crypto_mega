"""Performance Monitor — tracks theoretical vs real trading, detects divergence."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from crypto_mega.utils.types import StrategyStats, TradeResult

logger = logging.getLogger(__name__)


@dataclass
class DivergenceAlert:
    strategy_id: str
    metric: str
    theoretical: float
    real: float
    divergence_pct: float
    severity: str  # "info", "warning", "critical"
    timestamp: float = field(default_factory=time.time)
    message: str = ""


class PerformanceMonitor:
    """
    Monitors strategy performance in real-time.

    Key responsibilities:
    - Track theoretical (backtest) vs real (live) performance
    - Detect divergence and alert
    - Maintain running statistics per strategy
    - Recommend resource reallocation based on real performance
    - Detect anomalies (sudden PnL spikes, unusual drawdowns)
    """

    def __init__(self, divergence_threshold_pct: float = 20.0):
        self.divergence_threshold = divergence_threshold_pct
        self._strategy_stats: dict[str, StrategyStats] = {}
        self._theoretical_pnl: dict[str, float] = {}
        self._real_trades: dict[str, list[TradeResult]] = {}
        self._alerts: list[DivergenceAlert] = []
        self._alert_handlers: list[callable] = []

    def on_alert(self, handler: callable) -> None:
        """Register alert handler."""
        self._alert_handlers.append(handler)

    def set_theoretical_pnl(self, strategy_id: str, pnl: float) -> None:
        """Set expected PnL from backtesting."""
        self._theoretical_pnl[strategy_id] = pnl

    def record_trade(self, trade: TradeResult) -> None:
        """Record a real executed trade."""
        sid = trade.strategy_id
        if sid not in self._real_trades:
            self._real_trades[sid] = []
        self._real_trades[sid].append(trade)

        self._update_stats(sid)
        self._check_divergence(sid)

    def _update_stats(self, strategy_id: str) -> None:
        """Recalculate stats for a strategy."""
        trades = self._real_trades.get(strategy_id, [])
        if not trades:
            return

        closed = [t for t in trades if t.closed_at is not None]
        winning = [t for t in closed if t.pnl > 0]
        losing = [t for t in closed if t.pnl <= 0]

        total_pnl = sum(t.pnl for t in closed)
        gross_profit = sum(t.pnl for t in winning)
        gross_loss = abs(sum(t.pnl for t in losing)) or 1

        stats = StrategyStats(
            strategy_id=strategy_id,
            total_trades=len(closed),
            winning_trades=len(winning),
            losing_trades=len(losing),
            total_pnl=total_pnl,
            win_rate=len(winning) / len(closed) * 100 if closed else 0,
            avg_trade_pnl=total_pnl / len(closed) if closed else 0,
            profit_factor=gross_profit / gross_loss,
            real_pnl=total_pnl,
            theoretical_pnl=self._theoretical_pnl.get(strategy_id, 0),
        )
        stats.divergence = stats.theoretical_pnl - stats.real_pnl
        self._strategy_stats[strategy_id] = stats

    def _check_divergence(self, strategy_id: str) -> None:
        """Check if theoretical and real performance are diverging."""
        stats = self._strategy_stats.get(strategy_id)
        if not stats or stats.theoretical_pnl == 0:
            return

        div_pct = abs(stats.divergence) / abs(stats.theoretical_pnl) * 100

        if div_pct > self.divergence_threshold:
            severity = "critical" if div_pct > self.divergence_threshold * 2 else "warning"

            alert = DivergenceAlert(
                strategy_id=strategy_id,
                metric="pnl",
                theoretical=stats.theoretical_pnl,
                real=stats.real_pnl,
                divergence_pct=div_pct,
                severity=severity,
                message=(
                    f"Strategy {strategy_id[:8]} divergence: "
                    f"theoretical={stats.theoretical_pnl:+.2f}, "
                    f"real={stats.real_pnl:+.2f} ({div_pct:.1f}% off)"
                ),
            )
            self._alerts.append(alert)
            logger.warning(alert.message)

            for handler in self._alert_handlers:
                try:
                    handler(alert)
                except Exception as e:
                    logger.error(f"Alert handler error: {e}")

    def get_stats(self, strategy_id: str) -> StrategyStats | None:
        return self._strategy_stats.get(strategy_id)

    def get_all_stats(self) -> dict[str, dict]:
        return {
            sid: {
                "trades": s.total_trades,
                "win_rate": round(s.win_rate, 1),
                "pnl": round(s.total_pnl, 2),
                "theoretical_pnl": round(s.theoretical_pnl, 2),
                "real_pnl": round(s.real_pnl, 2),
                "divergence": round(s.divergence, 2),
                "profit_factor": round(s.profit_factor, 2),
            }
            for sid, s in self._strategy_stats.items()
        }

    def get_alerts(self, severity: str | None = None, limit: int = 50) -> list[dict]:
        alerts = self._alerts
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return [
            {
                "strategy_id": a.strategy_id[:8],
                "metric": a.metric,
                "divergence_pct": round(a.divergence_pct, 1),
                "severity": a.severity,
                "message": a.message,
                "timestamp": a.timestamp,
            }
            for a in alerts[-limit:]
        ]

    def get_recommendations(self) -> list[dict]:
        """Generate resource allocation recommendations based on real performance."""
        recs = []
        for sid, stats in self._strategy_stats.items():
            if stats.total_trades < 10:
                continue  # not enough data

            if stats.profit_factor > 1.5 and stats.win_rate > 55:
                recs.append({
                    "strategy_id": sid[:8],
                    "action": "increase_priority",
                    "reason": f"Strong performance: PF={stats.profit_factor:.2f}, WR={stats.win_rate:.1f}%",
                })
            elif stats.profit_factor < 0.8 or stats.win_rate < 35:
                recs.append({
                    "strategy_id": sid[:8],
                    "action": "decrease_priority",
                    "reason": f"Weak performance: PF={stats.profit_factor:.2f}, WR={stats.win_rate:.1f}%",
                })
            if abs(stats.divergence) > 0 and stats.theoretical_pnl != 0:
                div_pct = abs(stats.divergence) / abs(stats.theoretical_pnl) * 100
                if div_pct > 50:
                    recs.append({
                        "strategy_id": sid[:8],
                        "action": "review_strategy",
                        "reason": f"High divergence: {div_pct:.0f}% between theoretical and real",
                    })
        return recs
