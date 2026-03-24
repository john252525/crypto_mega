"""
Strategy: VWAP Bounce (Scalper)

High-frequency scalping strategy using Volume-Weighted Average Price.
BUY when price dips below VWAP and bounces back above.
SELL when price spikes above VWAP and drops back below.

Very active — designed to generate lots of signals for stat accumulation.
"""

import numpy as np
import pandas as pd

from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig


class VWAPBounce(BaseStrategy):
    """VWAP bounce scalper — catches quick reversions to volume-weighted mean."""

    DESCRIPTION = (
        "High-frequency scalping strategy. Uses VWAP as dynamic support/resistance. "
        "LONG when price dips below VWAP and bounces back — mean reversion play. "
        "SHORT when price spikes above VWAP and reverses. Very active, tight SL/TP. "
        "Best on 5m-15m for liquid pairs (BTC, ETH)."
    )
    CATEGORY = "scalping"
    RISK_LEVEL = "high"
    BEST_TIMEFRAMES = ["5m", "15m"]
    BEST_MARKETS = ["ranging", "sideways"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.vwap_period = config.parameters.get("vwap_period", 20)
        self.bounce_threshold = config.parameters.get("bounce_threshold", 0.001)
        self.sl_pct = config.parameters.get("sl_pct", 0.01)
        self.tp_pct = config.parameters.get("tp_pct", 0.015)

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for key, df in data.items():
            if len(df) < self.vwap_period + 5:
                continue

            symbol = key.split("_")[0]
            df = df.copy()

            # Calculate VWAP
            typical_price = (df["high"] + df["low"] + df["close"]) / 3
            vol = df["volume"].replace(0, np.nan).fillna(1)
            df["vwap"] = (typical_price * vol).rolling(self.vwap_period).sum() / vol.rolling(self.vwap_period).sum()

            # Distance from VWAP
            df["vwap_dist"] = (df["close"] - df["vwap"]) / df["vwap"]

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
                "vwap": round(curr["vwap"], 2),
                "vwap_dist_pct": round(curr["vwap_dist"] * 100, 4),
                "vwap_period": self.vwap_period,
                "candles": candles,
            }

            # LONG: price was below VWAP and bounced back above
            if (prev["close"] < prev["vwap"]
                    and curr["close"] > curr["vwap"]
                    and abs(prev["vwap_dist"]) > self.bounce_threshold):
                strength = min(1.0, 0.5 + abs(prev["vwap_dist"]) * 50)
                sl = price * (1 - self.sl_pct)
                tp = price * (1 + self.tp_pct)
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
                            f"VWAP bounce LONG: price crossed above VWAP {curr['vwap']:.2f}. "
                            f"Was {abs(prev['vwap_dist'])*100:.3f}% below. "
                            f"Tight scalp: SL={sl:.2f} (-{self.sl_pct*100:.1f}%), "
                            f"TP={tp:.2f} (+{self.tp_pct*100:.1f}%)."
                        ),
                    },
                ))

            # SHORT: price was above VWAP and dropped back below
            elif (prev["close"] > prev["vwap"]
                    and curr["close"] < curr["vwap"]
                    and abs(prev["vwap_dist"]) > self.bounce_threshold):
                strength = min(1.0, 0.5 + abs(prev["vwap_dist"]) * 50)
                sl = price * (1 + self.sl_pct)
                tp = price * (1 - self.tp_pct)
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
                            f"VWAP bounce SHORT: price crossed below VWAP {curr['vwap']:.2f}. "
                            f"Was {abs(prev['vwap_dist'])*100:.3f}% above. "
                            f"Tight scalp: SL={sl:.2f} (+{self.sl_pct*100:.1f}%), "
                            f"TP={tp:.2f} (-{self.tp_pct*100:.1f}%)."
                        ),
                    },
                ))

        return signals

    def param_grid(self) -> dict[str, list]:
        return {
            "vwap_period": [10, 15, 20, 30],
            "bounce_threshold": [0.0005, 0.001, 0.002],
            "sl_pct": [0.005, 0.01, 0.015],
            "tp_pct": [0.01, 0.015, 0.02],
        }

    def param_defaults(self) -> dict:
        return {"vwap_period": 20, "bounce_threshold": 0.001, "sl_pct": 0.01, "tp_pct": 0.015}

    def param_descriptions(self) -> dict:
        return {
            "vwap_period": "Rolling VWAP calculation window",
            "bounce_threshold": "Min distance from VWAP to trigger (lower = more signals)",
            "sl_pct": "Stop loss as fraction of price",
            "tp_pct": "Take profit as fraction of price",
        }

    def required_history(self) -> int:
        return self.vwap_period + 20
