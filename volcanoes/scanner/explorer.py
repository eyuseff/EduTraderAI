"""Opportunity scanner for Volcanes — The Real Volcanoes."""

from __future__ import annotations

from volcanoes.domain import Candidate
from volcanoes.indicators.engine import IndicatorEngine
from volcanoes.market.sentinel import Sentinel


class Explorer:
    """Scan symbols and generate explainable trade candidates."""

    def __init__(self, sentinel: Sentinel | None = None) -> None:
        self.sentinel = sentinel or Sentinel()

    def evaluate_symbol(self, symbol: str) -> Candidate:
        """Evaluate one symbol using a simple momentum strategy."""

        history = self.sentinel.download_history(
            symbol,
            period="6mo",
            interval="1d",
        )

        indicators = IndicatorEngine(history)
        latest = indicators.last()

        price = float(history["Close"].iloc[-1])
        sma20 = latest["SMA20"]
        ema20 = latest["EMA20"]
        rsi14 = latest["RSI14"]

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

        return Candidate(
            symbol=symbol,
            strategy_name="Momentum",
            score=score,
            entry_price=price,
            explanation=" ".join(reasons),
        )

    def scan_symbols(self, symbols: list[str]) -> list[Candidate]:
        """Scan multiple symbols and return candidates sorted by score."""

        candidates: list[Candidate] = []

        for symbol in symbols:
            try:
                candidates.append(self.evaluate_symbol(symbol))
            except Exception as exc:
                print(f"Skipping {symbol}: {exc}")

        candidates.sort(key=lambda candidate: candidate.score, reverse=True)

        return candidates
