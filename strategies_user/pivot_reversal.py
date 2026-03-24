"""
Strategy: Pivot Point Reversal

Mean-reversion strategy using classic floor trader pivot points.
Trades reversals at pivot support/resistance levels.
Medium frequency — depends on price reaching pivot levels.
"""

import numpy as np
import pandas as pd

from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig


class PivotReversal(BaseStrategy):
    """Pivot point reversal — bounces off classic S/R levels."""

    DESCRIPTION = (
        "Mean-reversion at classic pivot points (floor trader pivots). "
        "Calculates Pivot, S1, S2, R1, R2 from prior period high/low/close. "
        "LONG when price touches S1/S2 and shows reversal candle. "
        "SHORT when price touches R1/R2 and shows reversal candle. "
        "Medium frequency, works well with clear range markets."
    )
    CATEGORY = "mean-reversion"
    RISK_LEVEL = "low"
    BEST_TIMEFRAMES = ["1h", "4h"]
    BEST_MARKETS = ["ranging", "sideways"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.pivot_lookback = config.parameters.get("pivot_lookback", 24)
        self.proximity_pct = config.parameters.get("proximity_pct", 0.003)
        self.reversal_body_pct = config.parameters.get("reversal_body_pct", 0.001)

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for key, df in data.items():
            if len(df) < self.pivot_lookback + 5:
                continue

            symbol = key.split("_")[0]
            df = df.copy()

            # Calculate pivots from the lookback period
            lookback = df.iloc[-(self.pivot_lookback + 1):-1]
            period_high = lookback["high"].max()
            period_low = lookback["low"].min()
            period_close = lookback["close"].iloc[-1]

            pivot = (period_high + period_low + period_close) / 3
            r1 = 2 * pivot - period_low
            s1 = 2 * pivot - period_high
            r2 = pivot + (period_high - period_low)
            s2 = pivot - (period_high - period_low)

            curr = df.iloc[-1]
            prev = df.iloc[-2]
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
                "pivot": round(pivot, 2),
                "r1": round(r1, 2),
                "r2": round(r2, 2),
                "s1": round(s1, 2),
                "s2": round(s2, 2),
                "candles": candles,
            }

            # Reversal candle: previous candle was bearish, current is bullish (or vice versa)
            bullish_reversal = prev["close"] < prev["open"] and curr["close"] > curr["open"]
            bearish_reversal = prev["close"] > prev["open"] and curr["close"] < curr["open"]

            body_size = abs(curr["close"] - curr["open"]) / curr["open"]

            # LONG at S1 or S2
            for level_name, level in [("S1", s1), ("S2", s2)]:
                dist = abs(curr["low"] - level) / level
                if dist < self.proximity_pct and bullish_reversal and body_size > self.reversal_body_pct:
                    strength = min(1.0, 0.5 + (1 - dist / self.proximity_pct) * 0.3 + body_size * 50)
                    sl = level * 0.99
                    tp = pivot
                    signals.append(Signal(
                        symbol=symbol,
                        direction=SignalDirection.LONG,
                        strength=strength,
                        price=price,
                        stop_loss=sl,
                        take_profit=tp,
                        metadata={
                            **base_meta,
                            "level": level_name,
                            "level_value": round(level, 2),
                            "reason": (
                                f"Pivot reversal LONG at {level_name}={level:.2f}. "
                                f"Price touched support (dist {dist*100:.3f}%) with bullish reversal candle. "
                                f"Body size {body_size*100:.3f}%. "
                                f"TP at pivot {pivot:.2f}, SL below {level_name} at {sl:.2f}."
                            ),
                        },
                    ))
                    break

            # SHORT at R1 or R2
            for level_name, level in [("R1", r1), ("R2", r2)]:
                dist = abs(curr["high"] - level) / level
                if dist < self.proximity_pct and bearish_reversal and body_size > self.reversal_body_pct:
                    strength = min(1.0, 0.5 + (1 - dist / self.proximity_pct) * 0.3 + body_size * 50)
                    sl = level * 1.01
                    tp = pivot
                    signals.append(Signal(
                        symbol=symbol,
                        direction=SignalDirection.SHORT,
                        strength=strength,
                        price=price,
                        stop_loss=sl,
                        take_profit=tp,
                        metadata={
                            **base_meta,
                            "level": level_name,
                            "level_value": round(level, 2),
                            "reason": (
                                f"Pivot reversal SHORT at {level_name}={level:.2f}. "
                                f"Price touched resistance (dist {dist*100:.3f}%) with bearish reversal candle. "
                                f"Body size {body_size*100:.3f}%. "
                                f"TP at pivot {pivot:.2f}, SL above {level_name} at {sl:.2f}."
                            ),
                        },
                    ))
                    break

        return signals

    def param_grid(self) -> dict[str, list]:
        return {
            "pivot_lookback": [12, 24, 48],
            "proximity_pct": [0.002, 0.003, 0.005],
            "reversal_body_pct": [0.0005, 0.001, 0.002],
        }

    def param_defaults(self) -> dict:
        return {"pivot_lookback": 24, "proximity_pct": 0.003, "reversal_body_pct": 0.001}

    def param_descriptions(self) -> dict:
        return {
            "pivot_lookback": "Bars to calculate pivot levels from",
            "proximity_pct": "How close price must be to level (lower = more precise, fewer signals)",
            "reversal_body_pct": "Minimum candle body for reversal confirmation",
        }

    def required_history(self) -> int:
        return self.pivot_lookback + 10
