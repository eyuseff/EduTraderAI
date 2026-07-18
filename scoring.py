"""
EduTrader AI
Professional Scoring Engine
"""

from config import (
    TREND_WEIGHT,
    EMA_WEIGHT,
    MACD_WEIGHT,
    RSI_WEIGHT,
    ATR_WEIGHT,
    LOW_VOLATILITY,
    MEDIUM_VOLATILITY,
)


class ScoringEngine:

    def calculate(self, stock: dict) -> tuple[int, list[str]]:

        score = 0
        reasons = []

        # -------------------------------------------------
        # Long-term Trend
        # -------------------------------------------------

        if stock["Price"] > stock["SMA200"]:
            score += TREND_WEIGHT
            reasons.append(
                f"Price above SMA200 (+{TREND_WEIGHT})"
            )

        else:
            reasons.append(
                "Price below SMA200"
            )

        # -------------------------------------------------
        # Medium-term Trend
        # -------------------------------------------------

        if stock["EMA20"] > stock["EMA50"]:
            score += EMA_WEIGHT
            reasons.append(
                f"EMA20 above EMA50 (+{EMA_WEIGHT})"
            )

        else:
            reasons.append(
                "EMA20 below EMA50"
            )

        # -------------------------------------------------
        # MACD
        # -------------------------------------------------

        if stock["MACD"] > stock["Signal"]:
            score += MACD_WEIGHT
            reasons.append(
                f"MACD bullish crossover (+{MACD_WEIGHT})"
            )

        else:
            reasons.append(
                "MACD below signal"
            )

        # -------------------------------------------------
        # RSI
        # -------------------------------------------------

        rsi = stock["RSI"]

        if 40 <= rsi <= 60:

            score += RSI_WEIGHT

            reasons.append(
                f"Healthy RSI ({rsi:.1f}) (+{RSI_WEIGHT})"
            )

        elif 30 <= rsi < 40 or 60 < rsi <= 70:

            partial = int(RSI_WEIGHT * 0.6)

            score += partial

            reasons.append(
                f"Acceptable RSI ({rsi:.1f}) (+{partial})"
            )

        else:

            reasons.append(
                f"Extreme RSI ({rsi:.1f})"
            )

        # -------------------------------------------------
        # ATR
        # -------------------------------------------------

        atr_percent = (
            stock["ATR"] / stock["Price"] * 100
        )

        if atr_percent < LOW_VOLATILITY:

            score += ATR_WEIGHT

            reasons.append(
                f"Low volatility ({atr_percent:.2f}%) (+{ATR_WEIGHT})"
            )

        elif atr_percent < MEDIUM_VOLATILITY:

            partial = int(ATR_WEIGHT * 0.5)

            score += partial

            reasons.append(
                f"Moderate volatility ({atr_percent:.2f}%) (+{partial})"
            )

        else:

            reasons.append(
                f"High volatility ({atr_percent:.2f}%)"
            )

        return score, reasons