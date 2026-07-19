from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategySignal:
    symbol: str
    score: int
    entry_price: float
    stop_price: float
    target_price: float
    average_volume: float
    daily_change_pct: float
    reasons: list[str]


def score_candidate(*, symbol: str, close: float, sma20: float, sma50: float, rsi14: float,
                    atr14: float, average_volume: float, daily_change_pct: float) -> StrategySignal:
    score = 0
    reasons: list[str] = []
    if close > sma20:
        score += 25
        reasons.append("Price is above SMA20.")
    if sma20 > sma50:
        score += 25
        reasons.append("SMA20 is above SMA50.")
    if 50 <= rsi14 <= 70:
        score += 20
        reasons.append("RSI shows constructive momentum without extreme overbought conditions.")
    elif 40 <= rsi14 < 50:
        score += 8
        reasons.append("RSI is neutral.")
    if average_volume >= 1_000_000:
        score += 15
        reasons.append("Liquidity filter passed.")
    if 0 < daily_change_pct <= 4.0:
        score += 15
        reasons.append("Positive daily momentum is within the permitted range.")

    stop_distance = max(atr14 * 1.5, close * 0.02)
    entry = round(close, 2)
    stop = round(max(0.01, entry - stop_distance), 2)
    target = round(entry + 2.2 * (entry - stop), 2)
    return StrategySignal(
        symbol=symbol,
        score=min(score, 100),
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        average_volume=average_volume,
        daily_change_pct=daily_change_pct,
        reasons=reasons,
    )
