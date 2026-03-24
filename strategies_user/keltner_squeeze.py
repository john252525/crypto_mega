"""
Strategy: Keltner Channel Squeeze (Bollinger-Keltner Squeeze)

Rare but powerful breakout strategy. Detects when Bollinger Bands
contract inside Keltner Channels (squeeze), then trades the breakout.
Low frequency — squeezes are rare but explosive.
"""

import numpy as np
import pandas as pd

from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig


class KeltnerSqueeze(BaseStrategy):
    """Bollinger-Keltner squeeze — catches explosive breakouts from low volatility."""

    DESCRIPTION = (
        "Volatility squeeze detector (TTM Squeeze concept). "
        "When Bollinger Bands contract inside Keltner Channels, volatility is compressed. "
        "Trades the breakout when squeeze releases. RARE signals but high conviction. "
        "Direction determined by momentum histogram slope. "
        "Best on 4h/1d — catches multi-day explosive moves."
    )
    CATEGORY = "breakout"
    RISK_LEVEL = "medium"
    BEST_TIMEFRAMES = ["4h", "1d"]
    BEST_MARKETS = ["volatile"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.bb_period = config.parameters.get("bb_period", 20)
        self.bb_std = config.parameters.get("bb_std", 2.0)
        self.kc_period = config.parameters.get("kc_period", 20)
        self.kc_multiplier = config.parameters.get("kc_multiplier", 1.5)
        self.mom_period = config.parameters.get("mom_period", 12)

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for key, df in data.items():
            if len(df) < max(self.bb_period, self.kc_period) + self.mom_period + 10:
                continue

            symbol = key.split("_")[0]
            df = df.copy()

            # Bollinger Bands
            df["bb_mid"] = df["close"].rolling(self.bb_period).mean()
            bb_std = df["close"].rolling(self.bb_period).std()
            df["bb_upper"] = df["bb_mid"] + self.bb_std * bb_std
            df["bb_lower"] = df["bb_mid"] - self.bb_std * bb_std

            # Keltner Channels (using ATR)
            tr = pd.concat([
                df["high"] - df["low"],
                (df["high"] - df["close"].shift(1)).abs(),
                (df["low"] - df["close"].shift(1)).abs(),
            ], axis=1).max(axis=1)
            atr = tr.rolling(self.kc_period).mean()
            kc_mid = df["close"].ewm(span=self.kc_period, adjust=False).mean()
            df["kc_upper"] = kc_mid + self.kc_multiplier * atr
            df["kc_lower"] = kc_mid - self.kc_multiplier * atr

            # Squeeze: BB inside KC
            df["squeeze_on"] = (df["bb_lower"] > df["kc_lower"]) & (df["bb_upper"] < df["kc_upper"])

            # Momentum (linear regression slope proxy — simplified)
            df["momentum"] = df["close"] - df["close"].shift(self.mom_period)
            df["mom_prev"] = df["momentum"].shift(1)

            df = df.dropna()
            if len(df) < 3:
                continue

            prev2 = df.iloc[-3]
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
                "bb_upper": round(curr["bb_upper"], 2),
                "bb_lower": round(curr["bb_lower"], 2),
                "kc_upper": round(curr["kc_upper"], 2),
                "kc_lower": round(curr["kc_lower"], 2),
                "squeeze_on": bool(curr["squeeze_on"]),
                "momentum": round(curr["momentum"], 2),
                "candles": candles,
            }

            # Squeeze release: was in squeeze, now not
            squeeze_released = prev["squeeze_on"] and not curr["squeeze_on"]
            # Or: was in squeeze for 2+ bars and just released
            squeeze_released = squeeze_released or (prev2["squeeze_on"] and prev["squeeze_on"] and not curr["squeeze_on"])

            if not squeeze_released:
                continue

            # Direction from momentum
            if curr["momentum"] > 0 and curr["momentum"] > prev["momentum"]:
                strength = min(1.0, 0.7 + abs(curr["momentum"]) / price * 10)
                sl = price * 0.97
                tp = price * 1.06
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
                            f"SQUEEZE RELEASE LONG: BB was inside KC (volatility compressed). "
                            f"Squeeze released with positive momentum={curr['momentum']:.2f}. "
                            f"Expecting explosive upward move. "
                            f"SL={sl:.2f} (-3%), TP={tp:.2f} (+6%)."
                        ),
                    },
                ))

            elif curr["momentum"] < 0 and curr["momentum"] < prev["momentum"]:
                strength = min(1.0, 0.7 + abs(curr["momentum"]) / price * 10)
                sl = price * 1.03
                tp = price * 0.94
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
                            f"SQUEEZE RELEASE SHORT: BB was inside KC (volatility compressed). "
                            f"Squeeze released with negative momentum={curr['momentum']:.2f}. "
                            f"Expecting explosive downward move. "
                            f"SL={sl:.2f} (+3%), TP={tp:.2f} (-6%)."
                        ),
                    },
                ))

        return signals

    def param_grid(self) -> dict[str, list]:
        return {
            "bb_period": [15, 20, 25],
            "bb_std": [1.5, 2.0, 2.5],
            "kc_period": [15, 20, 25],
            "kc_multiplier": [1.0, 1.5, 2.0],
            "mom_period": [8, 12, 16],
        }

    def param_defaults(self) -> dict:
        return {"bb_period": 20, "bb_std": 2.0, "kc_period": 20, "kc_multiplier": 1.5, "mom_period": 12}

    def param_descriptions(self) -> dict:
        return {
            "bb_period": "Bollinger Band period",
            "bb_std": "Bollinger Band std deviation multiplier",
            "kc_period": "Keltner Channel period",
            "kc_multiplier": "Keltner Channel ATR multiplier (lower = tighter squeeze detection)",
            "mom_period": "Momentum lookback for breakout direction",
        }

    def required_history(self) -> int:
        return max(self.bb_period, self.kc_period) + self.mom_period + 15
