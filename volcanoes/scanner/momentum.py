"""Pure Volcanes momentum scoring shared by live and injected-data scans."""

from __future__ import annotations


def score_momentum(
    *,
    price: float,
    sma20: float,
    ema20: float,
    rsi14: float,
) -> tuple[int, tuple[str, ...]]:
    score = 0
    reasons: list[str] = []
    if price > sma20:
        score += 35
        reasons.append("Price is above SMA20.")
    if price > ema20:
        score += 35
        reasons.append("Price is above EMA20.")
    if 50 <= rsi14 <= 70:
        score += 30
        reasons.append("RSI14 confirms positive momentum.")
    if not reasons:
        reasons.append("Momentum conditions were not confirmed.")
    return score, tuple(reasons)
