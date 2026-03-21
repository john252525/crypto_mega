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


async def init_db(database_url: str) -> async_sessionmaker:
    """Initialize database and create tables."""
    engine = create_async_engine(database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)
