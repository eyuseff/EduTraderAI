"""
EduTrader AI
Strategy Engine

Converts the AI score into a trading recommendation.
"""

from dataclasses import dataclass

from config import (
    STRONG_BUY_THRESHOLD,
    BUY_THRESHOLD,
    HOLD_THRESHOLD,
    SELL_THRESHOLD,
)

from scoring import ScoringEngine


@dataclass
class StrategyResult:
    score: int
    recommendation: str
    confidence: int
    stars: str
    reasons: list[str]


class StrategyEngine:

    def __init__(self):

        self.scoring = ScoringEngine()

    def evaluate(self, stock: dict) -> StrategyResult:

        score, reasons = self.scoring.calculate(stock)

        recommendation, stars = self._recommendation(score)

        confidence = score

        return StrategyResult(
            score=score,
            recommendation=recommendation,
            confidence=confidence,
            stars=stars,
            reasons=reasons,
        )

    def _recommendation(self, score: int):

        if score >= STRONG_BUY_THRESHOLD:
            return "STRONG BUY", "★★★★★"

        if score >= BUY_THRESHOLD:
            return "BUY", "★★★★☆"

        if score >= HOLD_THRESHOLD:
            return "HOLD", "★★★☆☆"

        if score >= SELL_THRESHOLD:
            return "SELL", "★★☆☆☆"

        return "STRONG SELL", "★☆☆☆☆"