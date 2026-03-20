"""Tests for deployment-related components: DB models, config, API imports."""

import os
import pytest
import pytest_asyncio


class TestDatabaseModels:
    def test_models_import(self):
        from crypto_mega.data.models import (
            Base, StrategyRecord, TradeRecord, SignalRecord,
            AlertRecord, BacktestResultRecord,
        )
        assert StrategyRecord.__tablename__ == "strategies"
        assert TradeRecord.__tablename__ == "trades"
        assert SignalRecord.__tablename__ == "signals"
        assert AlertRecord.__tablename__ == "alerts"
        assert BacktestResultRecord.__tablename__ == "backtest_results"

    @pytest.mark.asyncio
    async def test_init_db_sqlite(self):
        """Test DB initialization with SQLite (no PostgreSQL needed)."""
        from crypto_mega.data.models import init_db
        session_maker = await init_db("sqlite+aiosqlite:///test_crypto.db")
        assert session_maker is not None

        # Verify we can create a session and write
        from crypto_mega.data.models import StrategyRecord
        async with session_maker() as session:
            record = StrategyRecord(name="test_strat", description="test")
            session.add(record)
            await session.commit()
            assert record.id is not None

        # Cleanup
        import os
        os.unlink("test_crypto.db")


class TestConfig:
    def test_database_url_rewrite(self):
        """Railway gives postgres:// but SQLAlchemy needs postgresql+asyncpg://"""
        from crypto_mega.config.settings import DatabaseConfig

        # Simulate Railway's DATABASE_URL
        cfg = DatabaseConfig.__new__(DatabaseConfig)
        cfg.url = "postgres://user:pass@host:5432/db"
        cfg.__post_init__()
        assert cfg.url.startswith("postgresql+asyncpg://")

    def test_redis_config(self):
        from crypto_mega.config.settings import RedisConfig
        cfg = RedisConfig()
        assert cfg.celery_broker_url == cfg.url
        assert cfg.celery_result_backend == cfg.url

    def test_system_config_defaults(self):
        from crypto_mega.config.settings import SystemConfig
        cfg = SystemConfig()
        assert cfg.api_port > 0
        assert cfg.api_host == "0.0.0.0"

    def test_risk_config_from_env(self):
        from crypto_mega.config.settings import RiskConfig
        cfg = RiskConfig()
        assert cfg.max_portfolio_risk_pct > 0
        assert cfg.kill_switch_loss_pct > cfg.max_drawdown_pct


class TestCeleryTasks:
    def test_celery_app_import(self):
        from crypto_mega.engine.tasks import celery_app
        assert celery_app.main == "crypto_mega"

    def test_tasks_registered(self):
        from crypto_mega.engine.tasks import run_backtest_task, run_grid_search_task
        assert run_backtest_task.name == "crypto_mega.run_backtest"
        assert run_grid_search_task.name == "crypto_mega.run_grid_search"


class TestAPIImport:
    def test_app_import(self):
        from crypto_mega.api.app import app
        assert app.title == "CryptoMega"

    def test_websocket_routes_exist(self):
        from crypto_mega.api.app import app
        routes = [r.path for r in app.routes]
        assert "/ws/signals" in routes
        assert "/ws/monitor" in routes

    def test_health_route_exists(self):
        from crypto_mega.api.app import app
        routes = [r.path for r in app.routes]
        assert "/health" in routes

    def test_backtest_task_route_exists(self):
        from crypto_mega.api.app import app
        routes = [r.path for r in app.routes]
        assert "/backtest/task/{task_id}" in routes
