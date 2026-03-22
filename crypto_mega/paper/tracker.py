"""Paper Tracker — virtual P&L tracking for every signal on live prices.

This is the core of the "strategy tournament" approach:
- Every signal opens a virtual position at signal price
- Positions are tracked against live exchange prices
- SL/TP triggers are respected
- Stats accumulate per strategy for the leaderboard
- No real money — just proof that a strategy works (or doesn't)

All state is persisted to PostgreSQL so it survives restarts.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select, update

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
    signal_metadata: dict = field(default_factory=dict)

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
    All state persisted to PostgreSQL — survives restarts.

    Usage:
        tracker = PaperTracker()
        await tracker.init_db(session_factory)   # load from DB
        signal_engine.on_signal(tracker.handle_signal)
    """

    def __init__(self, max_positions_per_strategy: int = 50):
        self.max_positions_per_strategy = max_positions_per_strategy
        self._positions: dict[str, PaperPosition] = {}  # pos_id -> position (open only)
        self._strategy_names: dict[str, str] = {}  # strategy_id -> name
        self._closed: list[PaperPosition] = []
        self._signal_log: list[dict] = []  # in-memory recent signal log for fast reads
        self._on_close_handlers: list[callable] = []
        self._session_factory = None  # async_sessionmaker, set via init_db()

    async def init_db(self, session_factory) -> None:
        """Load paper state from PostgreSQL on startup."""
        from crypto_mega.data.models import PaperPositionRecord, PaperSignalLogRecord

        self._session_factory = session_factory
        if not session_factory:
            logger.warning("PaperTracker: no DB session, running in-memory only")
            return

        async with session_factory() as session:
            # Load open positions
            result = await session.execute(
                select(PaperPositionRecord).where(PaperPositionRecord.status == "open")
            )
            for rec in result.scalars().all():
                pos = self._record_to_position(rec)
                self._positions[pos.id] = pos

            # Load closed positions (last 500)
            result = await session.execute(
                select(PaperPositionRecord)
                .where(PaperPositionRecord.status == "closed")
                .order_by(PaperPositionRecord.closed_at.desc())
                .limit(500)
            )
            for rec in result.scalars().all():
                self._closed.append(self._record_to_position(rec))
            self._closed.reverse()  # oldest first

            # Load recent signal log (last 500)
            result = await session.execute(
                select(PaperSignalLogRecord)
                .order_by(PaperSignalLogRecord.timestamp.desc())
                .limit(500)
            )
            for rec in result.scalars().all():
                self._signal_log.append({
                    "id": rec.signal_id,
                    "strategy_id": rec.strategy_id,
                    "strategy_name": rec.strategy_name,
                    "symbol": rec.symbol,
                    "direction": rec.direction,
                    "strength": rec.strength,
                    "price": rec.price,
                    "stop_loss": rec.stop_loss,
                    "take_profit": rec.take_profit,
                    "metadata": json.loads(rec.metadata_json) if rec.metadata_json else {},
                    "timestamp": rec.timestamp,
                })
            self._signal_log.reverse()  # oldest first

        logger.info(
            f"PaperTracker loaded from DB: {len(self._positions)} open, "
            f"{len(self._closed)} closed, {len(self._signal_log)} signals"
        )

    @staticmethod
    def _record_to_position(rec) -> PaperPosition:
        """Convert a PaperPositionRecord to PaperPosition dataclass."""
        return PaperPosition(
            id=rec.id,
            signal_id=rec.signal_id or "",
            strategy_id=rec.strategy_id or "",
            strategy_name=rec.strategy_name or "",
            symbol=rec.symbol,
            direction=SignalDirection(rec.direction),
            entry_price=rec.entry_price,
            current_price=rec.current_price or rec.entry_price,
            stop_loss=rec.stop_loss,
            take_profit=rec.take_profit,
            quantity=rec.quantity or 1.0,
            unrealized_pnl=rec.unrealized_pnl or 0.0,
            unrealized_pnl_pct=rec.unrealized_pnl_pct or 0.0,
            opened_at=rec.opened_at or datetime.utcnow(),
            closed_at=rec.closed_at,
            exit_price=rec.exit_price,
            realized_pnl=rec.realized_pnl or 0.0,
            realized_pnl_pct=rec.realized_pnl_pct or 0.0,
            close_reason=rec.close_reason or "",
            signal_strength=rec.signal_strength or 0.0,
            signal_metadata=json.loads(rec.signal_metadata_json) if rec.signal_metadata_json else {},
        )

    def _position_to_record(self, pos: PaperPosition):
        """Convert PaperPosition to PaperPositionRecord for DB insert."""
        from crypto_mega.data.models import PaperPositionRecord
        return PaperPositionRecord(
            id=pos.id,
            signal_id=pos.signal_id,
            strategy_id=pos.strategy_id,
            strategy_name=pos.strategy_name,
            symbol=pos.symbol,
            direction=pos.direction.value,
            entry_price=pos.entry_price,
            current_price=pos.current_price,
            stop_loss=pos.stop_loss,
            take_profit=pos.take_profit,
            quantity=pos.quantity,
            unrealized_pnl=pos.unrealized_pnl,
            unrealized_pnl_pct=pos.unrealized_pnl_pct,
            realized_pnl=pos.realized_pnl,
            realized_pnl_pct=pos.realized_pnl_pct,
            exit_price=pos.exit_price,
            close_reason=pos.close_reason,
            signal_strength=pos.signal_strength,
            signal_metadata_json=json.dumps(pos.signal_metadata) if pos.signal_metadata else "{}",
            status="open" if pos.is_open else "closed",
            opened_at=pos.opened_at,
            closed_at=pos.closed_at,
        )

    async def _db_save_position(self, pos: PaperPosition) -> None:
        """Save a new position to DB."""
        if not self._session_factory:
            return
        try:
            async with self._session_factory() as session:
                session.add(self._position_to_record(pos))
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to save position {pos.id} to DB: {e}")

    async def _db_close_position(self, pos: PaperPosition) -> None:
        """Update a closed position in DB."""
        if not self._session_factory:
            return
        try:
            from crypto_mega.data.models import PaperPositionRecord
            async with self._session_factory() as session:
                await session.execute(
                    update(PaperPositionRecord)
                    .where(PaperPositionRecord.id == pos.id)
                    .values(
                        status="closed",
                        exit_price=pos.exit_price,
                        current_price=pos.current_price,
                        realized_pnl=pos.realized_pnl,
                        realized_pnl_pct=pos.realized_pnl_pct,
                        close_reason=pos.close_reason,
                        closed_at=pos.closed_at,
                        unrealized_pnl=0.0,
                        unrealized_pnl_pct=0.0,
                    )
                )
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to update closed position {pos.id} in DB: {e}")

    async def _db_update_prices(self, positions: list[PaperPosition]) -> None:
        """Batch update current prices in DB."""
        if not self._session_factory or not positions:
            return
        try:
            from crypto_mega.data.models import PaperPositionRecord
            async with self._session_factory() as session:
                for pos in positions:
                    await session.execute(
                        update(PaperPositionRecord)
                        .where(PaperPositionRecord.id == pos.id)
                        .values(
                            current_price=pos.current_price,
                            unrealized_pnl=pos.unrealized_pnl,
                            unrealized_pnl_pct=pos.unrealized_pnl_pct,
                        )
                    )
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to batch update prices in DB: {e}")

    async def _db_save_signal(self, sig: dict) -> None:
        """Save a signal log entry to DB."""
        if not self._session_factory:
            return
        try:
            from crypto_mega.data.models import PaperSignalLogRecord
            async with self._session_factory() as session:
                session.add(PaperSignalLogRecord(
                    signal_id=sig.get("id", ""),
                    strategy_id=sig.get("strategy_id", ""),
                    strategy_name=sig.get("strategy_name", ""),
                    symbol=sig["symbol"],
                    direction=sig["direction"],
                    strength=sig.get("strength", 0.0),
                    price=sig.get("price", 0.0),
                    stop_loss=sig.get("stop_loss"),
                    take_profit=sig.get("take_profit"),
                    metadata_json=json.dumps(sig.get("metadata", {})),
                    timestamp=sig["timestamp"],
                ))
                await session.commit()
        except Exception as e:
            logger.error(f"Failed to save signal to DB: {e}")

    def on_position_close(self, handler: callable) -> None:
        """Register handler called when a paper position closes."""
        self._on_close_handlers.append(handler)

    async def handle_signal(self, signal: Signal) -> None:
        """Signal handler — called by SignalEngine for each new signal."""
        if signal.direction == SignalDirection.HOLD:
            return

        # Log every signal (including metadata for detail view)
        sig_entry = {
            "id": signal.id,
            "strategy_id": signal.strategy_id[:8] if signal.strategy_id else "",
            "strategy_name": self._strategy_names.get(signal.strategy_id, "?"),
            "symbol": signal.symbol,
            "direction": signal.direction.value,
            "strength": round(signal.strength, 3),
            "price": signal.price,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "metadata": signal.metadata or {},
            "timestamp": time.time(),
        }
        self._signal_log.append(sig_entry)
        # Keep only last 500 in memory
        if len(self._signal_log) > 500:
            self._signal_log = self._signal_log[-500:]
        # Persist to DB
        await self._db_save_signal(sig_entry)

        # CLOSE signals close existing positions for this strategy+symbol
        if signal.direction == SignalDirection.CLOSE:
            await self._close_positions_for(
                signal.strategy_id, signal.symbol, signal.price, "signal"
            )
            return

        # Skip weak signals
        if signal.strength < 0.3:
            return

        # Deduplicate: skip if already have an open position for this strategy+symbol+direction
        for p in self._positions.values():
            if (
                p.strategy_id == signal.strategy_id
                and p.symbol == signal.symbol
                and p.direction == signal.direction
                and p.is_open
            ):
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
            signal_metadata=signal.metadata or {},
        )
        self._positions[pos.id] = pos
        await self._db_save_position(pos)
        logger.info(
            f"Paper OPEN: {signal.direction.value.upper()} {signal.symbol} "
            f"@ {signal.price:.2f} | strategy={pos.strategy_name} "
            f"(strength={signal.strength:.2f}"
            f"{f', SL={signal.stop_loss:.2f}' if signal.stop_loss else ''}"
            f"{f', TP={signal.take_profit:.2f}' if signal.take_profit else ''}"
            f") | open positions: {len(self._positions)}"
        )

    def register_strategy(self, strategy_id: str, name: str) -> None:
        """Register strategy name for display."""
        self._strategy_names[strategy_id] = name

    async def update_price(self, symbol: str, price: float) -> list[PaperPosition]:
        """Update price for a symbol, check SL/TP. Returns newly closed positions."""
        closed = []
        to_remove = []
        updated = []

        for pos_id, pos in self._positions.items():
            if pos.symbol != symbol or not pos.is_open:
                continue

            reason = pos.update_price(price)
            updated.append(pos)
            if reason:
                pos.close(price, reason)
                self._closed.append(pos)
                to_remove.append(pos_id)
                closed.append(pos)
                pnl_sign = "+" if pos.realized_pnl_pct >= 0 else ""
                logger.info(
                    f"Paper CLOSE [{reason.upper()}]: {pos.direction.value.upper()} "
                    f"{pos.symbol} | entry={pos.entry_price:.2f} exit={price:.2f} | "
                    f"P&L={pnl_sign}{pos.realized_pnl_pct:.2f}% | "
                    f"strategy={pos.strategy_name}"
                )
                await self._db_close_position(pos)

                for handler in self._on_close_handlers:
                    try:
                        handler(pos)
                    except Exception as e:
                        logger.error(f"Close handler error: {e}")

        for pid in to_remove:
            del self._positions[pid]

        # Batch update prices for positions that stayed open
        still_open = [p for p in updated if p not in closed]
        await self._db_update_prices(still_open)

        return closed

    async def close_position(self, position_id: str, price: float, reason: str = "manual") -> PaperPosition | None:
        """Manually close a position."""
        pos = self._positions.get(position_id)
        if not pos or not pos.is_open:
            return None

        pos.close(price, reason)
        self._closed.append(pos)
        del self._positions[position_id]
        await self._db_close_position(pos)
        return pos

    async def _close_positions_for(
        self, strategy_id: str, symbol: str, price: float, reason: str
    ) -> None:
        to_remove = []
        for pos_id, pos in self._positions.items():
            if pos.strategy_id == strategy_id and pos.symbol == symbol and pos.is_open:
                pos.close(price, reason)
                self._closed.append(pos)
                to_remove.append(pos_id)
                await self._db_close_position(pos)
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
                "signal_id": p.signal_id,
                "metadata": p.signal_metadata,
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
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "strength": p.signal_strength,
                "signal_id": p.signal_id,
                "metadata": p.signal_metadata,
            }
            for p in positions[-limit:]
        ]

    async def reset_all(self) -> dict:
        """Close all open positions and clear state. Returns count of cleared items."""
        open_count = len(self._positions)
        closed_count = len(self._closed)
        signal_count = len(self._signal_log)
        self._positions.clear()
        self._closed.clear()
        self._signal_log.clear()

        # Clear DB tables too
        if self._session_factory:
            try:
                from crypto_mega.data.models import PaperPositionRecord, PaperSignalLogRecord
                async with self._session_factory() as session:
                    await session.execute(
                        update(PaperPositionRecord)
                        .where(PaperPositionRecord.status == "open")
                        .values(status="reset")
                    )
                    await session.commit()
            except Exception as e:
                logger.error(f"Failed to reset paper positions in DB: {e}")

        logger.info(f"Paper tracker reset: {open_count} open, {closed_count} closed, {signal_count} signals cleared")
        return {"open_cleared": open_count, "closed_cleared": closed_count, "signals_cleared": signal_count}

    async def deduplicate_positions(self) -> int:
        """Remove duplicate open positions keeping only the oldest per strategy+symbol+direction."""
        seen = {}
        to_remove = []
        for pos_id, pos in sorted(self._positions.items(), key=lambda x: x[1].opened_at):
            if not pos.is_open:
                continue
            key = (pos.strategy_id, pos.symbol, pos.direction)
            if key in seen:
                to_remove.append(pos_id)
            else:
                seen[key] = pos_id
        for pid in to_remove:
            pos = self._positions.pop(pid)
            pos.close(pos.current_price, "dedup")
            self._closed.append(pos)
            await self._db_close_position(pos)
        if to_remove:
            logger.info(f"Deduplicated paper positions: removed {len(to_remove)} duplicates")
        return len(to_remove)

    def get_signal_log(self, limit: int = 100) -> list[dict]:
        """Get recent signal log."""
        return self._signal_log[-limit:]

    def get_symbols_tracked(self) -> set[str]:
        """Get all symbols with open positions (for price updates)."""
        return {p.symbol for p in self._positions.values() if p.is_open}
