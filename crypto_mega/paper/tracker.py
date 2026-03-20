"""Paper Tracker — virtual P&L tracking for every signal on live prices.

This is the core of the "strategy tournament" approach:
- Every signal opens a virtual position at signal price
- Positions are tracked against live exchange prices
- SL/TP triggers are respected
- Stats accumulate per strategy for the leaderboard
- No real money — just proof that a strategy works (or doesn't)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from crypto_mega.utils.types import Signal, SignalDirection

logger = logging.getLogger(__name__)


@dataclass
class PaperPosition:
    """A virtual position opened from a signal."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str = ""
    strategy_id: str = ""
    strategy_name: str = ""
    symbol: str = ""
    direction: SignalDirection = SignalDirection.LONG
    entry_price: float = 0.0
    current_price: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    quantity: float = 1.0  # normalized to 1 unit for fair comparison
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    opened_at: datetime = field(default_factory=datetime.utcnow)
    closed_at: datetime | None = None
    exit_price: float | None = None
    realized_pnl: float = 0.0
    realized_pnl_pct: float = 0.0
    close_reason: str = ""  # "sl", "tp", "signal", "manual", "timeout"
    signal_strength: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    def update_price(self, price: float) -> str | None:
        """Update current price, check SL/TP. Returns close reason or None."""
        self.current_price = price

        if self.direction == SignalDirection.LONG:
            self.unrealized_pnl = (price - self.entry_price) * self.quantity
            self.unrealized_pnl_pct = (
                (price - self.entry_price) / self.entry_price * 100
                if self.entry_price > 0
                else 0
            )
        elif self.direction == SignalDirection.SHORT:
            self.unrealized_pnl = (self.entry_price - price) * self.quantity
            self.unrealized_pnl_pct = (
                (self.entry_price - price) / self.entry_price * 100
                if self.entry_price > 0
                else 0
            )

        # Check stop loss
        if self.stop_loss is not None:
            if self.direction == SignalDirection.LONG and price <= self.stop_loss:
                return "sl"
            if self.direction == SignalDirection.SHORT and price >= self.stop_loss:
                return "sl"

        # Check take profit
        if self.take_profit is not None:
            if self.direction == SignalDirection.LONG and price >= self.take_profit:
                return "tp"
            if self.direction == SignalDirection.SHORT and price <= self.take_profit:
                return "tp"

        return None

    def close(self, price: float, reason: str = "manual") -> None:
        """Close the position."""
        self.exit_price = price
        self.current_price = price
        self.closed_at = datetime.utcnow()
        self.close_reason = reason

        if self.direction == SignalDirection.LONG:
            self.realized_pnl = (price - self.entry_price) * self.quantity
            self.realized_pnl_pct = (
                (price - self.entry_price) / self.entry_price * 100
                if self.entry_price > 0
                else 0
            )
        elif self.direction == SignalDirection.SHORT:
            self.realized_pnl = (self.entry_price - price) * self.quantity
            self.realized_pnl_pct = (
                (self.entry_price - price) / self.entry_price * 100
                if self.entry_price > 0
                else 0
            )


@dataclass
class StrategyPaperStats:
    """Aggregated paper-trading stats for one strategy."""

    strategy_id: str = ""
    strategy_name: str = ""
    total_signals: int = 0
    open_positions: int = 0
    closed_positions: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    unrealized_pnl: float = 0.0
    max_drawdown: float = 0.0
    best_trade_pnl_pct: float = 0.0
    worst_trade_pnl_pct: float = 0.0
    avg_trade_pnl_pct: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    avg_hold_time_min: float = 0.0
    last_signal_at: float = 0.0
    promoted: bool = False  # whether this strategy is live-trading
    equity_curve: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "strategy_id": self.strategy_id[:8] if self.strategy_id else "",
            "strategy_name": self.strategy_name,
            "total_signals": self.total_signals,
            "open_positions": self.open_positions,
            "closed_positions": self.closed_positions,
            "wins": self.wins,
            "losses": self.losses,
            "total_pnl": round(self.total_pnl, 4),
            "total_pnl_pct": round(self.total_pnl_pct, 2),
            "unrealized_pnl": round(self.unrealized_pnl, 4),
            "max_drawdown": round(self.max_drawdown, 2),
            "best_trade_pnl_pct": round(self.best_trade_pnl_pct, 2),
            "worst_trade_pnl_pct": round(self.worst_trade_pnl_pct, 2),
            "avg_trade_pnl_pct": round(self.avg_trade_pnl_pct, 2),
            "win_rate": round(self.win_rate, 1),
            "profit_factor": round(self.profit_factor, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2),
            "avg_hold_time_min": round(self.avg_hold_time_min, 1),
            "last_signal_at": self.last_signal_at,
            "promoted": self.promoted,
            "equity_curve": self.equity_curve[-100:],  # last 100 points
        }


class PaperTracker:
    """
    Tracks all signals as virtual positions on live market data.

    Usage:
        tracker = PaperTracker()
        # Register as signal handler in SignalEngine:
        signal_engine.on_signal(tracker.handle_signal)
        # Periodically update prices:
        await tracker.update_prices(data_provider)
    """

    def __init__(self, max_positions_per_strategy: int = 50):
        self.max_positions_per_strategy = max_positions_per_strategy
        self._positions: dict[str, PaperPosition] = {}  # pos_id -> position
        self._strategy_names: dict[str, str] = {}  # strategy_id -> name
        self._closed: list[PaperPosition] = []
        self._signal_log: list[dict] = []  # raw signal log for UI
        self._on_close_handlers: list[callable] = []

    def on_position_close(self, handler: callable) -> None:
        """Register handler called when a paper position closes."""
        self._on_close_handlers.append(handler)

    async def handle_signal(self, signal: Signal) -> None:
        """Signal handler — called by SignalEngine for each new signal."""
        if signal.direction == SignalDirection.HOLD:
            return

        # Log every signal
        self._signal_log.append({
            "id": signal.id,
            "strategy_id": signal.strategy_id[:8] if signal.strategy_id else "",
            "symbol": signal.symbol,
            "direction": signal.direction.value,
            "strength": round(signal.strength, 3),
            "price": signal.price,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "timestamp": time.time(),
        })
        # Keep only last 500
        if len(self._signal_log) > 500:
            self._signal_log = self._signal_log[-500:]

        # CLOSE signals close existing positions for this strategy+symbol
        if signal.direction == SignalDirection.CLOSE:
            self._close_positions_for(
                signal.strategy_id, signal.symbol, signal.price, "signal"
            )
            return

        # Skip weak signals
        if signal.strength < 0.3:
            return

        # Check max open positions per strategy
        open_count = sum(
            1
            for p in self._positions.values()
            if p.strategy_id == signal.strategy_id and p.is_open
        )
        if open_count >= self.max_positions_per_strategy:
            return

        # Open paper position
        pos = PaperPosition(
            signal_id=signal.id,
            strategy_id=signal.strategy_id,
            strategy_name=self._strategy_names.get(signal.strategy_id, "?"),
            symbol=signal.symbol,
            direction=signal.direction,
            entry_price=signal.price,
            current_price=signal.price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            signal_strength=signal.strength,
        )
        self._positions[pos.id] = pos
        logger.debug(
            f"Paper position opened: {signal.symbol} {signal.direction.value} "
            f"@ {signal.price} (strategy={signal.strategy_id[:8]})"
        )

    def register_strategy(self, strategy_id: str, name: str) -> None:
        """Register strategy name for display."""
        self._strategy_names[strategy_id] = name

    def update_price(self, symbol: str, price: float) -> list[PaperPosition]:
        """Update price for a symbol, check SL/TP. Returns newly closed positions."""
        closed = []
        to_remove = []

        for pos_id, pos in self._positions.items():
            if pos.symbol != symbol or not pos.is_open:
                continue

            reason = pos.update_price(price)
            if reason:
                pos.close(price, reason)
                self._closed.append(pos)
                to_remove.append(pos_id)
                closed.append(pos)

                for handler in self._on_close_handlers:
                    try:
                        handler(pos)
                    except Exception as e:
                        logger.error(f"Close handler error: {e}")

        for pid in to_remove:
            del self._positions[pid]

        return closed

    def close_position(self, position_id: str, price: float, reason: str = "manual") -> PaperPosition | None:
        """Manually close a position."""
        pos = self._positions.get(position_id)
        if not pos or not pos.is_open:
            return None

        pos.close(price, reason)
        self._closed.append(pos)
        del self._positions[position_id]
        return pos

    def _close_positions_for(
        self, strategy_id: str, symbol: str, price: float, reason: str
    ) -> None:
        to_remove = []
        for pos_id, pos in self._positions.items():
            if pos.strategy_id == strategy_id and pos.symbol == symbol and pos.is_open:
                pos.close(price, reason)
                self._closed.append(pos)
                to_remove.append(pos_id)
        for pid in to_remove:
            del self._positions[pid]

    # ─── Stats & Leaderboard ───

    def get_strategy_stats(self, strategy_id: str) -> StrategyPaperStats:
        """Compute stats for a single strategy."""
        open_pos = [
            p for p in self._positions.values()
            if p.strategy_id == strategy_id and p.is_open
        ]
        closed_pos = [p for p in self._closed if p.strategy_id == strategy_id]

        stats = StrategyPaperStats(
            strategy_id=strategy_id,
            strategy_name=self._strategy_names.get(strategy_id, "?"),
            total_signals=len(
                [s for s in self._signal_log if s["strategy_id"] == strategy_id[:8]]
            ),
            open_positions=len(open_pos),
            closed_positions=len(closed_pos),
        )

        if closed_pos:
            wins = [p for p in closed_pos if p.realized_pnl > 0]
            losses = [p for p in closed_pos if p.realized_pnl <= 0]
            stats.wins = len(wins)
            stats.losses = len(losses)
            stats.total_pnl = sum(p.realized_pnl for p in closed_pos)
            stats.total_pnl_pct = sum(p.realized_pnl_pct for p in closed_pos)
            stats.win_rate = len(wins) / len(closed_pos) * 100
            stats.avg_trade_pnl_pct = stats.total_pnl_pct / len(closed_pos)

            pnl_pcts = [p.realized_pnl_pct for p in closed_pos]
            if pnl_pcts:
                stats.best_trade_pnl_pct = max(pnl_pcts)
                stats.worst_trade_pnl_pct = min(pnl_pcts)

            gross_profit = sum(p.realized_pnl for p in wins)
            gross_loss = abs(sum(p.realized_pnl for p in losses)) or 1.0
            stats.profit_factor = gross_profit / gross_loss

            # Sharpe ratio (simplified — using trade PnL % as returns)
            if len(pnl_pcts) > 1:
                import statistics

                mean_r = statistics.mean(pnl_pcts)
                std_r = statistics.stdev(pnl_pcts) or 1.0
                stats.sharpe_ratio = mean_r / std_r

            # Average hold time
            hold_times = []
            for p in closed_pos:
                if p.closed_at and p.opened_at:
                    dt = (p.closed_at - p.opened_at).total_seconds() / 60
                    hold_times.append(dt)
            if hold_times:
                stats.avg_hold_time_min = sum(hold_times) / len(hold_times)

            # Max drawdown from equity curve
            equity = 0.0
            peak = 0.0
            max_dd = 0.0
            curve = []
            for p in sorted(closed_pos, key=lambda x: x.closed_at or x.opened_at):
                equity += p.realized_pnl_pct
                curve.append(round(equity, 2))
                if equity > peak:
                    peak = equity
                dd = peak - equity
                if dd > max_dd:
                    max_dd = dd
            stats.max_drawdown = max_dd
            stats.equity_curve = curve

        stats.unrealized_pnl = sum(p.unrealized_pnl for p in open_pos)

        signals_for = [
            s for s in self._signal_log if s["strategy_id"] == strategy_id[:8]
        ]
        if signals_for:
            stats.last_signal_at = signals_for[-1]["timestamp"]

        return stats

    def get_leaderboard(self, sort_by: str = "total_pnl_pct", limit: int = 50) -> list[dict]:
        """Get strategy leaderboard sorted by given metric."""
        # Collect all strategy IDs
        all_ids = set()
        for p in self._positions.values():
            all_ids.add(p.strategy_id)
        for p in self._closed:
            all_ids.add(p.strategy_id)

        stats_list = []
        for sid in all_ids:
            s = self.get_strategy_stats(sid)
            stats_list.append(s)

        # Sort
        valid_keys = {
            "total_pnl_pct", "total_pnl", "win_rate", "sharpe_ratio",
            "profit_factor", "closed_positions", "total_signals",
        }
        key = sort_by if sort_by in valid_keys else "total_pnl_pct"
        stats_list.sort(key=lambda x: getattr(x, key, 0), reverse=True)

        return [s.to_dict() for s in stats_list[:limit]]

    def get_open_positions(self, strategy_id: str | None = None) -> list[dict]:
        """Get all open paper positions."""
        positions = list(self._positions.values())
        if strategy_id:
            positions = [p for p in positions if p.strategy_id == strategy_id]

        return [
            {
                "id": p.id,
                "strategy_id": p.strategy_id[:8],
                "strategy_name": p.strategy_name,
                "symbol": p.symbol,
                "direction": p.direction.value,
                "entry_price": p.entry_price,
                "current_price": p.current_price,
                "unrealized_pnl": round(p.unrealized_pnl, 4),
                "unrealized_pnl_pct": round(p.unrealized_pnl_pct, 2),
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "strength": p.signal_strength,
                "opened_at": str(p.opened_at),
            }
            for p in positions
        ]

    def get_closed_positions(
        self, strategy_id: str | None = None, limit: int = 100
    ) -> list[dict]:
        """Get closed paper positions."""
        positions = self._closed
        if strategy_id:
            positions = [p for p in positions if p.strategy_id == strategy_id]

        return [
            {
                "id": p.id,
                "strategy_id": p.strategy_id[:8],
                "strategy_name": p.strategy_name,
                "symbol": p.symbol,
                "direction": p.direction.value,
                "entry_price": p.entry_price,
                "exit_price": p.exit_price,
                "realized_pnl": round(p.realized_pnl, 4),
                "realized_pnl_pct": round(p.realized_pnl_pct, 2),
                "close_reason": p.close_reason,
                "opened_at": str(p.opened_at),
                "closed_at": str(p.closed_at),
            }
            for p in positions[-limit:]
        ]

    def get_signal_log(self, limit: int = 100) -> list[dict]:
        """Get recent signal log."""
        return self._signal_log[-limit:]

    def get_symbols_tracked(self) -> set[str]:
        """Get all symbols with open positions (for price updates)."""
        return {p.symbol for p in self._positions.values() if p.is_open}
