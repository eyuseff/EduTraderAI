from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketRegime:
    label: str
    score: int
    tradeable: bool
    reasons: list[str]


def classify_market(spy_close: float, spy_sma50: float, spy_sma200: float, volatility_pct: float) -> MarketRegime:
    score = 0
    reasons: list[str] = []
    if spy_close > spy_sma200:
        score += 45
        reasons.append("SPY is above its 200-day moving average.")
    else:
        reasons.append("SPY is below its 200-day moving average.")
    if spy_sma50 > spy_sma200:
        score += 30
        reasons.append("The 50-day average is above the 200-day average.")
    else:
        reasons.append("The 50-day average is not above the 200-day average.")
    if volatility_pct <= 2.5:
        score += 25
        reasons.append("Recent volatility is within the permitted range.")
    else:
        reasons.append("Recent volatility is elevated.")

    if score >= 75:
        return MarketRegime("Bullish", score, True, reasons)
    if score >= 45:
        return MarketRegime("Cautious", score, False, reasons)
    return MarketRegime("Risk-Off", score, False, reasons)
