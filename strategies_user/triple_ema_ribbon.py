"""
Strategy: Triple EMA Ribbon

Trend strategy using 3 EMAs (fast, mid, slow) forming a ribbon.
Signals when all 3 EMAs are aligned and expanding.
State-based — fires on every candle where trend is clear.
Very active for stat accumulation.
"""

import numpy as np
import pandas as pd

from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig


class TripleEMARibbon(BaseStrategy):
    """Triple EMA ribbon — rides the trend when all EMAs align."""

    DESCRIPTION = (
        "Trend-following with 3 EMAs forming a ribbon. "
        "LONG when fast > mid > slow and ribbon is expanding (EMAs spreading apart). "
        "SHORT when fast < mid < slow and ribbon expanding. "
        "State-based: fires on EVERY candle where trend holds. "
        "Very active — great for accumulating statistics quickly."
    )
    CATEGORY = "trend"
    RISK_LEVEL = "low"
    BEST_TIMEFRAMES = ["15m", "1h", "4h"]
    BEST_MARKETS = ["trending"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.ema_fast = config.parameters.get("ema_fast", 8)
        self.ema_mid = config.parameters.get("ema_mid", 21)
        self.ema_slow = config.parameters.get("ema_slow", 55)
        self.min_spread = config.parameters.get("min_spread", 0.001)

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for key, df in data.items():
            if len(df) < self.ema_slow + 10:
                continue

            symbol = key.split("_")[0]
            df = df.copy()

            df["ema_fast"] = df["close"].ewm(span=self.ema_fast, adjust=False).mean()
            df["ema_mid"] = df["close"].ewm(span=self.ema_mid, adjust=False).mean()
            df["ema_slow"] = df["close"].ewm(span=self.ema_slow, adjust=False).mean()

            # Ribbon spread (fast-slow distance as % of price)
            df["ribbon_spread"] = (df["ema_fast"] - df["ema_slow"]).abs() / df["close"]

            # Is ribbon expanding?
            df["ribbon_prev"] = df["ribbon_spread"].shift(1)

            df = df.dropna()
            if len(df) < 1:
                continue

            curr = df.iloc[-1]
            price = curr["close"]
            ema_f = curr["ema_fast"]
            ema_m = curr["ema_mid"]
            ema_s = curr["ema_slow"]
            spread = curr["ribbon_spread"]

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
                "ema_fast": round(ema_f, 2),
                "ema_mid": round(ema_m, 2),
                "ema_slow": round(ema_s, 2),
                "ribbon_spread_pct": round(spread * 100, 4),
                "ribbon_expanding": spread > curr["ribbon_prev"],
                "candles": candles,
            }

            if spread < self.min_spread:
                continue

            # Bullish ribbon: fast > mid > slow, price above all
            if price > ema_f > ema_m > ema_s:
                expanding = spread > curr["ribbon_prev"]
                strength_base = 0.4 + min(0.3, spread * 30)
                if expanding:
                    strength_base += 0.15
                sl = ema_s * 0.995
                tp = price + (price - ema_s) * 1.2
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.LONG,
                    strength=min(1.0, strength_base),
                    price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "reason": (
                            f"Bullish EMA ribbon: price {price:.2f} > EMA{self.ema_fast} {ema_f:.2f} > "
                            f"EMA{self.ema_mid} {ema_m:.2f} > EMA{self.ema_slow} {ema_s:.2f}. "
                            f"Ribbon spread {spread*100:.3f}%, {'expanding' if expanding else 'stable'}. "
                            f"SL below slow EMA at {sl:.2f}."
                        ),
                    },
                ))

            # Bearish ribbon: fast < mid < slow, price below all
            elif price < ema_f < ema_m < ema_s:
                expanding = spread > curr["ribbon_prev"]
                strength_base = 0.4 + min(0.3, spread * 30)
                if expanding:
                    strength_base += 0.15
                sl = ema_s * 1.005
                tp = price - (ema_s - price) * 1.2
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.SHORT,
                    strength=min(1.0, strength_base),
                    price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "reason": (
                            f"Bearish EMA ribbon: price {price:.2f} < EMA{self.ema_fast} {ema_f:.2f} < "
                            f"EMA{self.ema_mid} {ema_m:.2f} < EMA{self.ema_slow} {ema_s:.2f}. "
                            f"Ribbon spread {spread*100:.3f}%, {'expanding' if expanding else 'stable'}. "
                            f"SL above slow EMA at {sl:.2f}."
                        ),
                    },
                ))

        return signals

    def param_grid(self) -> dict[str, list]:
        return {
            "ema_fast": [5, 8, 13],
            "ema_mid": [15, 21, 34],
            "ema_slow": [40, 55, 89],
            "min_spread": [0.0005, 0.001, 0.002],
        }

    def param_defaults(self) -> dict:
        return {"ema_fast": 8, "ema_mid": 21, "ema_slow": 55, "min_spread": 0.001}

    def param_descriptions(self) -> dict:
        return {
            "ema_fast": "Fast EMA period (inner ribbon edge)",
            "ema_mid": "Middle EMA period",
            "ema_slow": "Slow EMA period (outer ribbon edge)",
            "min_spread": "Minimum ribbon spread to signal (filters flat EMAs)",
        }

    def required_history(self) -> int:
        return self.ema_slow + 20
