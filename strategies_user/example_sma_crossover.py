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

            # Recent candles for detail view
            recent = df.tail(10)
            candles = [
                {
                    "t": str(row.get("timestamp", "")),
                    "o": round(row["open"], 2),
                    "h": round(row["high"], 2),
                    "l": round(row["low"], 2),
                    "c": round(row["close"], 2),
                    "v": round(row["volume"], 2) if row.get("volume") else 0,
                }
                for _, row in recent.iterrows()
            ]

            base_meta = {
                "sma_fast": round(curr["sma_fast"], 2),
                "sma_slow": round(curr["sma_slow"], 2),
                "prev_sma_fast": round(prev["sma_fast"], 2),
                "prev_sma_slow": round(prev["sma_slow"], 2),
                "fast_period": self.fast_period,
                "slow_period": self.slow_period,
                "candles": candles,
            }

            # Crossover detection
            if prev["sma_fast"] <= prev["sma_slow"] and curr["sma_fast"] > curr["sma_slow"]:
                sl = curr["close"] * 0.98
                tp = curr["close"] * 1.04
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.LONG,
                    strength=0.7,
                    price=curr["close"],
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "reason": (
                            f"Bullish SMA crossover: SMA{self.fast_period} crossed above SMA{self.slow_period}. "
                            f"Previous: fast={prev['sma_fast']:.2f} <= slow={prev['sma_slow']:.2f}. "
                            f"Current: fast={curr['sma_fast']:.2f} > slow={curr['sma_slow']:.2f}. "
                            f"Entry at {curr['close']:.2f}, SL={sl:.2f} (-2%), TP={tp:.2f} (+4%)."
                        ),
                    },
                ))

            elif prev["sma_fast"] >= prev["sma_slow"] and curr["sma_fast"] < curr["sma_slow"]:
                sl = curr["close"] * 1.02
                tp = curr["close"] * 0.96
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.SHORT,
                    strength=0.7,
                    price=curr["close"],
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "reason": (
                            f"Bearish SMA crossover: SMA{self.fast_period} crossed below SMA{self.slow_period}. "
                            f"Previous: fast={prev['sma_fast']:.2f} >= slow={prev['sma_slow']:.2f}. "
                            f"Current: fast={curr['sma_fast']:.2f} < slow={curr['sma_slow']:.2f}. "
                            f"Entry at {curr['close']:.2f}, SL={sl:.2f} (+2%), TP={tp:.2f} (-4%)."
                        ),
                    },
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
