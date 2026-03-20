"""Base strategy interface — all strategies implement this."""

from __future__ import annotations

import abc
from typing import Any

import pandas as pd

from crypto_mega.utils.types import Signal, StrategyConfig, TimeFrame


class BaseStrategy(abc.ABC):
    """
    Base class for all trading strategies.

    To create a new strategy:
    1. Subclass BaseStrategy
    2. Implement `generate_signals()`
    3. Optionally override `param_grid()` for parameter optimization
    4. Drop the .py file into strategies_user/ or register via API
    """

    def __init__(self, config: StrategyConfig):
        self.config = config
        self.id = config.id
        self.name = config.name or self.__class__.__name__

    @abc.abstractmethod
    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        """
        Generate trading signals from market data.

        Args:
            data: Dict mapping "SYMBOL_TIMEFRAME" (e.g. "BTC/USDT_1h") to OHLCV DataFrames.
                  Each DataFrame has columns: timestamp, open, high, low, close, volume

        Returns:
            List of Signal objects
        """
        ...

    def param_grid(self) -> dict[str, list[Any]]:
        """
        Return parameter grid for optimization / grid search.
        Keys are parameter names, values are lists of values to try.

        Example:
            return {
                "fast_period": [5, 10, 15, 20],
                "slow_period": [20, 30, 50, 100],
                "rsi_threshold": [30, 35, 40],
            }
        """
        return {}

    def required_timeframes(self) -> list[TimeFrame]:
        return self.config.timeframes

    def required_history(self) -> int:
        """Number of candles of history needed."""
        return 200

    def on_trade_result(self, result: dict) -> None:
        """Callback when a trade from this strategy is closed. Override for adaptive strategies."""
        pass

    def validate_params(self) -> list[str]:
        """Validate strategy parameters. Return list of error strings (empty = valid)."""
        return []

    def __repr__(self) -> str:
        return f"<Strategy {self.name} [{self.id[:8]}]>"
