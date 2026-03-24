"""
Strategy: MACD Divergence

Detects divergences between MACD histogram and price.
Bullish divergence: price makes lower low but MACD makes higher low → LONG
Bearish divergence: price makes higher high but MACD makes lower high → SHORT

Medium frequency — fires on divergence confirmation candle.
"""

import numpy as np
import pandas as pd

from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig


class MACDDivergence(BaseStrategy):
    """MACD histogram divergence — catches trend reversals early."""

    DESCRIPTION = (
        "Detects divergences between price action and MACD histogram. "
        "Bullish divergence (price lower low, MACD higher low) signals reversal up. "
        "Bearish divergence (price higher high, MACD lower high) signals reversal down. "
        "Medium frequency — only fires when divergence is confirmed."
    )
    CATEGORY = "momentum"
    RISK_LEVEL = "medium"
    BEST_TIMEFRAMES = ["1h", "4h"]
    BEST_MARKETS = ["trending", "volatile"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.fast_period = config.parameters.get("fast_period", 12)
        self.slow_period = config.parameters.get("slow_period", 26)
        self.signal_period = config.parameters.get("signal_period", 9)
        self.lookback = config.parameters.get("lookback", 20)

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for key, df in data.items():
            if len(df) < self.slow_period + self.signal_period + self.lookback:
                continue

            symbol = key.split("_")[0]
            df = df.copy()

            # MACD
            ema_fast = df["close"].ewm(span=self.fast_period, adjust=False).mean()
            ema_slow = df["close"].ewm(span=self.slow_period, adjust=False).mean()
            df["macd_line"] = ema_fast - ema_slow
            df["macd_signal"] = df["macd_line"].ewm(span=self.signal_period, adjust=False).mean()
            df["macd_hist"] = df["macd_line"] - df["macd_signal"]

            df = df.dropna()
            if len(df) < self.lookback + 2:
                continue

            recent = df.tail(self.lookback)
            price = recent["close"].values
            hist = recent["macd_hist"].values

            last = df.iloc[-1]
            curr_price = last["close"]

            # Find local lows/highs in the lookback window
            # Bullish divergence: price lower low, histogram higher low
            price_min_idx = np.argmin(price[-10:])
            price_min_prev_idx = np.argmin(price[:10])

            hist_min_idx = np.argmin(hist[-10:])
            hist_min_prev_idx = np.argmin(hist[:10])

            # Bearish divergence: price higher high, histogram lower high
            price_max_idx = np.argmax(price[-10:])
            price_max_prev_idx = np.argmax(price[:10])

            hist_max_idx = np.argmax(hist[-10:])
            hist_max_prev_idx = np.argmax(hist[:10])

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
                "macd_line": round(last["macd_line"], 4),
                "macd_signal": round(last["macd_signal"], 4),
                "macd_hist": round(last["macd_hist"], 4),
                "fast_period": self.fast_period,
                "slow_period": self.slow_period,
                "signal_period": self.signal_period,
                "candles": candles,
            }

            # Bullish divergence
            if (price[-10:][price_min_idx] < price[:10][price_min_prev_idx]
                    and hist[-10:][hist_min_idx] > hist[:10][hist_min_prev_idx]
                    and last["macd_hist"] > hist[-10:][hist_min_idx]):
                strength = min(1.0, 0.6 + abs(last["macd_hist"]) * 10)
                sl = curr_price * 0.97
                tp = curr_price * 1.05
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.LONG,
                    strength=strength,
                    price=curr_price,
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "divergence_type": "bullish",
                        "reason": (
                            f"Bullish MACD divergence: price made lower low but MACD histogram "
                            f"made higher low. MACD hist={last['macd_hist']:.4f}, "
                            f"confirming upward momentum shift. "
                            f"SL={sl:.2f} (-3%), TP={tp:.2f} (+5%)."
                        ),
                    },
                ))

            # Bearish divergence
            elif (price[-10:][price_max_idx] > price[:10][price_max_prev_idx]
                    and hist[-10:][hist_max_idx] < hist[:10][hist_max_prev_idx]
                    and last["macd_hist"] < hist[-10:][hist_max_idx]):
                strength = min(1.0, 0.6 + abs(last["macd_hist"]) * 10)
                sl = curr_price * 1.03
                tp = curr_price * 0.95
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.SHORT,
                    strength=strength,
                    price=curr_price,
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "divergence_type": "bearish",
                        "reason": (
                            f"Bearish MACD divergence: price made higher high but MACD histogram "
                            f"made lower high. MACD hist={last['macd_hist']:.4f}, "
                            f"confirming downward momentum shift. "
                            f"SL={sl:.2f} (+3%), TP={tp:.2f} (-5%)."
                        ),
                    },
                ))

        return signals

    def param_grid(self) -> dict[str, list]:
        return {
            "fast_period": [8, 12, 16],
            "slow_period": [21, 26, 34],
            "signal_period": [5, 9, 12],
            "lookback": [15, 20, 30],
        }

    def param_defaults(self) -> dict:
        return {"fast_period": 12, "slow_period": 26, "signal_period": 9, "lookback": 20}

    def param_descriptions(self) -> dict:
        return {
            "fast_period": "Fast EMA for MACD line",
            "slow_period": "Slow EMA for MACD line",
            "signal_period": "Signal line EMA period",
            "lookback": "Window to detect divergences (more bars = rarer signals)",
        }

    def required_history(self) -> int:
        return self.slow_period + self.signal_period + self.lookback + 10
