"""Global system configuration — reads from environment variables for deployment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DatabaseConfig:
    # Railway injects DATABASE_URL for PostgreSQL plugin
    url: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///crypto_mega.db")

    def __post_init__(self):
        # Railway gives postgres:// but SQLAlchemy needs postgresql://
        if self.url.startswith("postgres://"):
            self.url = self.url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif self.url.startswith("postgresql://") and "+asyncpg" not in self.url:
            self.url = self.url.replace("postgresql://", "postgresql+asyncpg://", 1)


@dataclass
class RedisConfig:
    # Railway injects REDIS_URL for Redis plugin
    url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    @property
    def celery_broker_url(self) -> str:
        return self.url

    @property
    def celery_result_backend(self) -> str:
        return self.url


@dataclass
class ExchangeConfig:
    exchange_id: str = os.getenv("EXCHANGE_ID", "binance")
    api_key: str = os.getenv("EXCHANGE_API_KEY", "")
    api_secret: str = os.getenv("EXCHANGE_API_SECRET", "")
    sandbox: bool = os.getenv("EXCHANGE_SANDBOX", "true").lower() == "true"
    rate_limit: int = 1200  # ms between requests


@dataclass
class ResourceConfig:
    max_workers: int = int(os.getenv("MAX_WORKERS", "4"))
    max_strategies_parallel: int = int(os.getenv("MAX_STRATEGIES", "10"))
    default_priority: int = 50  # 0-100, higher = more resources
    rebalance_interval_sec: int = 300  # how often to rebalance compute


@dataclass
class RiskConfig:
    max_portfolio_risk_pct: float = float(os.getenv("MAX_RISK_PCT", "2.0"))
    max_drawdown_pct: float = float(os.getenv("MAX_DRAWDOWN_PCT", "10.0"))
    max_position_size_pct: float = float(os.getenv("MAX_POSITION_PCT", "5.0"))
    max_open_positions: int = int(os.getenv("MAX_POSITIONS", "20"))
    max_daily_trades: int = int(os.getenv("MAX_DAILY_TRADES", "100"))
    kill_switch_loss_pct: float = float(os.getenv("KILL_SWITCH_PCT", "15.0"))


@dataclass
class CollectorConfig:
    # Which symbols to collect
    symbols: list[str] = field(
        default_factory=lambda: [s.strip() for s in os.getenv("COLLECTOR_SYMBOLS", "BTC/USDT,ETH/USDT").split(",")]
    )
    # Which timeframes to collect (configurable on the fly)
    timeframes: list[str] = field(
        default_factory=lambda: [t.strip() for t in os.getenv("COLLECTOR_TIMEFRAMES", "1m,5m,15m,1h,4h,1d").split(",")]
    )
    # How often to fetch new candles (seconds)
    interval_sec: float = float(os.getenv("COLLECTOR_INTERVAL", "10"))
    # How many candles to fetch per request
    candle_limit: int = int(os.getenv("COLLECTOR_CANDLE_LIMIT", "500"))
    # How long to keep candles (days)
    retention_days: int = int(os.getenv("COLLECTOR_RETENTION_DAYS", "90"))


@dataclass
class SystemConfig:
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    exchanges: list[ExchangeConfig] = field(default_factory=lambda: [ExchangeConfig()])
    resources: ResourceConfig = field(default_factory=ResourceConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    collector: CollectorConfig = field(default_factory=CollectorConfig)
    strategies_dir: Path = Path(os.getenv("STRATEGIES_DIR", "strategies_user"))
    data_dir: Path = Path("data")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    api_port: int = int(os.getenv("PORT", "8000"))  # Railway sets PORT
    api_host: str = os.getenv("HOST", "0.0.0.0")
