"""
Strategy: Stochastic RSI Crossover

High-frequency momentum strategy using Stochastic RSI.
Fires on %K/%D crossovers in overbought/oversold zones.
Very active — detects micro-momentum shifts.
"""

import numpy as np
import pandas as pd

from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig


class StochasticRSI(BaseStrategy):
    """Stochastic RSI crossover — catches momentum shifts in extreme zones."""

    DESCRIPTION = (
        "High-frequency momentum oscillator strategy. Uses Stochastic RSI "
        "to detect overbought/oversold conditions with %K/%D crossover confirmation. "
        "LONG when StochRSI crosses up from oversold zone (<20). "
        "SHORT when StochRSI crosses down from overbought zone (>80). "
        "Very active on shorter timeframes."
    )
    CATEGORY = "momentum"
    RISK_LEVEL = "medium"
    BEST_TIMEFRAMES = ["5m", "15m", "1h"]
    BEST_MARKETS = ["ranging", "volatile"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.rsi_period = config.parameters.get("rsi_period", 14)
        self.stoch_period = config.parameters.get("stoch_period", 14)
        self.smooth_k = config.parameters.get("smooth_k", 3)
        self.smooth_d = config.parameters.get("smooth_d", 3)
        self.oversold = config.parameters.get("oversold", 20)
        self.overbought = config.parameters.get("overbought", 80)

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for key, df in data.items():
            if len(df) < self.rsi_period + self.stoch_period + self.smooth_k + self.smooth_d + 5:
                continue

            symbol = key.split("_")[0]
            df = df.copy()

            # RSI
            delta = df["close"].diff()
            gain = delta.clip(lower=0).rolling(self.rsi_period).mean()
            loss = (-delta.clip(upper=0)).rolling(self.rsi_period).mean()
            rs = gain / loss.replace(0, np.nan)
            df["rsi"] = 100 - (100 / (1 + rs))

            # Stochastic RSI
            rsi_min = df["rsi"].rolling(self.stoch_period).min()
            rsi_max = df["rsi"].rolling(self.stoch_period).max()
            rsi_range = rsi_max - rsi_min
            stoch_rsi = ((df["rsi"] - rsi_min) / rsi_range.replace(0, np.nan)) * 100

            df["stoch_k"] = stoch_rsi.rolling(self.smooth_k).mean()
            df["stoch_d"] = df["stoch_k"].rolling(self.smooth_d).mean()

            df = df.dropna()
            if len(df) < 2:
                continue

            prev = df.iloc[-2]
            curr = df.iloc[-1]
            price = curr["close"]

            candles = [
                {
                    "t": str(row.get("timestamp", "")),
                    "o": round(row["open"], 2),
                    "h": round(row["high"], 2),
                    "l": round(row["low"], 2),
                    "c": round(row["close"], 2),
                    "v": round(row["volume"], 2) if row.get("volume") else 0,
                }
                for _, row in df.tail(10).iterrows()
            ]

            base_meta = {
                "stoch_k": round(curr["stoch_k"], 2),
                "stoch_d": round(curr["stoch_d"], 2),
                "rsi": round(curr["rsi"], 2),
                "prev_stoch_k": round(prev["stoch_k"], 2),
                "prev_stoch_d": round(prev["stoch_d"], 2),
                "candles": candles,
            }

            # LONG: %K crosses above %D in oversold zone
            if (prev["stoch_k"] <= prev["stoch_d"]
                    and curr["stoch_k"] > curr["stoch_d"]
                    and curr["stoch_k"] < self.oversold + 20):
                strength = min(1.0, 0.5 + (self.oversold - min(prev["stoch_k"], curr["stoch_d"])) / 100)
                sl = price * 0.985
                tp = price * 1.025
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.LONG,
                    strength=max(0.5, strength),
                    price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "reason": (
                            f"StochRSI bullish crossover: %K={curr['stoch_k']:.1f} crossed above "
                            f"%D={curr['stoch_d']:.1f} near oversold zone. RSI={curr['rsi']:.1f}. "
                            f"SL={sl:.2f} (-1.5%), TP={tp:.2f} (+2.5%)."
                        ),
                    },
                ))

            # SHORT: %K crosses below %D in overbought zone
            elif (prev["stoch_k"] >= prev["stoch_d"]
                    and curr["stoch_k"] < curr["stoch_d"]
                    and curr["stoch_k"] > self.overbought - 20):
                strength = min(1.0, 0.5 + (max(prev["stoch_k"], curr["stoch_d"]) - self.overbought) / 100)
                sl = price * 1.015
                tp = price * 0.975
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.SHORT,
                    strength=max(0.5, strength),
                    price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "reason": (
                            f"StochRSI bearish crossover: %K={curr['stoch_k']:.1f} crossed below "
                            f"%D={curr['stoch_d']:.1f} near overbought zone. RSI={curr['rsi']:.1f}. "
                            f"SL={sl:.2f} (+1.5%), TP={tp:.2f} (-2.5%)."
                        ),
                    },
                ))

        return signals

    def param_grid(self) -> dict[str, list]:
        return {
            "rsi_period": [7, 14],
            "stoch_period": [7, 14, 21],
            "smooth_k": [2, 3, 5],
            "smooth_d": [2, 3, 5],
            "oversold": [15, 20, 25],
            "overbought": [75, 80, 85],
        }

    def param_defaults(self) -> dict:
        return {
            "rsi_period": 14, "stoch_period": 14,
            "smooth_k": 3, "smooth_d": 3,
            "oversold": 20, "overbought": 80,
        }

    def param_descriptions(self) -> dict:
        return {
            "rsi_period": "RSI calculation period",
            "stoch_period": "Stochastic lookback on RSI values",
            "smooth_k": "%K smoothing period",
            "smooth_d": "%D smoothing period (signal line)",
            "oversold": "Oversold threshold for buy zone",
            "overbought": "Overbought threshold for sell zone",
        }

    def required_history(self) -> int:
        return self.rsi_period + self.stoch_period + self.smooth_k + self.smooth_d + 20
