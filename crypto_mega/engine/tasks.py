"""Celery app and tasks for distributed heavy computation.

Tasks:
  - run_backtest: Single backtest with fixed params
  - run_grid_search: Grid search over parameter space
  - run_exploration_task: Single exploration task (random strategy+params+symbol)
"""

from __future__ import annotations

import json
import logging
import os
import platform
import time

from celery import Celery
from celery.signals import worker_ready, worker_shutdown

from crypto_mega.config.settings import SystemConfig

logger = logging.getLogger(__name__)

config = SystemConfig()

celery_app = Celery(
    "crypto_mega",
    broker=config.redis.celery_broker_url,
    backend=config.redis.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    task_soft_time_limit=3000,  # soft limit 50 min
    worker_prefetch_multiplier=1,  # fair distribution
    worker_concurrency=config.resources.max_workers,
)


# ─── Worker registration via Celery signals ───

def _get_worker_id() -> str:
    """Generate a stable worker ID from hostname."""
    return f"worker-{platform.node()}"


@worker_ready.connect
def on_worker_ready(**kwargs):
    """Register this worker node in the DB when Celery worker starts."""
    import asyncio
    try:
        asyncio.run(_register_worker())
    except Exception as e:
        logger.warning(f"Worker registration failed (non-fatal): {e}")


@worker_shutdown.connect
def on_worker_shutdown(**kwargs):
    """Mark worker as offline when shutting down."""
    import asyncio
    try:
        asyncio.run(_deregister_worker())
    except Exception as e:
        logger.warning(f"Worker deregistration failed: {e}")


async def _register_worker():
    import socket
    from crypto_mega.data.models import WorkerNodeRecord, init_db
    session_factory = await init_db(config.db.url)
    async with session_factory() as session:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        worker_id = _get_worker_id()
        stmt = pg_insert(WorkerNodeRecord).values(
            id=worker_id,
            hostname=platform.node(),
            ip_address=_get_local_ip(),
            max_workers=config.resources.max_workers,
            status="online",
        ).on_conflict_do_update(
            index_elements=["id"],
            set_={
                "status": "online",
                "max_workers": config.resources.max_workers,
                "last_heartbeat": __import__("datetime").datetime.utcnow(),
            },
        )
        await session.execute(stmt)
        await session.commit()
    logger.info(f"Worker registered: {worker_id}")


async def _deregister_worker():
    from sqlalchemy import update
    from crypto_mega.data.models import WorkerNodeRecord, init_db
    session_factory = await init_db(config.db.url)
    async with session_factory() as session:
        await session.execute(
            update(WorkerNodeRecord)
            .where(WorkerNodeRecord.id == _get_worker_id())
            .values(status="offline")
        )
        await session.commit()
    logger.info(f"Worker deregistered: {_get_worker_id()}")


def _get_local_ip() -> str:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@celery_app.task(bind=True, name="crypto_mega.run_backtest")
def run_backtest_task(self, strategy_name: str, symbols: list[str], timeframes: list[str],
                      parameters: dict, initial_capital: float = 10000.0):
    """Run a single backtest as a Celery task."""
    import asyncio
    return asyncio.run(_run_backtest(strategy_name, symbols, timeframes, parameters, initial_capital))


async def _run_backtest(strategy_name: str, symbols: list[str], timeframes: list[str],
                        parameters: dict, initial_capital: float):
    from crypto_mega.backtester.backtester import Backtester
    from crypto_mega.data.provider import DataProvider
    from crypto_mega.strategies.loader import strategy_loader
    from crypto_mega.utils.types import StrategyConfig, TimeFrame

    strategy_loader.load_directory(config.strategies_dir)
    cls = strategy_loader.get(strategy_name)
    if not cls:
        return {"error": f"Strategy not found: {strategy_name}"}

    cfg = StrategyConfig(
        name=strategy_name,
        symbols=symbols,
        timeframes=[TimeFrame(tf) for tf in timeframes],
        parameters=parameters,
    )

    dp = DataProvider()
    await dp.init_exchange("binance", {"enableRateLimit": True})
    data = await dp.fetch_multi(symbols, timeframes, limit=500)
    await dp.close()

    bt = Backtester(initial_capital=initial_capital)
    strategy = cls(cfg)
    result = bt.run(strategy, data, cfg)

    return {
        "strategy": strategy_name,
        "parameters": parameters,
        "pnl": round(result.total_pnl, 2),
        "pnl_pct": round(result.total_pnl_pct, 2),
        "trades": result.total_trades,
        "win_rate": round(result.win_rate, 1),
        "sharpe": round(result.sharpe_ratio, 2),
        "max_dd": round(result.max_drawdown, 2),
        "profit_factor": round(result.profit_factor, 2),
        "run_time": round(result.run_time_sec, 3),
    }


@celery_app.task(bind=True, name="crypto_mega.run_grid_search")
def run_grid_search_task(self, strategy_name: str, symbols: list[str], timeframes: list[str],
                         param_grid: dict, max_combinations: int | None = None,
                         initial_capital: float = 10000.0):
    """Run grid search as a distributed Celery task."""
    import asyncio
    return asyncio.run(_run_grid_search(
        self, strategy_name, symbols, timeframes, param_grid, max_combinations, initial_capital
    ))


async def _run_grid_search(task, strategy_name: str, symbols: list[str], timeframes: list[str],
                           param_grid: dict, max_combinations: int | None, initial_capital: float):
    import itertools
    from crypto_mega.backtester.backtester import Backtester
    from crypto_mega.data.provider import DataProvider
    from crypto_mega.strategies.loader import strategy_loader
    from crypto_mega.utils.types import StrategyConfig, TimeFrame

    strategy_loader.load_directory(config.strategies_dir)
    cls = strategy_loader.get(strategy_name)
    if not cls:
        return {"error": f"Strategy not found: {strategy_name}"}

    # Fetch data once
    dp = DataProvider()
    await dp.init_exchange("binance", {"enableRateLimit": True})
    data = await dp.fetch_multi(symbols, timeframes, limit=500)
    await dp.close()

    cfg = StrategyConfig(
        name=strategy_name,
        symbols=symbols,
        timeframes=[TimeFrame(tf) for tf in timeframes],
    )

    bt = Backtester(initial_capital=initial_capital)
    results = bt.grid_search(cls, data, cfg, param_grid, max_combinations)

    # Update progress
    task.update_state(state="SUCCESS", meta={"total": len(results)})

    return {
        "strategy": strategy_name,
        "total_combinations": len(results),
        "top_20": [
            {
                "params": r.parameters,
                "pnl": round(r.total_pnl, 2),
                "pnl_pct": round(r.total_pnl_pct, 2),
                "trades": r.total_trades,
                "win_rate": round(r.win_rate, 1),
                "sharpe": round(r.sharpe_ratio, 2),
                "max_dd": round(r.max_drawdown, 2),
                "profit_factor": round(r.profit_factor, 2),
            }
            for r in results[:20]
        ],
    }


# ─── Exploration Task ───

@celery_app.task(bind=True, name="crypto_mega.run_exploration")
def run_exploration_task(
    self,
    task_id: str,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    exchange_id: str,
    parameters: dict,
    initial_capital: float = 10000.0,
):
    """Run a single exploration task: backtest one strategy+params+symbol combo.

    Called by StrategyExplorer via Celery. Results stored back via callback.
    """
    import asyncio
    return asyncio.run(
        _run_exploration(
            task_id, strategy_name, symbol, timeframe,
            exchange_id, parameters, initial_capital,
        )
    )


async def _run_exploration(
    task_id: str,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    exchange_id: str,
    parameters: dict,
    initial_capital: float,
):
    from crypto_mega.backtester.backtester import Backtester
    from crypto_mega.data.models import init_db
    from crypto_mega.data.provider import DataProvider
    from crypto_mega.engine.explorer import StrategyExplorer
    from crypto_mega.strategies.loader import strategy_loader
    from crypto_mega.utils.types import StrategyConfig, TimeFrame

    strategy_loader.load_directory(config.strategies_dir)
    cls = strategy_loader.get(strategy_name)
    if not cls:
        return {"error": f"Strategy not found: {strategy_name}"}

    # Fetch data from the specified exchange
    dp = DataProvider()
    try:
        await dp.init_exchange(exchange_id, {"enableRateLimit": True})
        data = await dp.fetch_multi([symbol], [timeframe], limit=500)
    finally:
        await dp.close()

    if not data:
        return {"error": f"No data for {symbol} {timeframe} on {exchange_id}"}

    cfg = StrategyConfig(
        name=strategy_name,
        symbols=[symbol],
        timeframes=[TimeFrame(timeframe)],
        parameters=parameters,
    )

    bt = Backtester(initial_capital=initial_capital)
    strategy = cls(cfg)
    result = bt.run(strategy, data, cfg)

    result_dict = {
        "task_id": task_id,
        "strategy": strategy_name,
        "symbol": symbol,
        "timeframe": timeframe,
        "exchange_id": exchange_id,
        "parameters": parameters,
        "pnl": round(result.total_pnl, 2),
        "pnl_pct": round(result.total_pnl_pct, 2),
        "trades": result.total_trades,
        "win_rate": round(result.win_rate, 1),
        "sharpe": round(result.sharpe_ratio, 2),
        "max_dd": round(result.max_drawdown, 2),
        "profit_factor": round(result.profit_factor, 2),
        "avg_trade_pnl": round(result.avg_trade_pnl, 2) if result.total_trades > 0 else 0,
        "run_time": round(result.run_time_sec, 3),
    }

    # Store result directly into DB from the worker
    try:
        session_factory = await init_db(config.db.url)
        explorer = StrategyExplorer(session_factory, config.exploration)
        await explorer.store_result(task_id, result_dict)
    except Exception as e:
        logger.error(f"Failed to store exploration result: {e}")

    return result_dict
