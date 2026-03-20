"""Celery app and tasks for distributed heavy computation (backtesting, grid search)."""

from __future__ import annotations

import json
import logging
import os

from celery import Celery

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
