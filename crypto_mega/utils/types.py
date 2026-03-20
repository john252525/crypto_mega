"""Core types used across the system."""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime


class SignalDirection(enum.Enum):
    LONG = "long"
    SHORT = "short"
    CLOSE = "close"
    HOLD = "hold"


class OrderType(enum.Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class StrategyStatus(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class TimeFrame(enum.Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


@dataclass
class Signal:
    """A trading signal produced by a strategy."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    strategy_id: str = ""
    symbol: str = ""  # e.g. "BTC/USDT"
    direction: SignalDirection = SignalDirection.HOLD
    strength: float = 0.0  # 0.0 to 1.0
    price: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    metadata: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class OHLCV:
    """Single candle data."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class StrategyConfig:
    """Configuration for a single strategy instance."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    symbols: list[str] = field(default_factory=list)
    timeframes: list[TimeFrame] = field(default_factory=lambda: [TimeFrame.H1])
    parameters: dict = field(default_factory=dict)
    priority: int = 50  # 0-100 resource priority
    auto_execute: bool = False  # whether to auto-forward signals for execution
    max_signals_per_hour: int = 100


@dataclass
class TradeResult:
    """Result of an executed trade."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str = ""
    strategy_id: str = ""
    symbol: str = ""
    direction: SignalDirection = SignalDirection.HOLD
    entry_price: float = 0.0
    exit_price: float | None = None
    quantity: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    fees: float = 0.0
    opened_at: datetime = field(default_factory=datetime.utcnow)
    closed_at: datetime | None = None
    exchange_order_id: str = ""


@dataclass
class StrategyStats:
    """Aggregated statistics for a strategy."""
    strategy_id: str = ""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    avg_trade_pnl: float = 0.0
    profit_factor: float = 0.0
    theoretical_pnl: float = 0.0  # from backtesting
    real_pnl: float = 0.0  # from live trading
    divergence: float = 0.0  # theoretical - real
