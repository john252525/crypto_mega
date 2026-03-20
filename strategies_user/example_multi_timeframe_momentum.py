"""
Example Strategy: Multi-Timeframe Momentum

Checks momentum across multiple timeframes for confluence.
Only signals when all timeframes agree on direction.
"""

import pandas as pd

from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig, TimeFrame


class MultiTFMomentum(BaseStrategy):
    """Multi-timeframe momentum confluence with volume confirmation."""

    DESCRIPTION = (
        "High-conviction trend strategy. Checks EMA slope on 3 timeframes "
        "(15m, 1h, 4h) — only enters when ALL agree on direction AND volume "
        "is above average. Fewer signals, but each one has strong confluence. "
        "Best for catching big moves. Misses quick reversals."
    )
    CATEGORY = "momentum"
    RISK_LEVEL = "medium"
    BEST_TIMEFRAMES = ["15m", "1h", "4h"]
    BEST_MARKETS = ["trending", "volatile"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.ema_period = config.parameters.get("ema_period", 20)
        self.slope_lookback = config.parameters.get("slope_lookback", 3)
        self.volume_multiplier = config.parameters.get("volume_multiplier", 1.5)

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        # Group data by symbol
        by_symbol: dict[str, dict[str, pd.DataFrame]] = {}
        for key, df in data.items():
            parts = key.split("_")
            symbol = parts[0]
            tf = parts[1] if len(parts) > 1 else "1h"
            if symbol not in by_symbol:
                by_symbol[symbol] = {}
            by_symbol[symbol][tf] = df

        for symbol, tf_data in by_symbol.items():
            if len(tf_data) < 2:
                continue

            directions = []
            volume_ok = False

            for tf, df in tf_data.items():
                if len(df) < self.ema_period + self.slope_lookback:
                    continue

                df = df.copy()
                df["ema"] = df["close"].ewm(span=self.ema_period).mean()
                ema_slope = df["ema"].iloc[-1] - df["ema"].iloc[-self.slope_lookback]

                avg_vol = df["volume"].rolling(20).mean().iloc[-1]
                curr_vol = df["volume"].iloc[-1]
                if curr_vol > avg_vol * self.volume_multiplier:
                    volume_ok = True

                if ema_slope > 0:
                    directions.append("up")
                else:
                    directions.append("down")

            if not directions:
                continue

            # All timeframes agree?
            if all(d == "up" for d in directions) and volume_ok:
                price = list(tf_data.values())[0].iloc[-1]["close"]
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.LONG,
                    strength=min(1.0, len(directions) * 0.3),
                    price=price,
                    stop_loss=price * 0.97,
                    take_profit=price * 1.06,
                    metadata={"confluence": len(directions), "direction": "up"},
                ))
            elif all(d == "down" for d in directions) and volume_ok:
                price = list(tf_data.values())[0].iloc[-1]["close"]
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.SHORT,
                    strength=min(1.0, len(directions) * 0.3),
                    price=price,
                    stop_loss=price * 1.03,
                    take_profit=price * 0.94,
                    metadata={"confluence": len(directions), "direction": "down"},
                ))

        return signals

    def required_timeframes(self) -> list[TimeFrame]:
        return [TimeFrame.M15, TimeFrame.H1, TimeFrame.H4]

    def param_grid(self) -> dict[str, list]:
        return {
            "ema_period": [10, 15, 20, 30],
            "slope_lookback": [2, 3, 5],
            "volume_multiplier": [1.2, 1.5, 2.0],
        }

    def param_defaults(self) -> dict:
        return {
            "ema_period": 20,
            "slope_lookback": 3,
            "volume_multiplier": 1.5,
        }

    def param_descriptions(self) -> dict:
        return {
            "ema_period": "EMA period for trend detection on each timeframe",
            "slope_lookback": "How many bars back to measure EMA slope direction",
            "volume_multiplier": "Volume must be Nx above average to confirm signal",
        }
