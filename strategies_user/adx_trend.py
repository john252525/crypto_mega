"""
Strategy: ADX Trend Strength

Uses Average Directional Index to measure trend strength.
Only enters trades when the trend is strong (ADX > 25).
Medium frequency — filters out noise, trades strong moves.
"""

import numpy as np
import pandas as pd

from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig


class ADXTrend(BaseStrategy):
    """ADX trend strength filter — only trades when trend is strong."""

    DESCRIPTION = (
        "Trend strength filter using ADX (Average Directional Index). "
        "Only enters when ADX > 25 (strong trend). Uses +DI/-DI crossovers "
        "for direction. LONG when +DI > -DI with strong ADX. "
        "SHORT when -DI > +DI with strong ADX. "
        "Avoids choppy markets by design."
    )
    CATEGORY = "trend"
    RISK_LEVEL = "low"
    BEST_TIMEFRAMES = ["1h", "4h", "1d"]
    BEST_MARKETS = ["trending"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.adx_period = config.parameters.get("adx_period", 14)
        self.adx_threshold = config.parameters.get("adx_threshold", 25)
        self.di_period = config.parameters.get("di_period", 14)

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for key, df in data.items():
            if len(df) < self.adx_period * 2 + 5:
                continue

            symbol = key.split("_")[0]
            df = df.copy()

            # True Range
            tr = pd.concat([
                df["high"] - df["low"],
                (df["high"] - df["close"].shift(1)).abs(),
                (df["low"] - df["close"].shift(1)).abs(),
            ], axis=1).max(axis=1)

            # Directional Movement
            up_move = df["high"] - df["high"].shift(1)
            down_move = df["low"].shift(1) - df["low"]

            plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
            minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

            # Smooth with EMA
            atr = pd.Series(tr, index=df.index).ewm(span=self.adx_period, adjust=False).mean()
            plus_di = pd.Series(plus_dm, index=df.index).ewm(span=self.di_period, adjust=False).mean() / atr * 100
            minus_di = pd.Series(minus_dm, index=df.index).ewm(span=self.di_period, adjust=False).mean() / atr * 100

            # ADX
            dx = (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100
            df["adx"] = dx.ewm(span=self.adx_period, adjust=False).mean()
            df["plus_di"] = plus_di
            df["minus_di"] = minus_di

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
                "adx": round(curr["adx"], 2),
                "plus_di": round(curr["plus_di"], 2),
                "minus_di": round(curr["minus_di"], 2),
                "adx_threshold": self.adx_threshold,
                "candles": candles,
            }

            if curr["adx"] < self.adx_threshold:
                continue

            # LONG: +DI crosses above -DI with strong ADX
            if prev["plus_di"] <= prev["minus_di"] and curr["plus_di"] > curr["minus_di"]:
                strength = min(1.0, 0.5 + (curr["adx"] - self.adx_threshold) / 50)
                sl = price * 0.975
                tp = price * 1.045
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
                            f"ADX bullish: +DI={curr['plus_di']:.1f} crossed above "
                            f"-DI={curr['minus_di']:.1f}. ADX={curr['adx']:.1f} (>{self.adx_threshold} = strong trend). "
                            f"SL={sl:.2f} (-2.5%), TP={tp:.2f} (+4.5%)."
                        ),
                    },
                ))

            # SHORT: -DI crosses above +DI with strong ADX
            elif prev["minus_di"] <= prev["plus_di"] and curr["minus_di"] > curr["plus_di"]:
                strength = min(1.0, 0.5 + (curr["adx"] - self.adx_threshold) / 50)
                sl = price * 1.025
                tp = price * 0.955
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
                            f"ADX bearish: -DI={curr['minus_di']:.1f} crossed above "
                            f"+DI={curr['plus_di']:.1f}. ADX={curr['adx']:.1f} (>{self.adx_threshold} = strong trend). "
                            f"SL={sl:.2f} (+2.5%), TP={tp:.2f} (-4.5%)."
                        ),
                    },
                ))

            # Also signal when ADX is rising with existing DI dominance (state-based)
            elif curr["adx"] > prev["adx"] and curr["adx"] > self.adx_threshold + 10:
                if curr["plus_di"] > curr["minus_di"] * 1.3:
                    strength = min(1.0, 0.4 + (curr["adx"] - self.adx_threshold) / 40)
                    sl = price * 0.98
                    tp = price * 1.04
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
                                f"ADX strengthening bullish: ADX rising {prev['adx']:.1f}→{curr['adx']:.1f}. "
                                f"+DI={curr['plus_di']:.1f} dominates -DI={curr['minus_di']:.1f}. "
                                f"Strong uptrend accelerating."
                            ),
                        },
                    ))
                elif curr["minus_di"] > curr["plus_di"] * 1.3:
                    strength = min(1.0, 0.4 + (curr["adx"] - self.adx_threshold) / 40)
                    sl = price * 1.02
                    tp = price * 0.96
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
                                f"ADX strengthening bearish: ADX rising {prev['adx']:.1f}→{curr['adx']:.1f}. "
                                f"-DI={curr['minus_di']:.1f} dominates +DI={curr['plus_di']:.1f}. "
                                f"Strong downtrend accelerating."
                            ),
                        },
                    ))

        return signals

    def param_grid(self) -> dict[str, list]:
        return {
            "adx_period": [10, 14, 20],
            "adx_threshold": [20, 25, 30],
            "di_period": [10, 14, 20],
        }

    def param_defaults(self) -> dict:
        return {"adx_period": 14, "adx_threshold": 25, "di_period": 14}

    def param_descriptions(self) -> dict:
        return {
            "adx_period": "ADX smoothing period",
            "adx_threshold": "Minimum ADX for trend to be considered strong",
            "di_period": "Directional Indicator period",
        }

    def required_history(self) -> int:
        return self.adx_period * 3 + 10
