"""
Technical Indicator Engine
Volcanes — The Real Volcanoes
"""

from __future__ import annotations

import pandas as pd


class IndicatorEngine:
    """Computes technical indicators from market history."""

    def __init__(self, history: pd.DataFrame):
        self.history = history.copy()

    @property
    def close(self):
        return self.history["Close"]

    def sma(self, period: int = 20):
        return self.close.rolling(period).mean()

    def ema(self, period: int = 20):
        return self.close.ewm(span=period, adjust=False).mean()

    def rsi(self, period: int = 14):
        delta = self.close.diff()

        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()

        rs = avg_gain / avg_loss

        return 100 - (100 / (1 + rs))

    def last(self):
        return {
            "SMA20": float(self.sma(20).iloc[-1]),
            "EMA20": float(self.ema(20).iloc[-1]),
            "RSI14": float(self.rsi(14).iloc[-1]),
        }
