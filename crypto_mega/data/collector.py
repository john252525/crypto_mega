"""CandleCollector — single process that fetches candles from exchange and writes to DB.

Only ONE instance of this runs. All strategies read from the DB instead of hitting the exchange.

Architecture:
    Exchange API  ──[CandleCollector]──>  PostgreSQL (candles table)
                                              ↓
                                    Strategy 1, 2, ... N  (read from DB)
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta

from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from crypto_mega.data.models import CandleRecord
from crypto_mega.data.provider import DataProvider

logger = logging.getLogger(__name__)


class CandleCollector:
    """Fetches candles from exchange and upserts into the database.

    Runs as a standalone loop. Configurable symbols, timeframes, and interval.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        data_provider: DataProvider,
        symbols: list[str],
        timeframes: list[str],
        collect_interval: float = 10.0,
        candle_limit: int = 500,
        retention_days: int = 90,
    ):
        self.session_factory = session_factory
        self.data_provider = data_provider
        self.symbols = symbols
        self.timeframes = timeframes
        self.collect_interval = collect_interval
        self.candle_limit = candle_limit
        self.retention_days = retention_days
        self._running = False
        self._stats: dict[str, dict] = {}

    async def collect_once(self) -> dict[str, int]:
        """Fetch all symbol/timeframe combos from exchange and write to DB.

        Returns dict of {key: rows_upserted}.
        """
        results = {}

        for symbol in self.symbols:
            for tf in self.timeframes:
                key = f"{symbol}_{tf}"
                try:
                    t0 = time.time()
                    count = await self._collect_pair(symbol, tf)
                    elapsed = time.time() - t0
                    results[key] = count
                    self._stats[key] = {
                        "last_collect": datetime.utcnow().isoformat(),
                        "rows_upserted": count,
                        "elapsed_sec": round(elapsed, 3),
                        "errors": 0,
                    }
                    if count > 0:
                        logger.info(f"Collected {count} candles: {key} ({elapsed:.2f}s)")
                    else:
                        logger.debug(f"No new candles: {key}")
                except Exception as e:
                    logger.error(f"Failed to collect {key}: {e}")
                    prev_errors = self._stats.get(key, {}).get("errors", 0)
                    self._stats[key] = {
                        "last_collect": datetime.utcnow().isoformat(),
                        "rows_upserted": 0,
                        "error": str(e),
                        "errors": prev_errors + 1,
                    }

        return results

    async def _collect_pair(self, symbol: str, timeframe: str) -> int:
        """Fetch candles for one symbol/timeframe and upsert into DB."""
        # Fetch from exchange (via DataProvider — uses ccxt)
        df = await self.data_provider.fetch_ohlcv(
            symbol, timeframe, limit=self.candle_limit
        )

        if df.empty:
            return 0

        # Prepare rows for bulk upsert
        rows = []
        for _, row in df.iterrows():
            ts = row["timestamp"]
            if hasattr(ts, "timestamp"):
                ts_ms = int(ts.timestamp() * 1000)
            else:
                ts_ms = int(ts)

            rows.append({
                "symbol": symbol,
                "timeframe": timeframe,
                "timestamp_ms": ts_ms,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            })

        # Upsert: insert new candles, update existing ones (last candle may be incomplete)
        async with self.session_factory() as session:
            upserted = await self._upsert_candles(session, rows)
            await session.commit()

        return upserted

    async def _upsert_candles(self, session: AsyncSession, rows: list[dict]) -> int:
        """Bulk upsert candles. Uses DB-specific ON CONFLICT for PostgreSQL,
        falls back to merge-style for SQLite."""
        if not rows:
            return 0

        bind = session.get_bind()
        dialect = bind.dialect.name if bind else ""

        if dialect == "postgresql":
            return await self._upsert_pg(session, rows)
        else:
            return await self._upsert_generic(session, rows)

    async def _upsert_pg(self, session: AsyncSession, rows: list[dict]) -> int:
        """PostgreSQL INSERT ... ON CONFLICT DO UPDATE."""
        stmt = pg_insert(CandleRecord).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_candle",
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "collected_at": stmt.excluded.collected_at,
            },
        )
        result = await session.execute(stmt)
        return result.rowcount

    async def _upsert_generic(self, session: AsyncSession, rows: list[dict]) -> int:
        """Generic upsert for SQLite — check existence, then insert or update."""
        count = 0
        for row in rows:
            existing = await session.execute(
                select(CandleRecord).where(
                    CandleRecord.symbol == row["symbol"],
                    CandleRecord.timeframe == row["timeframe"],
                    CandleRecord.timestamp_ms == row["timestamp_ms"],
                )
            )
            record = existing.scalar_one_or_none()
            if record:
                # Update if price changed (incomplete candle got finalized)
                if record.close != row["close"] or record.volume != row["volume"]:
                    record.open = row["open"]
                    record.high = row["high"]
                    record.low = row["low"]
                    record.close = row["close"]
                    record.volume = row["volume"]
                    count += 1
            else:
                session.add(CandleRecord(**row))
                count += 1
        return count

    async def cleanup_old_candles(self) -> int:
        """Delete candles older than retention_days."""
        cutoff_ms = int((datetime.utcnow() - timedelta(days=self.retention_days)).timestamp() * 1000)
        async with self.session_factory() as session:
            result = await session.execute(
                delete(CandleRecord).where(CandleRecord.timestamp_ms < cutoff_ms)
            )
            await session.commit()
            deleted = result.rowcount
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} candles older than {self.retention_days} days")
            return deleted

    async def run_loop(self):
        """Main collector loop. Runs forever, collecting candles at configured interval."""
        self._running = True
        cycle = 0
        cleanup_interval = 3600  # cleanup old candles every hour
        last_cleanup = 0

        logger.info(
            f"CandleCollector started | "
            f"symbols={self.symbols} | "
            f"timeframes={self.timeframes} | "
            f"interval={self.collect_interval}s"
        )

        while self._running:
            cycle += 1
            try:
                t0 = time.time()
                results = await self.collect_once()
                elapsed = time.time() - t0
                total = sum(results.values())

                logger.info(
                    f"Collector cycle #{cycle} done in {elapsed:.2f}s | "
                    f"{total} candles upserted across {len(results)} pairs"
                )

                # Periodic cleanup
                if time.time() - last_cleanup > cleanup_interval:
                    await self.cleanup_old_candles()
                    last_cleanup = time.time()

            except Exception as e:
                logger.error(f"Collector cycle #{cycle} error: {e}")

            await asyncio.sleep(self.collect_interval)

    def stop(self):
        self._running = False
        logger.info("CandleCollector stopped")

    def get_stats(self) -> dict:
        """Return collection stats for monitoring."""
        return {
            "running": self._running,
            "symbols": self.symbols,
            "timeframes": self.timeframes,
            "interval_sec": self.collect_interval,
            "pairs": self._stats,
        }
