"""Market data provider — fetches OHLCV from exchanges via ccxt."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


class DataProvider:
    """Fetches and caches market data from exchanges."""

    def __init__(self):
        self._cache: dict[str, pd.DataFrame] = {}
        self._exchange = None

    async def init_exchange(self, exchange_id: str = "binance", config: dict[str, Any] | None = None):
        """Initialize ccxt exchange (async)."""
        import ccxt.async_support as ccxt_async

        exchange_class = getattr(ccxt_async, exchange_id)
        self._exchange = exchange_class(config or {})
        logger.info(f"Initialized exchange: {exchange_id}")

    async def close(self):
        if self._exchange:
            await self._exchange.close()

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 500,
        since: datetime | None = None,
    ) -> pd.DataFrame:
        """Fetch OHLCV data and return as DataFrame."""
        cache_key = f"{symbol}_{timeframe}_{limit}"

        if cache_key in self._cache:
            cached = self._cache[cache_key]
            age = datetime.utcnow() - cached.iloc[-1]["timestamp"]
            # Refresh if cache is older than 1 timeframe unit
            if age < self._timeframe_to_delta(timeframe):
                logger.debug(f"Cache hit: {symbol} {timeframe} (age={age})")
                return cached

        logger.info(
            f"Fetching OHLCV: {symbol} {timeframe} limit={limit}"
        )
        since_ms = int(since.timestamp() * 1000) if since else None
        raw = await self._exchange.fetch_ohlcv(symbol, timeframe, since=since_ms, limit=limit)

        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        self._cache[cache_key] = df

        last_close = df["close"].iloc[-1] if len(df) > 0 else 0
        logger.info(
            f"Fetched {len(df)} candles: {symbol} {timeframe} | "
            f"last close={last_close:.2f} | "
            f"range=[{df['low'].min():.2f} - {df['high'].max():.2f}]"
        )
        return df

    async def fetch_multi(
        self,
        symbols: list[str],
        timeframes: list[str],
        limit: int = 500,
    ) -> dict[str, pd.DataFrame]:
        """Fetch data for multiple symbol/timeframe combos."""
        tasks = {}
        for symbol in symbols:
            for tf in timeframes:
                key = f"{symbol}_{tf}"
                tasks[key] = self.fetch_ohlcv(symbol, tf, limit)

        results = {}
        for key, coro in tasks.items():
            try:
                results[key] = await coro
            except Exception as e:
                logger.error(f"Failed to fetch {key}: {e}")
        return results

    async def get_ticker(self, symbol: str) -> dict:
        """Get current price ticker."""
        return await self._exchange.fetch_ticker(symbol)

    async def get_available_symbols(self) -> list[str]:
        """Get list of available trading pairs."""
        await self._exchange.load_markets()
        return list(self._exchange.markets.keys())

    @staticmethod
    def _timeframe_to_delta(tf: str) -> timedelta:
        units = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}
        num = int(tf[:-1])
        unit = units.get(tf[-1], "hours")
        return timedelta(**{unit: num})


# Global instance
data_provider = DataProvider()
