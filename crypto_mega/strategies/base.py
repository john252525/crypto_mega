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

    # ── Override these in subclasses for rich UI display ──
    DESCRIPTION: str = ""          # Human-readable description of the strategy
    CATEGORY: str = "custom"       # trend | mean-reversion | momentum | breakout | scalping | custom
    RISK_LEVEL: str = "medium"     # low | medium | high
    BEST_TIMEFRAMES: list[str] = []  # e.g. ["1h", "4h"]
    BEST_MARKETS: list[str] = []     # e.g. ["trending", "ranging"]

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
        """
        return {}

    def param_defaults(self) -> dict[str, Any]:
        """Return default values for all configurable parameters."""
        return {}

    def param_descriptions(self) -> dict[str, str]:
        """Return human-readable descriptions for each parameter."""
        return {}

    def describe(self) -> dict[str, Any]:
        """Return full strategy metadata for the UI."""
        grid = self.param_grid()
        total_combos = 1
        for vals in grid.values():
            total_combos *= len(vals)

        return {
            "name": self.__class__.__name__,
            "description": self.DESCRIPTION or self.__doc__ or "",
            "category": self.CATEGORY,
            "risk_level": self.RISK_LEVEL,
            "best_timeframes": self.BEST_TIMEFRAMES,
            "best_markets": self.BEST_MARKETS,
            "parameters": {
                k: {
                    "default": self.param_defaults().get(k),
                    "description": self.param_descriptions().get(k, ""),
                    "grid": v,
                }
                for k, v in grid.items()
            },
            "total_grid_combos": total_combos,
            "required_history": self.required_history(),
            "required_timeframes": [tf.value for tf in self.required_timeframes()],
        }

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
