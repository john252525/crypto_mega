"""Database models — SQLAlchemy async models for persistent storage."""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(AsyncAttrs, DeclarativeBase):
    pass


class CandleRecord(Base):
    """OHLCV candle stored locally. One row = one candle."""
    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "timestamp_ms", name="uq_candle"),
        Index("ix_candle_lookup", "symbol", "timeframe", "timestamp_ms"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)       # e.g. BTC/USDT
    timeframe: Mapped[str] = mapped_column(String(5), nullable=False)     # e.g. 1m, 5m, 1h
    timestamp_ms: Mapped[int] = mapped_column(BigInteger, nullable=False) # unix ms
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    collected_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())


class StrategyRecord(Base):
    """Persisted strategy configuration."""
    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    code: Mapped[str] = mapped_column(Text, default="")  # strategy source code
    symbols: Mapped[str] = mapped_column(Text, default="")  # JSON list
    timeframes: Mapped[str] = mapped_column(Text, default="1h")
    parameters: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    priority: Mapped[int] = mapped_column(Integer, default=50)
    auto_execute: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class TradeRecord(Base):
    """Persisted trade result."""
    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    signal_id: Mapped[str] = mapped_column(String(36), index=True)
    strategy_id: Mapped[str] = mapped_column(String(36), index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(10))
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float, nullable=True)
    quantity: Mapped[float] = mapped_column(Float)
    pnl: Mapped[float] = mapped_column(Float, default=0.0)
    pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)
    fees: Mapped[float] = mapped_column(Float, default=0.0)
    exchange_order_id: Mapped[str] = mapped_column(String(100), default="")
    is_theoretical: Mapped[bool] = mapped_column(Boolean, default=False)  # backtest vs real
    opened_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    closed_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)


class SignalRecord(Base):
    """Persisted signal for history/audit."""
    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id: Mapped[str] = mapped_column(String(36), index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(10))
    strength: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    was_executed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())


class AlertRecord(Base):
    """Persisted alerts for divergence monitoring."""
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_id: Mapped[str] = mapped_column(String(36), index=True)
    metric: Mapped[str] = mapped_column(String(50))
    theoretical: Mapped[float] = mapped_column(Float)
    real: Mapped[float] = mapped_column(Float)
    divergence_pct: Mapped[float] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text, default="")
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())


class BacktestResultRecord(Base):
    """Persisted backtest results."""
    __tablename__ = "backtest_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_name: Mapped[str] = mapped_column(String(255), index=True)
    parameters: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    total_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    total_pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0.0)
    sharpe_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    profit_factor: Mapped[float] = mapped_column(Float, default=0.0)
    run_time_sec: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())


class ExplorationTaskRecord(Base):
    """A single exploration task: test strategy X with params Y on symbol Z."""
    __tablename__ = "exploration_tasks"
    __table_args__ = (
        Index("ix_explore_status", "status"),
        Index("ix_explore_strategy", "strategy_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    strategy_name: Mapped[str] = mapped_column(String(255))
    symbol: Mapped[str] = mapped_column(String(30))
    timeframe: Mapped[str] = mapped_column(String(5))
    exchange_id: Mapped[str] = mapped_column(String(30), default="binance")
    parameters: Mapped[str] = mapped_column(Text, default="{}")  # JSON
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, running, done, failed
    worker_id: Mapped[str] = mapped_column(String(50), default="")
    celery_task_id: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)


class ExplorationResultRecord(Base):
    """Result of an exploration task — stored permanently for analysis."""
    __tablename__ = "exploration_results"
    __table_args__ = (
        Index("ix_explres_strategy", "strategy_name"),
        Index("ix_explres_pnl", "total_pnl_pct"),
        Index("ix_explres_sharpe", "sharpe_ratio"),
        Index("ix_explres_symbol", "symbol"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(String(36), index=True)
    strategy_name: Mapped[str] = mapped_column(String(255))
    symbol: Mapped[str] = mapped_column(String(30))
    timeframe: Mapped[str] = mapped_column(String(5))
    exchange_id: Mapped[str] = mapped_column(String(30), default="binance")
    parameters: Mapped[str] = mapped_column(Text, default="{}")
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    total_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    total_pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)
    max_drawdown: Mapped[float] = mapped_column(Float, default=0.0)
    sharpe_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    profit_factor: Mapped[float] = mapped_column(Float, default=0.0)
    avg_trade_pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)
    run_time_sec: Mapped[float] = mapped_column(Float, default=0.0)
    promoted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())


class PaperPositionRecord(Base):
    """Persisted paper trading position — survives restarts."""
    __tablename__ = "paper_positions"
    __table_args__ = (
        Index("ix_paper_pos_strategy", "strategy_id"),
        Index("ix_paper_pos_symbol", "symbol"),
        Index("ix_paper_pos_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    signal_id: Mapped[str] = mapped_column(String(36), default="")
    strategy_id: Mapped[str] = mapped_column(String(36), default="")
    strategy_name: Mapped[str] = mapped_column(String(255), default="")
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # long/short
    entry_price: Mapped[float] = mapped_column(Float, nullable=False)
    current_price: Mapped[float] = mapped_column(Float, default=0.0)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float] = mapped_column(Float, nullable=True)
    quantity: Mapped[float] = mapped_column(Float, default=1.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    unrealized_pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    realized_pnl_pct: Mapped[float] = mapped_column(Float, default=0.0)
    exit_price: Mapped[float] = mapped_column(Float, nullable=True)
    close_reason: Mapped[str] = mapped_column(String(20), default="")
    signal_strength: Mapped[float] = mapped_column(Float, default=0.0)
    signal_metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(10), default="open")  # open/closed
    opened_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    closed_at: Mapped[datetime.datetime] = mapped_column(DateTime, nullable=True)


class PaperSignalLogRecord(Base):
    """Persisted paper signal log entry."""
    __tablename__ = "paper_signal_log"
    __table_args__ = (
        Index("ix_paper_sig_strategy", "strategy_id"),
        Index("ix_paper_sig_ts", "timestamp"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(String(36), default="")
    strategy_id: Mapped[str] = mapped_column(String(36), default="")
    strategy_name: Mapped[str] = mapped_column(String(255), default="")
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    strength: Mapped[float] = mapped_column(Float, default=0.0)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    timestamp: Mapped[float] = mapped_column(Float, nullable=False)


class WorkerNodeRecord(Base):
    """Registered compute worker node."""
    __tablename__ = "worker_nodes"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)  # hostname or UUID
    hostname: Mapped[str] = mapped_column(String(255), default="")
    ip_address: Mapped[str] = mapped_column(String(45), default="")
    max_workers: Mapped[int] = mapped_column(Integer, default=4)
    current_tasks: Mapped[int] = mapped_column(Integer, default=0)
    total_completed: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="online")  # online, offline, draining
    last_heartbeat: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())
    registered_at: Mapped[datetime.datetime] = mapped_column(DateTime, server_default=func.now())


async def init_db(database_url: str, connect_timeout: int = 10) -> async_sessionmaker:
    """Initialize database and create tables. PostgreSQL only."""
    if "sqlite" in database_url.lower():
        raise RuntimeError("SQLite is not supported. Use PostgreSQL.")
    engine = create_async_engine(
        database_url,
        echo=False,
        connect_args={"command_timeout": connect_timeout},
        pool_pre_ping=True,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)
