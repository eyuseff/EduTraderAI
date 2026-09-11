"""
Optional news contribution to the research score.

News never auto-executes trades. It only:
  - adds a small, bounded score adjustment (−5 … +5)
  - attaches context for the advisory UI
  - can add a soft informational flag (not a hard blocker)
"""

from __future__ import annotations

from dataclasses import dataclass

from volcanoes.market.news_provider import NewsContext


# Bounded news contribution
NEWS_SCORE_MIN = -5
NEWS_SCORE_MAX = 5

# Sentiment thresholds for points
SENTIMENT_STRONG_POS = 0.35
SENTIMENT_MILD_POS = 0.15
SENTIMENT_MILD_NEG = -0.15
SENTIMENT_STRONG_NEG = -0.35

STRONG_POS_PTS = 4
MILD_POS_PTS = 2
MILD_NEG_PTS = -2
STRONG_NEG_PTS = -4
NO_NEWS_PTS = 0


@dataclass(frozen=True, slots=True)
class NewsScoreResult:
    score: int
    reasons: tuple[str, ...]
    context: NewsContext

    def clamped_score(self) -> int:
        return max(NEWS_SCORE_MIN, min(NEWS_SCORE_MAX, self.score))


def score_news(context: NewsContext) -> NewsScoreResult:
    """
    Translate news context into a small score adjustment.

    Rules (explicit):
    - No headlines / error → 0 points, informational reason.
    - Average sentiment strong positive → +4
    - Mild positive → +2
    - Mild negative → −2
    - Strong negative → −4
    - Neutral or unknown sentiment with headlines → 0 (still listed)
    """
    reasons: list[str] = []
    score = 0

    if context.error:
        reasons.append(f"News unavailable ({context.error}).")
        return NewsScoreResult(score=0, reasons=tuple(reasons), context=context)

    if context.headline_count == 0:
        reasons.append("No recent headlines.")
        return NewsScoreResult(score=0, reasons=tuple(reasons), context=context)

    sent = context.average_sentiment
    label = context.sentiment_label

    if sent is None:
        reasons.append(
            f"{context.headline_count} recent headline(s), sentiment unknown."
        )
        score = NO_NEWS_PTS
    elif sent >= SENTIMENT_STRONG_POS:
        score = STRONG_POS_PTS
        reasons.append(
            f"Strong positive news sentiment ({sent:+.2f}) (+{STRONG_POS_PTS})"
        )
    elif sent >= SENTIMENT_MILD_POS:
        score = MILD_POS_PTS
        reasons.append(
            f"Mild positive news sentiment ({sent:+.2f}) (+{MILD_POS_PTS})"
        )
    elif sent <= SENTIMENT_STRONG_NEG:
        score = STRONG_NEG_PTS
        reasons.append(
            f"Strong negative news sentiment ({sent:+.2f}) ({STRONG_NEG_PTS})"
        )
    elif sent <= SENTIMENT_MILD_NEG:
        score = MILD_NEG_PTS
        reasons.append(
            f"Mild negative news sentiment ({sent:+.2f}) ({MILD_NEG_PTS})"
        )
    else:
        reasons.append(f"Neutral news sentiment ({sent:+.2f}).")
        score = NO_NEWS_PTS

    # Surface top headline for the advisory UI
    if context.top_headlines:
        reasons.append(f"Top: {context.top_headlines[0][:120]}")

    return NewsScoreResult(
        score=score,
        reasons=tuple(reasons),
        context=context,
    )
