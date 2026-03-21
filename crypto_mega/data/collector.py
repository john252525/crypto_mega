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

from sqlalchemy import select, delete, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from crypto_mega.data.models import CandleRecord
from crypto_mega.data.provider import DataProvider

logger = logging.getLogger(__name__)

# How often each timeframe should be re-fetched (seconds).
# No point hammering the exchange for 1d candles every 10 seconds.
_TF_INTERVALS: dict[str, float] = {
    "1m": 15,
    "3m": 45,
    "5m": 60,
    "15m": 300,
    "30m": 600,
    "1h": 900,
    "2h": 1800,
    "4h": 3600,
    "6h": 3600,
    "8h": 3600,
    "12h": 3600,
    "1d": 3600,
    "3d": 7200,
    "1w": 14400,
}

# How many candles to fetch on regular updates vs initial backfill.
_TF_UPDATE_LIMIT: dict[str, int] = {
    "1m": 10,
    "3m": 10,
    "5m": 10,
    "15m": 5,
    "30m": 5,
    "1h": 5,
    "2h": 3,
    "4h": 3,
    "6h": 3,
    "8h": 3,
    "12h": 3,
    "1d": 3,
    "3d": 3,
    "1w": 3,
}


class CandleCollector:
    """Fetches candles from exchange and upserts into the database.

    Smart collection: each timeframe has its own fetch interval and limit.
    Only updates collected_at when candle data actually changes.
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
        self.candle_limit = candle_limit  # used for initial backfill
        self.retention_days = retention_days
        self._running = False
        self._stats: dict[str, dict] = {}
        # Track last fetch time per symbol+timeframe to respect per-TF intervals
        self._last_fetch: dict[str, float] = {}
        # Track which pairs have done initial backfill
        self._backfilled: set[str] = set()

    async def collect_once(self) -> dict[str, int]:
        """Fetch symbol/timeframe combos that are due for collection.

        Respects per-timeframe intervals — won't re-fetch 1d candles every 10s.
        Returns dict of {key: rows_upserted}.
        """
        results = {}
        now = time.time()

        for symbol in self.symbols:
            for tf in self.timeframes:
                key = f"{symbol}_{tf}"
                interval = _TF_INTERVALS.get(tf, self.collect_interval)

                # Skip if not enough time has passed since last fetch
                last = self._last_fetch.get(key, 0)
                if now - last < interval:
                    continue

                try:
                    t0 = time.time()
                    # Use large limit for backfill, small for updates
                    if key not in self._backfilled:
                        limit = self.candle_limit
                    else:
                        limit = _TF_UPDATE_LIMIT.get(tf, 10)

                    count = await self._collect_pair(symbol, tf, limit)
                    elapsed = time.time() - t0
                    self._last_fetch[key] = now

                    if key not in self._backfilled:
                        self._backfilled.add(key)
                        logger.info(
                            f"Backfilled {count} candles: {key} ({elapsed:.2f}s)"
                        )

                    results[key] = count
                    self._stats[key] = {
                        "last_collect": datetime.utcnow().isoformat(),
                        "rows_upserted": count,
                        "elapsed_sec": round(elapsed, 3),
                        "interval_sec": interval,
                        "errors": 0,
                    }
                    if count > 0 and key in self._backfilled:
                        logger.debug(f"Updated {count} candles: {key} ({elapsed:.2f}s)")
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

    async def _collect_pair(self, symbol: str, timeframe: str, limit: int) -> int:
        """Fetch candles for one symbol/timeframe and upsert into DB."""
        df = await self.data_provider.fetch_ohlcv(
            symbol, timeframe, limit=limit
        )

        if df.empty:
            return 0

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
        """PostgreSQL INSERT ... ON CONFLICT DO UPDATE.

        Only updates collected_at when actual OHLCV data changes (new candle
        or incomplete candle finalized). This keeps collected_at meaningful —
        it reflects when the data *last changed*, not when we last checked.
        """
        stmt = pg_insert(CandleRecord).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_candle",
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                # Only bump collected_at if data actually changed
                "collected_at": text(
                    "CASE WHEN "
                    "candles.close != EXCLUDED.close OR "
                    "candles.volume != EXCLUDED.volume OR "
                    "candles.high != EXCLUDED.high OR "
                    "candles.low != EXCLUDED.low "
                    "THEN now() "
                    "ELSE candles.collected_at END"
                ),
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
                if (record.close != row["close"] or record.volume != row["volume"]
                        or record.high != row["high"] or record.low != row["low"]):
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
        """Main collector loop. Smart intervals per timeframe."""
        self._running = True
        cycle = 0
        cleanup_interval = 3600
        last_cleanup = 0

        tf_intervals_str = ", ".join(
            f"{tf}={_TF_INTERVALS.get(tf, self.collect_interval)}s"
            for tf in self.timeframes
        )
        logger.info(
            f"CandleCollector started | "
            f"symbols={self.symbols} | "
            f"intervals: {tf_intervals_str} | "
            f"backfill_limit={self.candle_limit}"
        )

        while self._running:
            cycle += 1
            try:
                t0 = time.time()
                results = await self.collect_once()
                elapsed = time.time() - t0

                if results:
                    total = sum(results.values())
                    fetched_pairs = len(results)
                    logger.info(
                        f"Collector cycle #{cycle} | "
                        f"{fetched_pairs} pairs fetched | "
                        f"{total} rows upserted | {elapsed:.2f}s"
                    )

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
