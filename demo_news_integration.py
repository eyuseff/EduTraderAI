#!/usr/bin/env python3
"""
Demo: advanced scoring + news context (research only).

Uses the offline mock provider by default so no API key is required.
To try Finnhub live news:

    export FINNHUB_API_KEY=your_key_here
    export NEWS_PROVIDER=finnhub
    PYTHONPATH=. python3 demo_news_integration.py
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import numpy as np
import pandas as pd

from volcanoes.market.global_rotation_advanced_integration import (
    enrich_candidate_with_advanced,
)
from volcanoes.market.news_integration import enrich_views_with_news
from volcanoes.market.news_provider import get_news_provider


@dataclass(frozen=True)
class FakeCandidate:
    symbol: str
    region: str = "US"
    category: str = "esperar"
    edu_score: int = 70
    volcano_score: int = 65
    blockers: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    quantity: Decimal = Decimal("0")
    reward_risk_to_resistance: Decimal = Decimal("1.6")
    entry_usd: Decimal = Decimal("100")
    rsi14: Decimal = Decimal("55")


def _hist(seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = 260
    close = 120 + np.cumsum(rng.normal(0.05, 1.0, n))
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 1.2,
            "Low": close - 1.2,
            "Close": close,
            "Volume": rng.integers(60_000, 250_000, n).astype(float),
        },
        index=pd.bdate_range("2024-01-01", periods=n),
    )


def main() -> None:
    print("=" * 72)
    print("AI EMERS — News + Advanced Scoring Demo (research only)")
    print("=" * 72)

    provider = get_news_provider()
    print(f"\nActive news provider: {provider.name}")
    if provider.name == "offline_mock":
        print("(Set FINNHUB_API_KEY and NEWS_PROVIDER=finnhub for live headlines)")

    symbols = ["AAPL", "MSFT", "NVDA", "ORCL"]
    views = []
    for i, sym in enumerate(symbols):
        cand = FakeCandidate(sym, edu_score=70 + i * 3, volcano_score=60 + i * 2)
        views.append(enrich_candidate_with_advanced(cand, _hist(i + 1)))

    results = enrich_views_with_news(
        views,
        provider=provider,
        include_news_in_total=True,
    )

    print(
        f"\n{'Symbol':<8} {'Edu':>4} {'Vol':>4} {'Adv':>4} {'News':>5} "
        f"{'Total':>6}  Sentiment   Top headline"
    )
    print("-" * 72)
    for r in results:
        sent = r.news_context.sentiment_label if r.news_context else "—"
        top = ""
        if r.news_context and r.news_context.top_headlines:
            top = r.news_context.top_headlines[0][:42]
        print(
            f"{r.symbol:<8} {r.view.edu_score:>4} {r.view.volcano_score:>4} "
            f"{r.view.advanced_score:>4} {r.news_score:>5} {r.total_with_news:>6}  "
            f"{sent:<10}  {top}"
        )

    print("\n--- Detail: first symbol ---")
    first = results[0]
    print(f"Symbol        : {first.symbol}")
    print(f"Total (w/news): {first.total_with_news}")
    print(f"News reasons  :")
    for reason in first.news_reasons:
        print(f"  • {reason}")
    if first.news_context:
        print(f"Headlines ({first.news_context.headline_count}):")
        for h in first.news_context.top_headlines:
            print(f"  – {h}")
    print()


if __name__ == "__main__":
    main()
