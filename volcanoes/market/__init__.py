"""Market-data components for Volcanes."""

from volcanoes.market.bar import Bar
from volcanoes.market.feed import MarketFeed
from volcanoes.market.historical_feed import HistoricalFeed
from volcanoes.market.quote import Quote
from volcanoes.market.sentinel import (
    MarketSnapshot,
    Sentinel,
)

# Research-layer advanced indicators / scoring / news (optional imports)
try:
    from volcanoes.market.advanced_indicators import (
        AdvancedIndicatorSnapshot,
        add_advanced_indicators,
        interpret_advanced,
        last_advanced_snapshot,
    )
    from volcanoes.market.advanced_scoring import (
        AdvancedScoreResult,
        combine_scores,
        score_advanced,
    )
except ImportError:  # pragma: no cover - keep base market usable if optional deps missing
    AdvancedIndicatorSnapshot = None  # type: ignore
    add_advanced_indicators = None  # type: ignore
    interpret_advanced = None  # type: ignore
    last_advanced_snapshot = None  # type: ignore
    AdvancedScoreResult = None  # type: ignore
    combine_scores = None  # type: ignore
    score_advanced = None  # type: ignore

__all__ = [
    "Bar",
    "HistoricalFeed",
    "MarketFeed",
    "MarketSnapshot",
    "Quote",
    "Sentinel",
    "AdvancedIndicatorSnapshot",
    "AdvancedScoreResult",
    "add_advanced_indicators",
    "combine_scores",
    "interpret_advanced",
    "last_advanced_snapshot",
    "score_advanced",
]
