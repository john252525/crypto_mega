"""
Strategy: Volume Spike Momentum

Detects abnormal volume spikes and trades in the direction of the move.
High frequency — volume spikes happen often in crypto.
"""

import numpy as np
import pandas as pd

from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig


class VolumeSpike(BaseStrategy):
    """Volume spike detector — rides the momentum of abnormal volume."""

    DESCRIPTION = (
        "Detects abnormal volume spikes (2x+ above average) and trades the direction "
        "of the candle. Big volume = institutional activity or whale moves. "
        "LONG on bullish volume spikes, SHORT on bearish. "
        "Active strategy — crypto has lots of volume anomalies."
    )
    CATEGORY = "momentum"
    RISK_LEVEL = "high"
    BEST_TIMEFRAMES = ["5m", "15m", "1h"]
    BEST_MARKETS = ["volatile", "trending"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.vol_avg_period = config.parameters.get("vol_avg_period", 20)
        self.spike_threshold = config.parameters.get("spike_threshold", 2.0)
        self.min_body_pct = config.parameters.get("min_body_pct", 0.003)

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for key, df in data.items():
            if len(df) < self.vol_avg_period + 5:
                continue

            symbol = key.split("_")[0]
            df = df.copy()

            df["vol_avg"] = df["volume"].rolling(self.vol_avg_period).mean()
            df["vol_ratio"] = df["volume"] / df["vol_avg"].replace(0, np.nan)
            df["body_pct"] = (df["close"] - df["open"]) / df["open"]

            df = df.dropna()
            if len(df) < 1:
                continue

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
                "volume_ratio": round(curr["vol_ratio"], 2),
                "body_pct": round(curr["body_pct"] * 100, 4),
                "vol_avg": round(curr["vol_avg"], 2),
                "current_volume": round(curr["volume"], 2),
                "candles": candles,
            }

            if curr["vol_ratio"] < self.spike_threshold:
                continue

            # Bullish volume spike
            if curr["body_pct"] > self.min_body_pct:
                strength = min(1.0, 0.4 + curr["vol_ratio"] / 10 + abs(curr["body_pct"]) * 20)
                sl = price * 0.985
                tp = price * 1.03
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
                            f"Bullish volume spike: {curr['vol_ratio']:.1f}x average volume "
                            f"with +{curr['body_pct']*100:.2f}% bullish candle. "
                            f"Likely institutional buying. SL={sl:.2f}, TP={tp:.2f}."
                        ),
                    },
                ))

            # Bearish volume spike
            elif curr["body_pct"] < -self.min_body_pct:
                strength = min(1.0, 0.4 + curr["vol_ratio"] / 10 + abs(curr["body_pct"]) * 20)
                sl = price * 1.015
                tp = price * 0.97
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
                            f"Bearish volume spike: {curr['vol_ratio']:.1f}x average volume "
                            f"with {curr['body_pct']*100:.2f}% bearish candle. "
                            f"Likely institutional selling. SL={sl:.2f}, TP={tp:.2f}."
                        ),
                    },
                ))

        return signals

    def param_grid(self) -> dict[str, list]:
        return {
            "vol_avg_period": [10, 20, 30],
            "spike_threshold": [1.5, 2.0, 2.5, 3.0],
            "min_body_pct": [0.001, 0.003, 0.005],
        }

    def param_defaults(self) -> dict:
        return {"vol_avg_period": 20, "spike_threshold": 2.0, "min_body_pct": 0.003}

    def param_descriptions(self) -> dict:
        return {
            "vol_avg_period": "Period for average volume calculation",
            "spike_threshold": "Volume must be Nx above average (lower = more signals)",
            "min_body_pct": "Minimum candle body size to confirm direction",
        }

    def required_history(self) -> int:
        return self.vol_avg_period + 10
