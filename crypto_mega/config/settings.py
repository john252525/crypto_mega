"""Global system configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DatabaseConfig:
    url: str = "sqlite+aiosqlite:///crypto_mega.db"


@dataclass
class RedisConfig:
    host: str = os.getenv("REDIS_HOST", "localhost")
    port: int = int(os.getenv("REDIS_PORT", "6379"))
    db: int = 0

    @property
    def url(self) -> str:
        return f"redis://{self.host}:{self.port}/{self.db}"


@dataclass
class ExchangeConfig:
    exchange_id: str = "binance"
    api_key: str = ""
    api_secret: str = ""
    sandbox: bool = True  # ALWAYS start in sandbox/testnet
    rate_limit: int = 1200  # ms between requests


@dataclass
class ResourceConfig:
    max_workers: int = int(os.getenv("MAX_WORKERS", "4"))
    max_strategies_parallel: int = int(os.getenv("MAX_STRATEGIES", "10"))
    default_priority: int = 50  # 0-100, higher = more resources
    rebalance_interval_sec: int = 300  # how often to rebalance compute


@dataclass
class RiskConfig:
    max_portfolio_risk_pct: float = 2.0  # max % of portfolio at risk per trade
    max_drawdown_pct: float = 10.0  # pause trading if drawdown exceeds this
    max_position_size_pct: float = 5.0  # max % of portfolio in single position
    max_open_positions: int = 20
    max_daily_trades: int = 100
    kill_switch_loss_pct: float = 15.0  # emergency stop


@dataclass
class SystemConfig:
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    exchanges: list[ExchangeConfig] = field(default_factory=lambda: [ExchangeConfig()])
    resources: ResourceConfig = field(default_factory=ResourceConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    strategies_dir: Path = Path("strategies_user")
    data_dir: Path = Path("data")
    log_level: str = "INFO"
