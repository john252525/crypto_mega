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

    # Exchanges to try in order if the primary one fails (geo-blocked, etc.)
    FALLBACK_EXCHANGES = ["bybit", "binanceus", "okx", "kucoin"]

    def __init__(self):
        self._cache: dict[str, pd.DataFrame] = {}
        self._exchange = None
        self._exchange_id: str = ""

    async def init_exchange(self, exchange_id: str = "binance", config: dict[str, Any] | None = None):
        """Initialize ccxt exchange (async). Falls back to other exchanges on geo-block."""
        import ccxt.async_support as ccxt_async

        candidates = [exchange_id] + [e for e in self.FALLBACK_EXCHANGES if e != exchange_id]

        for eid in candidates:
            if not hasattr(ccxt_async, eid):
                logger.warning(f"Exchange {eid} not available in ccxt, skipping")
                continue
            exchange_class = getattr(ccxt_async, eid)
            ex = exchange_class(config or {})
            try:
                # Quick connectivity check — fetch 1 candle
                await ex.fetch_ohlcv("BTC/USDT", "1h", limit=1)
                self._exchange = ex
                self._exchange_id = eid
                if eid != exchange_id:
                    logger.warning(
                        f"{exchange_id} is geo-blocked from this server. "
                        f"Fell back to {eid}"
                    )
                logger.info(f"Initialized exchange: {eid}")
                return
            except Exception as e:
                err_str = str(e)
                await ex.close()
                if "451" in err_str or "restricted location" in err_str.lower():
                    logger.warning(f"{eid} geo-blocked (HTTP 451), trying next...")
                    continue
                elif "NotSupported" in err_str or "not available" in err_str.lower():
                    logger.warning(f"{eid}: symbol not supported, trying next...")
                    continue
                else:
                    # Other error — still try fallbacks
                    logger.warning(f"{eid} failed: {e}, trying next...")
                    continue

        raise RuntimeError(
            f"All exchanges failed ({', '.join(candidates)}). "
            f"Check network / API keys / server location."
        )

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
