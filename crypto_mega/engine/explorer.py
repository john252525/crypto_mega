"""StrategyExplorer — generates random strategy/params/symbol combinations for distributed testing.

This is the core of the "brute-force alpha discovery" approach:
1. Load all available strategies with their param_grids
2. Get all available symbols from connected exchanges
3. Generate random (strategy, params, symbol, timeframe) combinations
4. Push each combo as a Celery task for workers to execute
5. Collect results into exploration_results table
6. Auto-promote winners that pass quality thresholds

The key insight: we don't need to test everything — we randomly sample
the enormous search space, and the more compute we add, the more we sample.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import datetime, timedelta

from sqlalchemy import select, func as sa_func, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from crypto_mega.config.settings import ExplorationConfig
from crypto_mega.data.models import (
    ExplorationTaskRecord,
    ExplorationResultRecord,
    WorkerNodeRecord,
)
from crypto_mega.strategies.loader import strategy_loader

logger = logging.getLogger(__name__)


class StrategyExplorer:
    """Generates and manages distributed strategy exploration tasks.

    Usage:
        explorer = StrategyExplorer(session_factory, config)
        await explorer.start()  # runs forever, generating tasks
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        config: ExplorationConfig,
    ):
        self.session_factory = session_factory
        self.config = config
        self._running = False
        self._available_symbols: dict[str, list[str]] = {}  # exchange_id -> [symbols]
        self._stats = {
            "tasks_generated": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "results_promoted": 0,
            "last_generation": None,
        }

    async def discover_symbols(self, exchange_id: str) -> list[str]:
        """Discover top symbols from an exchange by volume.
        Returns USDT pairs sorted by 24h volume descending."""
        import ccxt.async_support as ccxt_async

        if not hasattr(ccxt_async, exchange_id):
            logger.warning(f"Exchange {exchange_id} not in ccxt, skipping")
            return []

        exchange_class = getattr(ccxt_async, exchange_id)
        ex = exchange_class({"enableRateLimit": True})

        try:
            await ex.load_markets()
            # Filter USDT spot pairs that are active
            usdt_pairs = [
                symbol for symbol, market in ex.markets.items()
                if (market.get("quote") == "USDT"
                    and market.get("active", True)
                    and market.get("spot", True)
                    and "/" in symbol)
            ]

            # Try to sort by volume if tickers available
            try:
                tickers = await ex.fetch_tickers(usdt_pairs[:200])
                # Sort by quote volume (USDT volume)
                sorted_pairs = sorted(
                    usdt_pairs,
                    key=lambda s: tickers.get(s, {}).get("quoteVolume", 0) or 0,
                    reverse=True,
                )
            except Exception:
                # Fallback: just take what we have
                sorted_pairs = usdt_pairs

            result = sorted_pairs[: self.config.symbols_per_exchange]
            logger.info(
                f"Discovered {len(result)} symbols from {exchange_id} "
                f"(out of {len(usdt_pairs)} USDT pairs)"
            )
            return result

        except Exception as e:
            logger.error(f"Failed to discover symbols from {exchange_id}: {e}")
            return []
        finally:
            await ex.close()

    async def refresh_symbols(self) -> None:
        """Refresh available symbols from all configured exchanges."""
        for exchange_id in self.config.exchanges:
            symbols = await self.discover_symbols(exchange_id)
            if symbols:
                self._available_symbols[exchange_id] = symbols

    def _generate_random_task(self) -> dict | None:
        """Generate one random (strategy, params, symbol, timeframe, exchange) combination."""
        strategies = strategy_loader.list_all()
        if not strategies:
            return None

        if not self._available_symbols:
            return None

        # Pick random strategy
        strategy_name = random.choice(list(strategies.keys()))
        strategy_cls = strategies[strategy_name]

        # Get param grid and sample random params
        try:
            from crypto_mega.utils.types import StrategyConfig
            instance = strategy_cls(StrategyConfig(name=strategy_name))
            grid = instance.param_grid()
        except Exception:
            grid = {}

        if grid:
            params = {k: random.choice(v) for k, v in grid.items()}
        else:
            params = {}

        # Pick random exchange + symbol
        exchange_id = random.choice(list(self._available_symbols.keys()))
        symbols = self._available_symbols[exchange_id]
        symbol = random.choice(symbols)

        # Pick random timeframe
        timeframe = random.choice(self.config.timeframes)

        return {
            "strategy_name": strategy_name,
            "symbol": symbol,
            "timeframe": timeframe,
            "exchange_id": exchange_id,
            "parameters": json.dumps(params),
        }

    async def generate_batch(self, count: int | None = None) -> int:
        """Generate a batch of random exploration tasks and insert into DB.

        Returns number of tasks created.
        """
        if count is None:
            # Fill up to queue_size
            async with self.session_factory() as session:
                pending = await session.execute(
                    select(sa_func.count(ExplorationTaskRecord.id)).where(
                        ExplorationTaskRecord.status.in_(["pending", "running"])
                    )
                )
                active_count = pending.scalar() or 0
                count = max(0, self.config.queue_size - active_count)

        if count <= 0:
            return 0

        tasks = []
        for _ in range(count):
            task_data = self._generate_random_task()
            if task_data:
                tasks.append(task_data)

        if not tasks:
            return 0

        async with self.session_factory() as session:
            for t in tasks:
                session.add(ExplorationTaskRecord(**t))
            await session.commit()

        self._stats["tasks_generated"] += len(tasks)
        self._stats["last_generation"] = datetime.utcnow().isoformat()
        logger.info(f"Generated {len(tasks)} exploration tasks")
        return len(tasks)

    async def dispatch_tasks(self) -> int:
        """Take pending tasks from DB and dispatch to Celery workers.

        Returns number of tasks dispatched.
        """
        from crypto_mega.engine.tasks import run_exploration_task

        async with self.session_factory() as session:
            # Count running tasks
            running = await session.execute(
                select(sa_func.count(ExplorationTaskRecord.id)).where(
                    ExplorationTaskRecord.status == "running"
                )
            )
            running_count = running.scalar() or 0

            slots = max(0, self.config.max_concurrent - running_count)
            if slots <= 0:
                return 0

            # Grab pending tasks
            stmt = (
                select(ExplorationTaskRecord)
                .where(ExplorationTaskRecord.status == "pending")
                .order_by(ExplorationTaskRecord.created_at)
                .limit(slots)
            )
            result = await session.execute(stmt)
            pending_tasks = result.scalars().all()

            dispatched = 0
            for task in pending_tasks:
                try:
                    celery_result = run_exploration_task.delay(
                        task_id=task.id,
                        strategy_name=task.strategy_name,
                        symbol=task.symbol,
                        timeframe=task.timeframe,
                        exchange_id=task.exchange_id,
                        parameters=json.loads(task.parameters),
                    )
                    task.status = "running"
                    task.celery_task_id = celery_result.id
                    task.started_at = datetime.utcnow()
                    dispatched += 1
                except Exception as e:
                    logger.error(f"Failed to dispatch task {task.id}: {e}")
                    task.status = "failed"

            await session.commit()

        if dispatched:
            logger.info(f"Dispatched {dispatched} exploration tasks to workers")
        return dispatched

    async def store_result(
        self,
        task_id: str,
        result: dict,
    ) -> None:
        """Store exploration result and mark task as done."""
        async with self.session_factory() as session:
            # Update task status
            await session.execute(
                update(ExplorationTaskRecord)
                .where(ExplorationTaskRecord.id == task_id)
                .values(status="done", finished_at=datetime.utcnow())
            )

            # Insert result
            rec = ExplorationResultRecord(
                task_id=task_id,
                strategy_name=result.get("strategy", ""),
                symbol=result.get("symbol", ""),
                timeframe=result.get("timeframe", ""),
                exchange_id=result.get("exchange_id", ""),
                parameters=json.dumps(result.get("parameters", {})),
                total_trades=result.get("trades", 0),
                total_pnl=result.get("pnl", 0),
                total_pnl_pct=result.get("pnl_pct", 0),
                max_drawdown=result.get("max_dd", 0),
                sharpe_ratio=result.get("sharpe", 0),
                win_rate=result.get("win_rate", 0),
                profit_factor=result.get("profit_factor", 0),
                avg_trade_pnl_pct=result.get("avg_trade_pnl", 0),
                run_time_sec=result.get("run_time", 0),
            )
            session.add(rec)
            await session.commit()

        self._stats["tasks_completed"] += 1

    async def mark_failed(self, task_id: str, error: str) -> None:
        """Mark a task as failed."""
        async with self.session_factory() as session:
            await session.execute(
                update(ExplorationTaskRecord)
                .where(ExplorationTaskRecord.id == task_id)
                .values(status="failed", finished_at=datetime.utcnow())
            )
            await session.commit()
        self._stats["tasks_failed"] += 1

    async def check_promotions(self) -> list[dict]:
        """Find exploration results that pass promotion thresholds.

        Returns list of results that qualify for paper trading.
        """
        cfg = self.config
        async with self.session_factory() as session:
            stmt = (
                select(ExplorationResultRecord)
                .where(
                    ExplorationResultRecord.promoted == False,  # noqa: E712
                    ExplorationResultRecord.total_trades >= cfg.promote_min_trades,
                    ExplorationResultRecord.sharpe_ratio >= cfg.promote_min_sharpe,
                    ExplorationResultRecord.win_rate >= cfg.promote_min_win_rate,
                    ExplorationResultRecord.profit_factor >= cfg.promote_min_profit_factor,
                )
                .order_by(ExplorationResultRecord.sharpe_ratio.desc())
                .limit(20)
            )
            result = await session.execute(stmt)
            candidates = result.scalars().all()

            promoted = []
            for c in candidates:
                c.promoted = True
                promoted.append({
                    "id": c.id,
                    "strategy": c.strategy_name,
                    "symbol": c.symbol,
                    "timeframe": c.timeframe,
                    "exchange": c.exchange_id,
                    "params": json.loads(c.parameters),
                    "sharpe": c.sharpe_ratio,
                    "win_rate": c.win_rate,
                    "pnl_pct": c.total_pnl_pct,
                    "profit_factor": c.profit_factor,
                    "trades": c.total_trades,
                })

            if promoted:
                await session.commit()
                self._stats["results_promoted"] += len(promoted)
                logger.info(
                    f"Promoted {len(promoted)} exploration results to paper trading"
                )

        return promoted

    async def get_leaderboard(
        self,
        limit: int = 50,
        sort_by: str = "sharpe_ratio",
        min_trades: int | None = None,
    ) -> list[dict]:
        """Get exploration results leaderboard."""
        min_t = min_trades or self.config.min_trades
        valid_sorts = {
            "sharpe_ratio", "total_pnl_pct", "win_rate",
            "profit_factor", "total_trades",
        }
        sort_col = sort_by if sort_by in valid_sorts else "sharpe_ratio"

        async with self.session_factory() as session:
            stmt = (
                select(ExplorationResultRecord)
                .where(ExplorationResultRecord.total_trades >= min_t)
                .order_by(getattr(ExplorationResultRecord, sort_col).desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()

        return [
            {
                "id": r.id,
                "strategy": r.strategy_name,
                "symbol": r.symbol,
                "timeframe": r.timeframe,
                "exchange": r.exchange_id,
                "params": json.loads(r.parameters),
                "trades": r.total_trades,
                "pnl_pct": round(r.total_pnl_pct, 2),
                "sharpe": round(r.sharpe_ratio, 2),
                "win_rate": round(r.win_rate, 1),
                "profit_factor": round(r.profit_factor, 2),
                "max_dd": round(r.max_drawdown, 2),
                "promoted": r.promoted,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    async def get_stats(self) -> dict:
        """Get exploration system statistics."""
        async with self.session_factory() as session:
            # Task counts by status
            for status in ["pending", "running", "done", "failed"]:
                count = await session.execute(
                    select(sa_func.count(ExplorationTaskRecord.id)).where(
                        ExplorationTaskRecord.status == status
                    )
                )
                self._stats[f"tasks_{status}"] = count.scalar() or 0

            # Total results
            total_results = await session.execute(
                select(sa_func.count(ExplorationResultRecord.id))
            )
            self._stats["total_results"] = total_results.scalar() or 0

            # Unique strategies tested
            unique_strats = await session.execute(
                select(sa_func.count(sa_func.distinct(ExplorationResultRecord.strategy_name)))
            )
            self._stats["unique_strategies"] = unique_strats.scalar() or 0

            # Unique symbols tested
            unique_symbols = await session.execute(
                select(sa_func.count(sa_func.distinct(ExplorationResultRecord.symbol)))
            )
            self._stats["unique_symbols"] = unique_symbols.scalar() or 0

            # Promoted count
            promoted = await session.execute(
                select(sa_func.count(ExplorationResultRecord.id)).where(
                    ExplorationResultRecord.promoted == True  # noqa: E712
                )
            )
            self._stats["total_promoted"] = promoted.scalar() or 0

            # Best result
            best = await session.execute(
                select(ExplorationResultRecord)
                .where(ExplorationResultRecord.total_trades >= self.config.min_trades)
                .order_by(ExplorationResultRecord.sharpe_ratio.desc())
                .limit(1)
            )
            best_row = best.scalars().first()
            if best_row:
                self._stats["best_result"] = {
                    "strategy": best_row.strategy_name,
                    "symbol": best_row.symbol,
                    "sharpe": round(best_row.sharpe_ratio, 2),
                    "pnl_pct": round(best_row.total_pnl_pct, 2),
                }

            # Worker info
            workers = await session.execute(
                select(WorkerNodeRecord).where(WorkerNodeRecord.status == "online")
            )
            online_workers = workers.scalars().all()
            self._stats["workers_online"] = len(online_workers)
            self._stats["total_worker_capacity"] = sum(w.max_workers for w in online_workers)

        self._stats["available_symbols"] = {
            ex: len(syms) for ex, syms in self._available_symbols.items()
        }
        self._stats["running"] = self._running

        return dict(self._stats)

    async def cleanup_stale_tasks(self, timeout_minutes: int = 30) -> int:
        """Reset tasks that have been running too long (worker probably died)."""
        cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        async with self.session_factory() as session:
            result = await session.execute(
                update(ExplorationTaskRecord)
                .where(
                    ExplorationTaskRecord.status == "running",
                    ExplorationTaskRecord.started_at < cutoff,
                )
                .values(status="pending", worker_id="", celery_task_id="")
            )
            await session.commit()
            count = result.rowcount
            if count:
                logger.warning(f"Reset {count} stale exploration tasks")
            return count

    async def run_loop(self) -> None:
        """Main explorer loop: generate tasks, dispatch, check promotions."""
        self._running = True
        logger.info("StrategyExplorer started")

        # Initial symbol discovery
        await self.refresh_symbols()
        if not self._available_symbols:
            logger.warning("No symbols discovered, explorer will wait for symbols...")

        cycle = 0
        symbol_refresh_interval = 3600  # re-discover symbols every hour
        last_symbol_refresh = time.time()
        promotion_check_interval = 300  # check promotions every 5 min
        last_promotion_check = 0

        while self._running:
            cycle += 1
            try:
                # Refresh symbols periodically
                if time.time() - last_symbol_refresh > symbol_refresh_interval:
                    await self.refresh_symbols()
                    last_symbol_refresh = time.time()

                if self._available_symbols:
                    # Generate new tasks to fill the queue
                    generated = await self.generate_batch()

                    # Dispatch pending tasks to Celery workers
                    dispatched = await self.dispatch_tasks()

                    # Cleanup stale tasks
                    await self.cleanup_stale_tasks()

                    if generated or dispatched:
                        logger.info(
                            f"Explorer cycle #{cycle}: generated={generated}, dispatched={dispatched}"
                        )

                # Check for promotions periodically
                if time.time() - last_promotion_check > promotion_check_interval:
                    promoted = await self.check_promotions()
                    last_promotion_check = time.time()

            except Exception as e:
                logger.error(f"Explorer cycle #{cycle} error: {e}")

            await asyncio.sleep(self.config.generation_interval)

    def stop(self) -> None:
        self._running = False
        logger.info("StrategyExplorer stopped")
