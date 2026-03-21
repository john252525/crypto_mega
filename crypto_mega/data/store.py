"""CandleStore — reads candles from the local database for strategies.

This replaces direct exchange API calls. Strategies call CandleStore
instead of DataProvider to get their data.

    CandleStore.fetch_ohlcv("BTC/USDT", "1h", limit=500)
    -> reads from PostgreSQL candles table
    -> returns same DataFrame format as DataProvider
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from crypto_mega.data.models import CandleRecord

logger = logging.getLogger(__name__)


class CandleStore:
    """Reads candles from the database. Drop-in replacement for DataProvider
    in the strategy execution pipeline."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 500,
        since: datetime | None = None,
    ) -> pd.DataFrame:
        """Read candles from DB. Returns DataFrame with same columns as DataProvider."""
        since_ms = int(since.timestamp() * 1000) if since else None

        async with self.session_factory() as session:
            stmt = (
                select(CandleRecord)
                .where(
                    CandleRecord.symbol == symbol,
                    CandleRecord.timeframe == timeframe,
                )
            )
            if since_ms:
                stmt = stmt.where(CandleRecord.timestamp_ms >= since_ms)

            stmt = stmt.order_by(CandleRecord.timestamp_ms.desc()).limit(limit)
            result = await session.execute(stmt)
            records = result.scalars().all()

        if not records:
            logger.warning(f"No candles in DB for {symbol} {timeframe}")
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

        # Convert to DataFrame (reverse to chronological order)
        rows = [
            {
                "timestamp": pd.Timestamp(r.timestamp_ms, unit="ms"),
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in reversed(records)
        ]
        df = pd.DataFrame(rows)
        logger.debug(f"DB read: {symbol} {timeframe} -> {len(df)} candles")
        return df

    async def fetch_multi(
        self,
        symbols: list[str],
        timeframes: list[str],
        limit: int = 500,
    ) -> dict[str, pd.DataFrame]:
        """Read multiple symbol/timeframe combos from DB.
        Same interface as DataProvider.fetch_multi."""
        results = {}
        for symbol in symbols:
            for tf in timeframes:
                key = f"{symbol}_{tf}"
                try:
                    df = await self.fetch_ohlcv(symbol, tf, limit)
                    if not df.empty:
                        results[key] = df
                    else:
                        logger.warning(f"No data in DB for {key}, skipping")
                except Exception as e:
                    logger.error(f"DB read error for {key}: {e}")
        return results

    async def get_latest_timestamp(self, symbol: str, timeframe: str) -> int | None:
        """Get the latest candle timestamp for a symbol/timeframe pair.
        Useful for checking data freshness."""
        async with self.session_factory() as session:
            stmt = (
                select(CandleRecord.timestamp_ms)
                .where(
                    CandleRecord.symbol == symbol,
                    CandleRecord.timeframe == timeframe,
                )
                .order_by(CandleRecord.timestamp_ms.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return row

    async def get_candle_count(self, symbol: str | None = None, timeframe: str | None = None) -> int:
        """Count candles in DB, optionally filtered."""
        from sqlalchemy import func
        async with self.session_factory() as session:
            stmt = select(func.count(CandleRecord.id))
            if symbol:
                stmt = stmt.where(CandleRecord.symbol == symbol)
            if timeframe:
                stmt = stmt.where(CandleRecord.timeframe == timeframe)
            result = await session.execute(stmt)
            return result.scalar_one()

    async def get_available_pairs(self) -> list[dict]:
        """List all symbol/timeframe pairs available in the DB with their candle count."""
        from sqlalchemy import func
        async with self.session_factory() as session:
            stmt = (
                select(
                    CandleRecord.symbol,
                    CandleRecord.timeframe,
                    func.count(CandleRecord.id).label("count"),
                    func.min(CandleRecord.timestamp_ms).label("first_ts"),
                    func.max(CandleRecord.timestamp_ms).label("last_ts"),
                )
                .group_by(CandleRecord.symbol, CandleRecord.timeframe)
                .order_by(CandleRecord.symbol, CandleRecord.timeframe)
            )
            result = await session.execute(stmt)
            rows = result.all()

        return [
            {
                "symbol": r.symbol,
                "timeframe": r.timeframe,
                "candle_count": r.count,
                "first": datetime.utcfromtimestamp(r.first_ts / 1000).isoformat(),
                "last": datetime.utcfromtimestamp(r.last_ts / 1000).isoformat(),
            }
            for r in rows
        ]
