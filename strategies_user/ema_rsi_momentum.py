"""
Strategy: EMA + RSI Momentum

Generates signals based on EMA trend alignment and RSI momentum.
Designed to fire regularly — checks trend STATE (not crossover),
so it produces signals whenever the market shows clear direction.

LONG:  price > EMA fast > EMA slow, RSI > 45 (uptrend with momentum)
SHORT: price < EMA fast < EMA slow, RSI < 55 (downtrend with momentum)
"""

import numpy as np
import pandas as pd

from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig


class EmaRsiMomentum(BaseStrategy):
    """EMA trend alignment + RSI momentum — fires when trend is clear."""

    DESCRIPTION = (
        "Trend-following strategy that combines EMA alignment with RSI momentum. "
        "BUY when price is above both EMAs and RSI confirms upward momentum. "
        "SELL when price is below both EMAs and RSI confirms downward momentum. "
        "Fires on every candle where conditions hold, not just on crossovers."
    )
    CATEGORY = "momentum"
    RISK_LEVEL = "medium"
    BEST_TIMEFRAMES = ["15m", "1h", "4h"]
    BEST_MARKETS = ["trending", "ranging"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.ema_fast = config.parameters.get("ema_fast", 9)
        self.ema_slow = config.parameters.get("ema_slow", 21)
        self.rsi_period = config.parameters.get("rsi_period", 14)
        self.rsi_long_min = config.parameters.get("rsi_long_min", 45)
        self.rsi_short_max = config.parameters.get("rsi_short_max", 55)

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for key, df in data.items():
            if len(df) < self.ema_slow + self.rsi_period + 5:
                continue

            symbol = key.split("_")[0]
            df = df.copy()

            # EMA
            df["ema_fast"] = df["close"].ewm(span=self.ema_fast, adjust=False).mean()
            df["ema_slow"] = df["close"].ewm(span=self.ema_slow, adjust=False).mean()

            # RSI
            delta = df["close"].diff()
            gain = delta.clip(lower=0).rolling(self.rsi_period).mean()
            loss = (-delta.clip(upper=0)).rolling(self.rsi_period).mean()
            rs = gain / loss.replace(0, np.nan)
            df["rsi"] = 100 - (100 / (1 + rs))

            # EMA spread as % of price
            df["ema_spread"] = (df["ema_fast"] - df["ema_slow"]) / df["close"] * 100

            df = df.dropna()
            if len(df) < 1:
                continue

            last = df.iloc[-1]
            price = last["close"]
            ema_f = last["ema_fast"]
            ema_s = last["ema_slow"]
            rsi = last["rsi"]
            spread = abs(last["ema_spread"])

            # Strength: based on RSI distance from 50 + EMA spread
            # RSI component: 0-0.5, spread component: 0-0.3, base: 0.3
            rsi_component = abs(rsi - 50) / 100  # 0-0.5
            spread_component = min(spread / 2, 0.3)  # cap at 0.3

            # Build detailed metadata for signal detail view
            recent = df.tail(10)
            candles = [
                {
                    "t": str(row.get("timestamp", "")),
                    "o": round(row["open"], 2),
                    "h": round(row["high"], 2),
                    "l": round(row["low"], 2),
                    "c": round(row["close"], 2),
                    "v": round(row["volume"], 2) if row["volume"] else 0,
                }
                for _, row in recent.iterrows()
            ]

            base_meta = {
                "rsi": round(rsi, 2),
                "ema_fast": round(ema_f, 2),
                "ema_slow": round(ema_s, 2),
                "ema_spread_pct": round(spread, 4),
                "rsi_threshold_long": self.rsi_long_min,
                "rsi_threshold_short": self.rsi_short_max,
                "ema_fast_period": self.ema_fast,
                "ema_slow_period": self.ema_slow,
                "candles": candles,
            }

            # LONG: price > EMA fast > EMA slow, RSI confirms
            if price > ema_f > ema_s and rsi > self.rsi_long_min:
                strength = min(1.0, 0.3 + rsi_component + spread_component)
                sl = ema_s * 0.995
                tp = price + (price - ema_s) * 1.5
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.LONG,
                    strength=max(0.55, strength),
                    price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "reason": (
                            f"Uptrend confirmed: price {price:.2f} > EMA{self.ema_fast} {ema_f:.2f} > EMA{self.ema_slow} {ema_s:.2f}. "
                            f"RSI={rsi:.1f} > {self.rsi_long_min} confirms momentum. "
                            f"EMA spread {spread:.3f}% shows trend strength. "
                            f"SL at {sl:.2f} (below slow EMA), TP at {tp:.2f} (1.5x EMA distance)."
                        ),
                    },
                ))

            # SHORT: price < EMA fast < EMA slow, RSI confirms
            elif price < ema_f < ema_s and rsi < self.rsi_short_max:
                strength = min(1.0, 0.3 + rsi_component + spread_component)
                sl = ema_s * 1.005
                tp = price - (ema_s - price) * 1.5
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.SHORT,
                    strength=max(0.55, strength),
                    price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "reason": (
                            f"Downtrend confirmed: price {price:.2f} < EMA{self.ema_fast} {ema_f:.2f} < EMA{self.ema_slow} {ema_s:.2f}. "
                            f"RSI={rsi:.1f} < {self.rsi_short_max} confirms bearish momentum. "
                            f"EMA spread {spread:.3f}% shows trend strength. "
                            f"SL at {sl:.2f} (above slow EMA), TP at {tp:.2f} (1.5x EMA distance)."
                        ),
                    },
                ))

        return signals

    def param_grid(self) -> dict[str, list]:
        return {
            "ema_fast": [5, 9, 12],
            "ema_slow": [15, 21, 30],
            "rsi_period": [7, 14],
            "rsi_long_min": [40, 45, 50],
            "rsi_short_max": [50, 55, 60],
        }

    def param_defaults(self) -> dict:
        return {
            "ema_fast": 9,
            "ema_slow": 21,
            "rsi_period": 14,
            "rsi_long_min": 45,
            "rsi_short_max": 55,
        }

    def param_descriptions(self) -> dict:
        return {
            "ema_fast": "Fast EMA period (shorter = more reactive)",
            "ema_slow": "Slow EMA period (longer = smoother trend detection)",
            "rsi_period": "RSI lookback period",
            "rsi_long_min": "Minimum RSI for LONG signals (lower = more signals)",
            "rsi_short_max": "Maximum RSI for SHORT signals (higher = more signals)",
        }

    def required_history(self) -> int:
        return self.ema_slow + self.rsi_period + 20
