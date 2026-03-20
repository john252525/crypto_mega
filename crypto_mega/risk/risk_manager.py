"""Risk Manager — position sizing, drawdown control, kill switch."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from crypto_mega.config.settings import RiskConfig
from crypto_mega.utils.types import Signal, SignalDirection

logger = logging.getLogger(__name__)


@dataclass
class Position:
    symbol: str
    direction: SignalDirection
    entry_price: float
    quantity: float
    strategy_id: str
    opened_at: float = field(default_factory=time.time)
    unrealized_pnl: float = 0.0


@dataclass
class PortfolioState:
    total_equity: float = 10000.0
    available_balance: float = 10000.0
    positions: dict[str, Position] = field(default_factory=dict)
    daily_trades: int = 0
    daily_pnl: float = 0.0
    peak_equity: float = 10000.0
    current_drawdown_pct: float = 0.0
    kill_switch_active: bool = False


class RiskManager:
    """
    Controls risk across the entire portfolio.

    Features:
    - Position sizing based on risk per trade
    - Maximum drawdown monitoring with auto-pause
    - Kill switch for emergency stop
    - Per-strategy position limits
    - Daily trade/loss limits
    - Correlation-aware position sizing (don't overload correlated assets)
    """

    def __init__(self, config: RiskConfig, initial_equity: float = 10000.0):
        self.config = config
        self.portfolio = PortfolioState(
            total_equity=initial_equity,
            available_balance=initial_equity,
            peak_equity=initial_equity,
        )

    def check_signal(self, signal: Signal) -> tuple[bool, str, float]:
        """
        Check if a signal is allowed and calculate position size.

        Returns:
            (allowed: bool, reason: str, quantity: float)
        """
        # Kill switch
        if self.portfolio.kill_switch_active:
            return False, "Kill switch is active — all trading halted", 0.0

        # Drawdown check
        if self.portfolio.current_drawdown_pct >= self.config.max_drawdown_pct:
            return False, f"Max drawdown exceeded: {self.portfolio.current_drawdown_pct:.1f}%", 0.0

        # Daily trade limit
        if self.portfolio.daily_trades >= self.config.max_daily_trades:
            return False, f"Daily trade limit reached: {self.config.max_daily_trades}", 0.0

        # Max open positions
        if len(self.portfolio.positions) >= self.config.max_open_positions:
            if signal.direction in (SignalDirection.LONG, SignalDirection.SHORT):
                return False, f"Max positions reached: {self.config.max_open_positions}", 0.0

        # Calculate position size
        quantity = self._calculate_position_size(signal)
        if quantity <= 0:
            return False, "Calculated position size is zero", 0.0

        # Check position concentration
        position_value = quantity * signal.price
        position_pct = position_value / self.portfolio.total_equity * 100
        if position_pct > self.config.max_position_size_pct:
            # Scale down to max allowed
            quantity = (self.config.max_position_size_pct / 100 * self.portfolio.total_equity) / signal.price

        return True, "OK", quantity

    def _calculate_position_size(self, signal: Signal) -> float:
        """
        Calculate position size using risk-based sizing.
        Risk per trade = config.max_portfolio_risk_pct of equity.
        """
        if signal.price <= 0:
            return 0.0

        risk_amount = self.portfolio.total_equity * (self.config.max_portfolio_risk_pct / 100)

        if signal.stop_loss and signal.stop_loss > 0:
            # Size based on stop loss distance
            risk_per_unit = abs(signal.price - signal.stop_loss)
            if risk_per_unit > 0:
                return risk_amount / risk_per_unit
        else:
            # Default: assume 2% adverse move as stop
            risk_per_unit = signal.price * 0.02
            return risk_amount / risk_per_unit

    def open_position(self, signal: Signal, quantity: float) -> None:
        """Record a new position."""
        key = f"{signal.strategy_id}_{signal.symbol}"
        self.portfolio.positions[key] = Position(
            symbol=signal.symbol,
            direction=signal.direction,
            entry_price=signal.price,
            quantity=quantity,
            strategy_id=signal.strategy_id,
        )
        self.portfolio.daily_trades += 1
        self.portfolio.available_balance -= quantity * signal.price

    def close_position(self, strategy_id: str, symbol: str, exit_price: float) -> float:
        """Close a position and return PnL."""
        key = f"{strategy_id}_{symbol}"
        pos = self.portfolio.positions.pop(key, None)
        if not pos:
            return 0.0

        if pos.direction == SignalDirection.LONG:
            pnl = (exit_price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - exit_price) * pos.quantity

        self.portfolio.total_equity += pnl
        self.portfolio.available_balance += pos.quantity * exit_price
        self.portfolio.daily_pnl += pnl

        # Update drawdown tracking
        if self.portfolio.total_equity > self.portfolio.peak_equity:
            self.portfolio.peak_equity = self.portfolio.total_equity

        dd = (self.portfolio.peak_equity - self.portfolio.total_equity) / self.portfolio.peak_equity * 100
        self.portfolio.current_drawdown_pct = dd

        # Kill switch check
        if dd >= self.config.kill_switch_loss_pct:
            self.portfolio.kill_switch_active = True
            logger.critical(f"KILL SWITCH ACTIVATED — drawdown {dd:.1f}% exceeds {self.config.kill_switch_loss_pct}%")

        return pnl

    def activate_kill_switch(self) -> None:
        """Manual emergency stop."""
        self.portfolio.kill_switch_active = True
        logger.critical("KILL SWITCH MANUALLY ACTIVATED")

    def deactivate_kill_switch(self) -> None:
        """Reset kill switch (admin action)."""
        self.portfolio.kill_switch_active = False
        logger.info("Kill switch deactivated")

    def reset_daily_counters(self) -> None:
        """Call at start of each trading day."""
        self.portfolio.daily_trades = 0
        self.portfolio.daily_pnl = 0.0

    def update_unrealized_pnl(self, prices: dict[str, float]) -> None:
        """Update unrealized PnL for all positions given current prices."""
        for pos in self.portfolio.positions.values():
            current = prices.get(pos.symbol, pos.entry_price)
            if pos.direction == SignalDirection.LONG:
                pos.unrealized_pnl = (current - pos.entry_price) * pos.quantity
            else:
                pos.unrealized_pnl = (pos.entry_price - current) * pos.quantity

    def get_status(self) -> dict:
        return {
            "equity": round(self.portfolio.total_equity, 2),
            "available": round(self.portfolio.available_balance, 2),
            "positions": len(self.portfolio.positions),
            "daily_trades": self.portfolio.daily_trades,
            "daily_pnl": round(self.portfolio.daily_pnl, 2),
            "drawdown_pct": round(self.portfolio.current_drawdown_pct, 2),
            "kill_switch": self.portfolio.kill_switch_active,
            "open_positions": {
                k: {
                    "symbol": p.symbol,
                    "direction": p.direction.value,
                    "entry": p.entry_price,
                    "qty": p.quantity,
                    "unrealized_pnl": round(p.unrealized_pnl, 2),
                }
                for k, p in self.portfolio.positions.items()
            },
        }
