"""
Example Strategy: RSI + Bollinger Bands

Mean-reversion strategy: buy when RSI is oversold AND price touches lower Bollinger Band.
"""

import numpy as np
import pandas as pd

from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig


class RSIBollinger(BaseStrategy):
    """RSI + Bollinger Bands mean-reversion."""

    DESCRIPTION = (
        "Mean-reversion strategy that catches bounces from extremes. "
        "BUY when RSI shows oversold (<30) AND price is at the lower "
        "Bollinger Band. SELL when RSI is overbought (>70) AND price "
        "hits the upper band. Best for ranging/sideways markets. "
        "Avoid during strong trends — will get chopped up."
    )
    CATEGORY = "mean-reversion"
    RISK_LEVEL = "medium"
    BEST_TIMEFRAMES = ["15m", "1h", "4h"]
    BEST_MARKETS = ["ranging", "sideways"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.rsi_period = config.parameters.get("rsi_period", 14)
        self.bb_period = config.parameters.get("bb_period", 20)
        self.bb_std = config.parameters.get("bb_std", 2.0)
        self.rsi_oversold = config.parameters.get("rsi_oversold", 30)
        self.rsi_overbought = config.parameters.get("rsi_overbought", 70)

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for key, df in data.items():
            if len(df) < max(self.rsi_period, self.bb_period) + 5:
                continue

            symbol = key.split("_")[0]
            df = df.copy()

            # RSI
            delta = df["close"].diff()
            gain = delta.clip(lower=0).rolling(self.rsi_period).mean()
            loss = (-delta.clip(upper=0)).rolling(self.rsi_period).mean()
            rs = gain / loss.replace(0, np.nan)
            df["rsi"] = 100 - (100 / (1 + rs))

            # Bollinger Bands
            df["bb_mid"] = df["close"].rolling(self.bb_period).mean()
            bb_std = df["close"].rolling(self.bb_period).std()
            df["bb_upper"] = df["bb_mid"] + self.bb_std * bb_std
            df["bb_lower"] = df["bb_mid"] - self.bb_std * bb_std

            df = df.dropna()
            if len(df) < 1:
                continue

            last = df.iloc[-1]

            # Recent candles for detail view
            recent = df.tail(10)
            candles = [
                {
                    "t": str(row.get("timestamp", "")),
                    "o": round(row["open"], 2),
                    "h": round(row["high"], 2),
                    "l": round(row["low"], 2),
                    "c": round(row["close"], 2),
                    "v": round(row["volume"], 2) if row.get("volume") else 0,
                }
                for _, row in recent.iterrows()
            ]

            base_meta = {
                "rsi": round(last["rsi"], 2),
                "bb_upper": round(last["bb_upper"], 2),
                "bb_mid": round(last["bb_mid"], 2),
                "bb_lower": round(last["bb_lower"], 2),
                "rsi_period": self.rsi_period,
                "bb_period": self.bb_period,
                "bb_std": self.bb_std,
                "candles": candles,
            }

            if last["rsi"] < self.rsi_oversold and last["close"] <= last["bb_lower"]:
                sl = last["close"] * 0.97
                tp = last["bb_mid"]
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.LONG,
                    strength=min(1.0, (self.rsi_oversold - last["rsi"]) / 30 + 0.5),
                    price=last["close"],
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "reason": (
                            f"Mean-reversion BUY: RSI={last['rsi']:.1f} < {self.rsi_oversold} (oversold) "
                            f"AND price {last['close']:.2f} <= BB lower {last['bb_lower']:.2f}. "
                            f"BB range: [{last['bb_lower']:.2f} — {last['bb_mid']:.2f} — {last['bb_upper']:.2f}]. "
                            f"Expecting bounce to BB mid. SL={sl:.2f} (-3%), TP={tp:.2f} (BB mid)."
                        ),
                    },
                ))

            elif last["rsi"] > self.rsi_overbought and last["close"] >= last["bb_upper"]:
                sl = last["close"] * 1.03
                tp = last["bb_mid"]
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.SHORT,
                    strength=min(1.0, (last["rsi"] - self.rsi_overbought) / 30 + 0.5),
                    price=last["close"],
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "reason": (
                            f"Mean-reversion SELL: RSI={last['rsi']:.1f} > {self.rsi_overbought} (overbought) "
                            f"AND price {last['close']:.2f} >= BB upper {last['bb_upper']:.2f}. "
                            f"BB range: [{last['bb_lower']:.2f} — {last['bb_mid']:.2f} — {last['bb_upper']:.2f}]. "
                            f"Expecting pullback to BB mid. SL={sl:.2f} (+3%), TP={tp:.2f} (BB mid)."
                        ),
                    },
                ))

        return signals

    def param_grid(self) -> dict[str, list]:
        return {
            "rsi_period": [7, 14, 21],
            "bb_period": [15, 20, 25],
            "bb_std": [1.5, 2.0, 2.5],
            "rsi_oversold": [25, 30, 35],
            "rsi_overbought": [65, 70, 75],
        }

    def param_defaults(self) -> dict:
        return {
            "rsi_period": 14,
            "bb_period": 20,
            "bb_std": 2.0,
            "rsi_oversold": 30,
            "rsi_overbought": 70,
        }

    def param_descriptions(self) -> dict:
        return {
            "rsi_period": "RSI lookback period (shorter = more signals, more noise)",
            "bb_period": "Bollinger Band SMA period",
            "bb_std": "Bollinger Band width in standard deviations (wider = fewer signals)",
            "rsi_oversold": "RSI level to consider oversold (buy zone)",
            "rsi_overbought": "RSI level to consider overbought (sell zone)",
        }

    def required_history(self) -> int:
        return max(self.rsi_period, self.bb_period) + 20
