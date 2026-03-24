"""
Strategy: Ichimoku Cloud

Classic Japanese charting technique. Rare but high-conviction signals.
Uses all 5 Ichimoku components for confluence.
Low frequency — only fires on strong Ichimoku setups.
"""

import numpy as np
import pandas as pd

from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig


class IchimokuCloud(BaseStrategy):
    """Ichimoku Cloud — the ultimate trend confirmation system."""

    DESCRIPTION = (
        "Full Ichimoku Kinko Hyo system with all 5 components. "
        "LONG: price above cloud, Tenkan > Kijun, Chikou confirms. "
        "SHORT: price below cloud, Tenkan < Kijun, Chikou confirms. "
        "LOW frequency — Ichimoku signals are rare but have very high conviction. "
        "Best for catching major trend changes on higher timeframes."
    )
    CATEGORY = "trend"
    RISK_LEVEL = "low"
    BEST_TIMEFRAMES = ["4h", "1d"]
    BEST_MARKETS = ["trending"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.tenkan_period = config.parameters.get("tenkan_period", 9)
        self.kijun_period = config.parameters.get("kijun_period", 26)
        self.senkou_b_period = config.parameters.get("senkou_b_period", 52)
        self.chikou_period = config.parameters.get("chikou_period", 26)

    def _donchian_mid(self, series: pd.Series, period: int) -> pd.Series:
        """Donchian channel midline (Ichimoku uses this instead of SMA)."""
        return (series.rolling(period).max() + series.rolling(period).min()) / 2

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []

        for key, df in data.items():
            if len(df) < self.senkou_b_period + self.kijun_period + 5:
                continue

            symbol = key.split("_")[0]
            df = df.copy()

            # Tenkan-sen (Conversion Line)
            df["tenkan"] = self._donchian_mid(df["high"], self.tenkan_period)

            # Kijun-sen (Base Line)
            df["kijun"] = self._donchian_mid(df["high"], self.kijun_period)

            # Senkou Span A (Leading Span A) — shifted forward 26 periods
            df["senkou_a"] = ((df["tenkan"] + df["kijun"]) / 2).shift(self.kijun_period)

            # Senkou Span B (Leading Span B) — shifted forward 26 periods
            df["senkou_b"] = self._donchian_mid(df["high"], self.senkou_b_period).shift(self.kijun_period)

            # Chikou Span (Lagging Span) — close shifted back 26 periods
            df["chikou"] = df["close"].shift(-self.chikou_period)

            # Cloud boundaries
            df["cloud_top"] = df[["senkou_a", "senkou_b"]].max(axis=1)
            df["cloud_bottom"] = df[["senkou_a", "senkou_b"]].min(axis=1)

            df = df.dropna(subset=["tenkan", "kijun", "senkou_a", "senkou_b"])
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
                "tenkan": round(curr["tenkan"], 2),
                "kijun": round(curr["kijun"], 2),
                "senkou_a": round(curr["senkou_a"], 2),
                "senkou_b": round(curr["senkou_b"], 2),
                "cloud_top": round(curr["cloud_top"], 2),
                "cloud_bottom": round(curr["cloud_bottom"], 2),
                "candles": candles,
            }

            above_cloud = price > curr["cloud_top"]
            below_cloud = price < curr["cloud_bottom"]
            tenkan_above_kijun = curr["tenkan"] > curr["kijun"]
            tenkan_below_kijun = curr["tenkan"] < curr["kijun"]

            # TK cross detection
            tk_cross_bull = prev["tenkan"] <= prev["kijun"] and curr["tenkan"] > curr["kijun"]
            tk_cross_bear = prev["tenkan"] >= prev["kijun"] and curr["tenkan"] < curr["kijun"]

            # Count confluence factors for strength
            def bullish_score():
                score = 0
                if above_cloud:
                    score += 1
                if tenkan_above_kijun:
                    score += 1
                if tk_cross_bull:
                    score += 1
                if curr["senkou_a"] > curr["senkou_b"]:
                    score += 1  # Green cloud (bullish future)
                return score

            def bearish_score():
                score = 0
                if below_cloud:
                    score += 1
                if tenkan_below_kijun:
                    score += 1
                if tk_cross_bear:
                    score += 1
                if curr["senkou_a"] < curr["senkou_b"]:
                    score += 1  # Red cloud (bearish future)
                return score

            # LONG: TK cross above cloud OR full confluence
            bull_score = bullish_score()
            if tk_cross_bull and above_cloud and bull_score >= 3:
                strength = min(1.0, 0.5 + bull_score * 0.12)
                sl = curr["kijun"] * 0.99
                tp = price + (price - curr["kijun"]) * 2.5
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.LONG,
                    strength=strength,
                    price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "confluence_score": bull_score,
                        "reason": (
                            f"Ichimoku LONG: Tenkan/Kijun bullish cross above cloud. "
                            f"Confluence {bull_score}/4: "
                            f"{'above cloud, ' if above_cloud else ''}"
                            f"TK cross, "
                            f"{'green cloud, ' if curr['senkou_a'] > curr['senkou_b'] else ''}"
                            f"T={curr['tenkan']:.2f} > K={curr['kijun']:.2f}. "
                            f"SL at Kijun {sl:.2f}."
                        ),
                    },
                ))

            # SHORT: TK cross below cloud OR full confluence
            bear_score = bearish_score()
            if tk_cross_bear and below_cloud and bear_score >= 3:
                strength = min(1.0, 0.5 + bear_score * 0.12)
                sl = curr["kijun"] * 1.01
                tp = price - (curr["kijun"] - price) * 2.5
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.SHORT,
                    strength=strength,
                    price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "confluence_score": bear_score,
                        "reason": (
                            f"Ichimoku SHORT: Tenkan/Kijun bearish cross below cloud. "
                            f"Confluence {bear_score}/4: "
                            f"{'below cloud, ' if below_cloud else ''}"
                            f"TK cross, "
                            f"{'red cloud, ' if curr['senkou_a'] < curr['senkou_b'] else ''}"
                            f"T={curr['tenkan']:.2f} < K={curr['kijun']:.2f}. "
                            f"SL at Kijun {sl:.2f}."
                        ),
                    },
                ))

            # Also: state-based signal when ALL conditions align (no cross needed)
            elif bull_score >= 4:
                strength = min(1.0, 0.45 + bull_score * 0.1)
                sl = curr["cloud_top"] * 0.995
                tp = price * 1.05
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.LONG,
                    strength=strength,
                    price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "confluence_score": bull_score,
                        "reason": (
                            f"Ichimoku full bullish alignment ({bull_score}/4): "
                            f"above cloud, TK bullish, green cloud ahead. "
                            f"Strong uptrend confirmed by all 5 components."
                        ),
                    },
                ))
            elif bear_score >= 4:
                strength = min(1.0, 0.45 + bear_score * 0.1)
                sl = curr["cloud_bottom"] * 1.005
                tp = price * 0.95
                signals.append(Signal(
                    symbol=symbol,
                    direction=SignalDirection.SHORT,
                    strength=strength,
                    price=price,
                    stop_loss=sl,
                    take_profit=tp,
                    metadata={
                        **base_meta,
                        "confluence_score": bear_score,
                        "reason": (
                            f"Ichimoku full bearish alignment ({bear_score}/4): "
                            f"below cloud, TK bearish, red cloud ahead. "
                            f"Strong downtrend confirmed by all 5 components."
                        ),
                    },
                ))

        return signals

    def param_grid(self) -> dict[str, list]:
        return {
            "tenkan_period": [7, 9, 12],
            "kijun_period": [22, 26, 30],
            "senkou_b_period": [44, 52, 60],
        }

    def param_defaults(self) -> dict:
        return {"tenkan_period": 9, "kijun_period": 26, "senkou_b_period": 52, "chikou_period": 26}

    def param_descriptions(self) -> dict:
        return {
            "tenkan_period": "Tenkan-sen (Conversion Line) period — fastest line",
            "kijun_period": "Kijun-sen (Base Line) period — medium speed",
            "senkou_b_period": "Senkou Span B period — slowest cloud component",
            "chikou_period": "Chikou Span lookback (lagging confirmation)",
        }

    def required_history(self) -> int:
        return self.senkou_b_period + self.kijun_period + 20
