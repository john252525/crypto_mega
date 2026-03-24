"""
Strategy: Donchian Channel Breakout

Classic breakout strategy — enters on new highs/lows with volume confirmation.
The turtle trading approach adapted for crypto.
Medium frequency — fires only on genuine breakouts.
"""

import numpy as np
import pandas as pd

from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig


class DonchianBreakout(BaseStrategy):
    """Donchian Channel breakout — turtle trading for crypto."""

    DESCRIPTION = (
        "Classic breakout strategy inspired by the Turtle Traders. "
        "LONG when price breaks above the N-period high channel. "
        "SHORT when price breaks below the N-period low channel. "
        "Uses volume confirmation and ATR-based stops. "
        "Medium frequency — waits for genuine range breakouts."
    )
    CATEGORY = "breakout"
    RISK_LEVEL = "medium"
    BEST_TIMEFRAMES = ["1h", "4h", "1d"]
    BEST_MARKETS = ["trending", "volatile"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.channel_period = config.parameters.get("channel_period", 20)
        self.atr_period = config.parameters.get("atr_period", 14)
        self.atr_multiplier = config.parameters.get("atr_multiplier", 2.0)
        self.volume_confirm = config.parameters.get("volume_confirm", 1.3)

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for key, df in data.items():
            if len(df) < self.channel_period + self.atr_period + 5:
                continue

            symbol = key.split("_")[0]
            df = df.copy()

            # Donchian channels
            df["dc_upper"] = df["high"].rolling(self.channel_period).max()
            df["dc_lower"] = df["low"].rolling(self.channel_period).min()
            df["dc_mid"] = (df["dc_upper"] + df["dc_lower"]) / 2

            # ATR for stops
            tr = pd.concat([
                df["high"] - df["low"],
                (df["high"] - df["close"].shift(1)).abs(),
                (df["low"] - df["close"].shift(1)).abs(),
            ], axis=1).max(axis=1)
            df["atr"] = tr.rolling(self.atr_period).mean()

            # Volume check
            df["vol_avg"] = df["volume"].rolling(20).mean()

            df = df.dropna()
            if len(df) < 2:
                continue

            prev = df.iloc[-2]
            curr = df.iloc[-1]
            price = curr["close"]

            vol_ok = curr["volume"] > curr["vol_avg"] * self.volume_confirm

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
                "dc_upper": round(curr["dc_upper"], 2),
                "dc_lower": round(curr["dc_lower"], 2),
                "dc_mid": round(curr["dc_mid"], 2),
                "atr": round(curr["atr"], 2),
                "volume_ratio": round(curr["volume"] / curr["vol_avg"], 2) if curr["vol_avg"] > 0 else 0,
                "channel_period": self.channel_period,
                "candles": candles,
            }

            # Breakout UP: close above upper channel with volume
            if curr["close"] > prev["dc_upper"] and vol_ok:
                sl = price - curr["atr"] * self.atr_multiplier
                tp = price + curr["atr"] * self.atr_multiplier * 2
                strength = min(1.0, 0.6 + (curr["volume"] / curr["vol_avg"] - 1) * 0.3)
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
                            f"Donchian breakout UP: price {price:.2f} broke above {self.channel_period}-bar "
                            f"high {prev['dc_upper']:.2f}. Volume {curr['volume']/curr['vol_avg']:.1f}x average. "
                            f"ATR={curr['atr']:.2f}. SL={sl:.2f} (-{self.atr_multiplier}x ATR), "
                            f"TP={tp:.2f} (+{self.atr_multiplier*2}x ATR)."
                        ),
                    },
                ))

            # Breakout DOWN: close below lower channel with volume
            elif curr["close"] < prev["dc_lower"] and vol_ok:
                sl = price + curr["atr"] * self.atr_multiplier
                tp = price - curr["atr"] * self.atr_multiplier * 2
                strength = min(1.0, 0.6 + (curr["volume"] / curr["vol_avg"] - 1) * 0.3)
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
                            f"Donchian breakout DOWN: price {price:.2f} broke below {self.channel_period}-bar "
                            f"low {prev['dc_lower']:.2f}. Volume {curr['volume']/curr['vol_avg']:.1f}x average. "
                            f"ATR={curr['atr']:.2f}. SL={sl:.2f} (+{self.atr_multiplier}x ATR), "
                            f"TP={tp:.2f} (-{self.atr_multiplier*2}x ATR)."
                        ),
                    },
                ))

        return signals

    def param_grid(self) -> dict[str, list]:
        return {
            "channel_period": [10, 15, 20, 30, 55],
            "atr_period": [10, 14, 20],
            "atr_multiplier": [1.5, 2.0, 3.0],
            "volume_confirm": [1.0, 1.3, 1.5, 2.0],
        }

    def param_defaults(self) -> dict:
        return {"channel_period": 20, "atr_period": 14, "atr_multiplier": 2.0, "volume_confirm": 1.3}

    def param_descriptions(self) -> dict:
        return {
            "channel_period": "Donchian channel lookback (higher = rarer, stronger breakouts)",
            "atr_period": "ATR period for dynamic stop-loss",
            "atr_multiplier": "ATR multiplier for stop-loss distance",
            "volume_confirm": "Volume must be Nx above average to confirm breakout",
        }

    def required_history(self) -> int:
        return max(self.channel_period, self.atr_period) + 25
