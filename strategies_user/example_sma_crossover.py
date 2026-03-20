"""
Example Strategy: SMA Crossover

This is what "Vasya" or GPT would write and drop in.
Simple moving average crossover with configurable periods.
"""

import pandas as pd

from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig


class SMACrossover(BaseStrategy):
    """Classic SMA crossover — the "hello world" of trading strategies."""

    DESCRIPTION = (
        "Follows the trend using two Simple Moving Averages. "
        "When the fast SMA crosses above the slow SMA — BUY. "
        "When it crosses below — SELL. Works best on trending markets "
        "with clear directional moves (BTC rallies, ETH pumps). "
        "Avoid during sideways/choppy price action."
    )
    CATEGORY = "trend"
    RISK_LEVEL = "low"
    BEST_TIMEFRAMES = ["1h", "4h", "1d"]
    BEST_MARKETS = ["trending"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.fast_period = config.parameters.get("fast_period", 10)
        self.slow_period = config.parameters.get("slow_period", 30)

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for key, df in data.items():
            if len(df) < self.slow_period + 1:
                continue

            symbol = key.split("_")[0]
            df = df.copy()
            df["sma_fast"] = df["close"].rolling(self.fast_period).mean()
            df["sma_slow"] = df["close"].rolling(self.slow_period).mean()
            df = df.dropna()

            if len(df) < 2:
                continue

            prev = df.iloc[-2]
            curr = df.iloc[-1]

            # Crossover detection
            if prev["sma_fast"] <= prev["sma_slow"] and curr["sma_fast"] > curr["sma_slow"]:
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.LONG,
                    strength=0.7,
                    price=curr["close"],
                    stop_loss=curr["close"] * 0.98,
                    take_profit=curr["close"] * 1.04,
                    metadata={"fast": self.fast_period, "slow": self.slow_period},
                ))

            elif prev["sma_fast"] >= prev["sma_slow"] and curr["sma_fast"] < curr["sma_slow"]:
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.SHORT,
                    strength=0.7,
                    price=curr["close"],
                    stop_loss=curr["close"] * 1.02,
                    take_profit=curr["close"] * 0.96,
                    metadata={"fast": self.fast_period, "slow": self.slow_period},
                ))

        return signals

    def param_grid(self) -> dict[str, list]:
        return {
            "fast_period": [5, 8, 10, 13, 15, 20],
            "slow_period": [20, 30, 40, 50, 60, 100],
        }

    def param_defaults(self) -> dict:
        return {"fast_period": 10, "slow_period": 30}

    def param_descriptions(self) -> dict:
        return {
            "fast_period": "Fast SMA period (shorter = more reactive, more noise)",
            "slow_period": "Slow SMA period (longer = smoother, slower entries)",
        }

    def required_history(self) -> int:
        return self.slow_period + 10
