"""Opportunity scanner for Volcanes — The Real Volcanoes."""

from __future__ import annotations

from volcanoes.domain import Candidate
from volcanoes.indicators.engine import IndicatorEngine
from volcanoes.market.sentinel import Sentinel
from volcanoes.scanner.momentum import score_momentum


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

        score, reasons = score_momentum(
            price=price,
            sma20=sma20,
            ema20=ema20,
            rsi14=rsi14,
        )

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
