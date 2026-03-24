"""
Strategy: Supertrend

Popular ATR-based trend-following indicator.
Flips between bullish/bearish on ATR bands.
Medium-high frequency — captures most trend changes.
"""

import numpy as np
import pandas as pd

from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig


class Supertrend(BaseStrategy):
    """Supertrend indicator — simple ATR-based trend follower."""

    DESCRIPTION = (
        "ATR-based trend indicator that flips between bullish and bearish. "
        "Upper band = HL2 + ATR * multiplier, Lower band = HL2 - ATR * multiplier. "
        "LONG when price closes above upper band (trend flips bullish). "
        "SHORT when price closes below lower band (trend flips bearish). "
        "Clean signals, medium-high frequency. Works great on crypto."
    )
    CATEGORY = "trend"
    RISK_LEVEL = "medium"
    BEST_TIMEFRAMES = ["15m", "1h", "4h"]
    BEST_MARKETS = ["trending", "volatile"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.atr_period = config.parameters.get("atr_period", 10)
        self.multiplier = config.parameters.get("multiplier", 3.0)

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for key, df in data.items():
            if len(df) < self.atr_period + 20:
                continue

            symbol = key.split("_")[0]
            df = df.copy()

            # ATR
            tr = pd.concat([
                df["high"] - df["low"],
                (df["high"] - df["close"].shift(1)).abs(),
                (df["low"] - df["close"].shift(1)).abs(),
            ], axis=1).max(axis=1)
            df["atr"] = tr.rolling(self.atr_period).mean()

            # HL2
            hl2 = (df["high"] + df["low"]) / 2

            # Basic bands
            basic_upper = hl2 + self.multiplier * df["atr"]
            basic_lower = hl2 - self.multiplier * df["atr"]

            # Supertrend calculation with proper flip logic
            supertrend = pd.Series(index=df.index, dtype=float)
            direction = pd.Series(index=df.index, dtype=int)  # 1=up, -1=down

            upper_band = basic_upper.copy()
            lower_band = basic_lower.copy()

            valid_start = df["atr"].first_valid_index()
            if valid_start is None:
                continue

            idx = df.index.tolist()
            start_pos = idx.index(valid_start)

            direction.iloc[start_pos] = 1
            supertrend.iloc[start_pos] = lower_band.iloc[start_pos]

            for i in range(start_pos + 1, len(idx)):
                # Adjust bands (they only move in favorable direction)
                if basic_lower.iloc[i] > lower_band.iloc[i - 1]:
                    lower_band.iloc[i] = basic_lower.iloc[i]
                else:
                    lower_band.iloc[i] = lower_band.iloc[i - 1]

                if basic_upper.iloc[i] < upper_band.iloc[i - 1]:
                    upper_band.iloc[i] = basic_upper.iloc[i]
                else:
                    upper_band.iloc[i] = upper_band.iloc[i - 1]

                # Direction flip
                if direction.iloc[i - 1] == 1:
                    if df["close"].iloc[i] < lower_band.iloc[i]:
                        direction.iloc[i] = -1
                        supertrend.iloc[i] = upper_band.iloc[i]
                    else:
                        direction.iloc[i] = 1
                        supertrend.iloc[i] = lower_band.iloc[i]
                else:
                    if df["close"].iloc[i] > upper_band.iloc[i]:
                        direction.iloc[i] = 1
                        supertrend.iloc[i] = lower_band.iloc[i]
                    else:
                        direction.iloc[i] = -1
                        supertrend.iloc[i] = upper_band.iloc[i]

            df["supertrend"] = supertrend
            df["st_direction"] = direction

            df = df.dropna(subset=["supertrend", "st_direction"])
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
                "supertrend": round(curr["supertrend"], 2),
                "direction": int(curr["st_direction"]),
                "atr": round(curr["atr"], 2),
                "multiplier": self.multiplier,
                "candles": candles,
            }

            # Flip from bearish to bullish
            if prev["st_direction"] == -1 and curr["st_direction"] == 1:
                strength = min(1.0, 0.65 + curr["atr"] / price * 10)
                sl = curr["supertrend"] * 0.995
                tp = price + (price - curr["supertrend"]) * 2
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.LONG,
                    strength=strength,
                    price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "reason": (
                            f"Supertrend flipped BULLISH: price {price:.2f} broke above "
                            f"upper band. Supertrend now at {curr['supertrend']:.2f} (support). "
                            f"ATR={curr['atr']:.2f}. SL={sl:.2f}, TP={tp:.2f}."
                        ),
                    },
                ))

            # Flip from bullish to bearish
            elif prev["st_direction"] == 1 and curr["st_direction"] == -1:
                strength = min(1.0, 0.65 + curr["atr"] / price * 10)
                sl = curr["supertrend"] * 1.005
                tp = price - (curr["supertrend"] - price) * 2
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.SHORT,
                    strength=strength,
                    price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "reason": (
                            f"Supertrend flipped BEARISH: price {price:.2f} broke below "
                            f"lower band. Supertrend now at {curr['supertrend']:.2f} (resistance). "
                            f"ATR={curr['atr']:.2f}. SL={sl:.2f}, TP={tp:.2f}."
                        ),
                    },
                ))

        return signals

    def param_grid(self) -> dict[str, list]:
        return {
            "atr_period": [7, 10, 14, 20],
            "multiplier": [2.0, 2.5, 3.0, 4.0],
        }

    def param_defaults(self) -> dict:
        return {"atr_period": 10, "multiplier": 3.0}

    def param_descriptions(self) -> dict:
        return {
            "atr_period": "ATR period for volatility calculation",
            "multiplier": "ATR multiplier for band width (higher = fewer signals, wider stops)",
        }

    def required_history(self) -> int:
        return self.atr_period + 50
