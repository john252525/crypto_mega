"""
Strategy: OBV (On-Balance Volume) Momentum

Volume-price confirmation strategy using OBV trend.
Signals when OBV diverges from price or confirms trend with EMA crossover.
Medium frequency.
"""

import numpy as np
import pandas as pd

from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig


class OBVMomentum(BaseStrategy):
    """OBV momentum — confirms price moves with volume flow."""

    DESCRIPTION = (
        "Volume-based confirmation strategy using On-Balance Volume. "
        "OBV tracks cumulative buying/selling pressure. "
        "LONG when OBV breaks above its EMA (accumulation phase). "
        "SHORT when OBV breaks below its EMA (distribution phase). "
        "Also detects OBV-price divergences for early reversal signals."
    )
    CATEGORY = "momentum"
    RISK_LEVEL = "medium"
    BEST_TIMEFRAMES = ["1h", "4h"]
    BEST_MARKETS = ["trending", "ranging"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.obv_ema_period = config.parameters.get("obv_ema_period", 20)
        self.price_ema_period = config.parameters.get("price_ema_period", 20)
        self.divergence_lookback = config.parameters.get("divergence_lookback", 10)

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for key, df in data.items():
            if len(df) < max(self.obv_ema_period, self.price_ema_period) + self.divergence_lookback + 5:
                continue

            symbol = key.split("_")[0]
            df = df.copy()

            # OBV calculation
            obv_changes = np.where(
                df["close"] > df["close"].shift(1),
                df["volume"],
                np.where(df["close"] < df["close"].shift(1), -df["volume"], 0),
            )
            df["obv"] = pd.Series(obv_changes, index=df.index).cumsum()

            # OBV EMA
            df["obv_ema"] = df["obv"].ewm(span=self.obv_ema_period, adjust=False).mean()

            # Price EMA for divergence detection
            df["price_ema"] = df["close"].ewm(span=self.price_ema_period, adjust=False).mean()

            df = df.dropna()
            if len(df) < 3:
                continue

            prev = df.iloc[-2]
            curr = df.iloc[-1]
            price = curr["close"]

            # Check for OBV-price divergence
            recent = df.tail(self.divergence_lookback)
            price_change = (recent["close"].iloc[-1] - recent["close"].iloc[0]) / recent["close"].iloc[0]
            obv_change = recent["obv"].iloc[-1] - recent["obv"].iloc[0]
            obv_normalized = obv_change / (abs(recent["obv"].iloc[0]) + 1)

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
                "obv": round(curr["obv"], 0),
                "obv_ema": round(curr["obv_ema"], 0),
                "price_change_pct": round(price_change * 100, 3),
                "obv_trend": "up" if obv_change > 0 else "down",
                "candles": candles,
            }

            # OBV crossover signals
            if prev["obv"] <= prev["obv_ema"] and curr["obv"] > curr["obv_ema"]:
                strength = min(1.0, 0.6 + abs(obv_normalized) * 5)
                sl = price * 0.98
                tp = price * 1.035
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.LONG,
                    strength=strength,
                    price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "signal_type": "obv_crossover",
                        "reason": (
                            f"OBV crossed above its EMA — accumulation confirmed. "
                            f"OBV={curr['obv']:.0f} > EMA={curr['obv_ema']:.0f}. "
                            f"Buying pressure increasing. SL={sl:.2f}, TP={tp:.2f}."
                        ),
                    },
                ))

            elif prev["obv"] >= prev["obv_ema"] and curr["obv"] < curr["obv_ema"]:
                strength = min(1.0, 0.6 + abs(obv_normalized) * 5)
                sl = price * 1.02
                tp = price * 0.965
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.SHORT,
                    strength=strength,
                    price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "signal_type": "obv_crossover",
                        "reason": (
                            f"OBV crossed below its EMA — distribution confirmed. "
                            f"OBV={curr['obv']:.0f} < EMA={curr['obv_ema']:.0f}. "
                            f"Selling pressure increasing. SL={sl:.2f}, TP={tp:.2f}."
                        ),
                    },
                ))

            # Divergence signals (price goes one way, OBV the other)
            elif price_change < -0.01 and obv_change > 0 and curr["obv"] > curr["obv_ema"]:
                # Bullish divergence: price down but OBV up
                strength = min(1.0, 0.55 + abs(price_change) * 10)
                sl = price * 0.975
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
                        "signal_type": "bullish_divergence",
                        "reason": (
                            f"Bullish OBV divergence: price down {price_change*100:.2f}% "
                            f"but OBV rising (accumulation). Smart money buying the dip. "
                            f"SL={sl:.2f}, TP={tp:.2f}."
                        ),
                    },
                ))

            elif price_change > 0.01 and obv_change < 0 and curr["obv"] < curr["obv_ema"]:
                # Bearish divergence: price up but OBV down
                strength = min(1.0, 0.55 + abs(price_change) * 10)
                sl = price * 1.025
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
                        "signal_type": "bearish_divergence",
                        "reason": (
                            f"Bearish OBV divergence: price up {price_change*100:.2f}% "
                            f"but OBV falling (distribution). Smart money selling into strength. "
                            f"SL={sl:.2f}, TP={tp:.2f}."
                        ),
                    },
                ))

        return signals

    def param_grid(self) -> dict[str, list]:
        return {
            "obv_ema_period": [10, 20, 30],
            "price_ema_period": [10, 20, 30],
            "divergence_lookback": [5, 10, 15],
        }

    def param_defaults(self) -> dict:
        return {"obv_ema_period": 20, "price_ema_period": 20, "divergence_lookback": 10}

    def param_descriptions(self) -> dict:
        return {
            "obv_ema_period": "EMA period for smoothing OBV",
            "price_ema_period": "EMA period for price trend",
            "divergence_lookback": "Bars to check for OBV-price divergence",
        }

    def required_history(self) -> int:
        return max(self.obv_ema_period, self.price_ema_period) + self.divergence_lookback + 20
