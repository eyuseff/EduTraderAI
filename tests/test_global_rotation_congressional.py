from datetime import date
from decimal import Decimal

import pytest

from global_rotation.congressional import (
    CongressionalTrade,
    parse_congressional_snapshot,
    score_congressional_activity,
)


def _trade(
    *,
    politician: str,
    side: str = "purchase",
    traded_on: date = date(2026, 9, 12),
    published_on: date = date(2026, 9, 14),
    high: str = "100000",
) -> CongressionalTrade:
    return CongressionalTrade(
        symbol="AAA",
        politician=politician,
        transaction_type=side,
        traded_on=traded_on,
        published_on=published_on,
        amount_low_usd=Decimal("50000"),
        amount_high_usd=Decimal(high),
        source="capitoltrades",
    )


def test_future_publication_is_excluded_to_prevent_lookahead():
    signal = score_congressional_activity(
        "AAA",
        [_trade(politician="Person A", published_on=date(2026, 9, 17))],
        as_of=date(2026, 9, 16),
    )

    assert signal.available is False
    assert signal.priority_adjustment == 0


def test_recent_independent_purchases_create_positive_research_priority():
    signal = score_congressional_activity(
        "AAA",
        [_trade(politician="Person A"), _trade(politician="Person B")],
        as_of=date(2026, 9, 16),
    )

    assert signal.available is True
    assert signal.direction == "bullish"
    assert signal.score >= 60
    assert signal.priority_adjustment > 0
    assert signal.unique_purchase_traders == 2


def test_sales_are_directionally_negative_without_changing_execution_rules():
    signal = score_congressional_activity(
        "AAA",
        [
            _trade(politician="Person A", side="sale"),
            _trade(politician="Person B", side="sale"),
        ],
        as_of=date(2026, 9, 16),
    )

    assert signal.direction == "bearish"
    assert signal.priority_adjustment < 0
    assert signal.sale_count == 2


def test_long_disclosure_lag_scores_lower_than_prompt_disclosure():
    prompt = score_congressional_activity(
        "AAA",
        [
            _trade(
                politician="Person A",
                traded_on=date(2026, 9, 13),
                published_on=date(2026, 9, 14),
            )
        ],
        as_of=date(2026, 9, 16),
    )
    delayed = score_congressional_activity(
        "AAA",
        [
            _trade(
                politician="Person A",
                traded_on=date(2026, 8, 1),
                published_on=date(2026, 9, 14),
            )
        ],
        as_of=date(2026, 9, 16),
    )

    assert prompt.score > delayed.score
    assert prompt.median_disclosure_lag_days == 1.0
    assert delayed.median_disclosure_lag_days == 44.0


def test_snapshot_parser_preserves_source_and_rejects_invalid_amount_range():
    payload = {
        "schema_version": 1,
        "source": "capitoltrades",
        "as_of": "2026-09-16",
        "trades": [
            {
                "symbol": "AAA",
                "politician": "Person A",
                "transaction_type": "purchase",
                "traded_on": "2026-09-12",
                "published_on": "2026-09-14",
                "amount_low_usd": "50000",
                "amount_high_usd": "100000",
                "committees": ["Committee A"],
            }
        ],
    }
    snapshot = parse_congressional_snapshot(payload)
    assert snapshot.source == "capitoltrades"
    assert snapshot.trades[0].source == "capitoltrades"
    assert snapshot.trades[0].committees == ("Committee A",)

    payload["trades"][0]["amount_high_usd"] = "100"
    with pytest.raises(ValueError, match="amount_high_usd"):
        parse_congressional_snapshot(payload)
