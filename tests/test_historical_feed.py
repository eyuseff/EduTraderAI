"""Tests for the HistoricalFeed implementation."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from volcanoes.market import Bar, HistoricalFeed, MarketFeed


def create_bar(
    symbol: str,
    timestamp: datetime,
    close: str,
) -> Bar:
    """Create a valid flat-price bar for testing."""

    price = Decimal(close)

    return Bar(
        symbol=symbol,
        timestamp=timestamp,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=100,
    )


def test_historical_feed_is_market_feed() -> None:
    feed = HistoricalFeed([])

    assert isinstance(feed, MarketFeed)


def test_historical_feed_accepts_empty_collection() -> None:
    feed = HistoricalFeed([])

    assert feed.total_bars == 0
    assert feed.remaining_bars == 0
    assert feed.current_index == 0
    assert feed.has_next() is False
    assert feed.finished is True


def test_historical_feed_returns_bars_in_sequence() -> None:
    first = create_bar(
        symbol="AAPL",
        timestamp=datetime(2026, 7, 20, 14, 30, tzinfo=UTC),
        close="200",
    )
    second = create_bar(
        symbol="AAPL",
        timestamp=datetime(2026, 7, 21, 14, 30, tzinfo=UTC),
        close="205",
    )

    feed = HistoricalFeed([first, second])

    assert feed.next_bar() == first
    assert feed.next_bar() == second
    assert feed.has_next() is False


def test_historical_feed_sorts_bars_by_timestamp() -> None:
    earlier = create_bar(
        symbol="MSFT",
        timestamp=datetime(2026, 7, 20, 14, 30, tzinfo=UTC),
        close="500",
    )
    later = create_bar(
        symbol="AAPL",
        timestamp=datetime(2026, 7, 21, 14, 30, tzinfo=UTC),
        close="200",
    )

    feed = HistoricalFeed([later, earlier])

    assert feed.next_bar() == earlier
    assert feed.next_bar() == later


def test_historical_feed_sorts_equal_timestamps_by_symbol() -> None:
    timestamp = datetime(2026, 7, 20, 14, 30, tzinfo=UTC)

    msft = create_bar(
        symbol="MSFT",
        timestamp=timestamp,
        close="500",
    )
    aapl = create_bar(
        symbol="AAPL",
        timestamp=timestamp,
        close="200",
    )

    feed = HistoricalFeed([msft, aapl])

    assert feed.next_bar() == aapl
    assert feed.next_bar() == msft


def test_historical_feed_peek_does_not_advance() -> None:
    bar = create_bar(
        symbol="AAPL",
        timestamp=datetime(2026, 7, 20, 14, 30, tzinfo=UTC),
        close="200",
    )
    feed = HistoricalFeed([bar])

    assert feed.peek() == bar
    assert feed.current_index == 0
    assert feed.remaining_bars == 1

    assert feed.next_bar() == bar
    assert feed.current_index == 1


def test_historical_feed_tracks_progress() -> None:
    start = datetime(2026, 7, 20, 14, 30, tzinfo=UTC)

    bars = [
        create_bar(
            symbol="AAPL",
            timestamp=start + timedelta(days=index),
            close=str(200 + index),
        )
        for index in range(3)
    ]

    feed = HistoricalFeed(bars)

    assert feed.current_index == 0
    assert feed.total_bars == 3
    assert feed.remaining_bars == 3
    assert feed.finished is False

    feed.next_bar()

    assert feed.current_index == 1
    assert feed.remaining_bars == 2
    assert feed.finished is False


def test_historical_feed_reset_restarts_sequence() -> None:
    bar = create_bar(
        symbol="AAPL",
        timestamp=datetime(2026, 7, 20, 14, 30, tzinfo=UTC),
        close="200",
    )
    feed = HistoricalFeed([bar])

    assert feed.next_bar() == bar
    assert feed.finished is True

    feed.reset()

    assert feed.current_index == 0
    assert feed.remaining_bars == 1
    assert feed.finished is False
    assert feed.next_bar() == bar


def test_historical_feed_next_bar_raises_when_exhausted() -> None:
    feed = HistoricalFeed([])

    with pytest.raises(
        StopIteration,
        match="No historical market bars remain",
    ):
        feed.next_bar()


def test_historical_feed_peek_raises_when_exhausted() -> None:
    feed = HistoricalFeed([])

    with pytest.raises(
        StopIteration,
        match="No historical market bars remain",
    ):
        feed.peek()


def test_historical_feed_rejects_non_bar_items() -> None:
    with pytest.raises(
        TypeError,
        match="accepts only Bar instances",
    ):
        HistoricalFeed(["not-a-bar"])  # type: ignore[list-item]


def test_historical_feed_copies_input_collection() -> None:
    bar = create_bar(
        symbol="AAPL",
        timestamp=datetime(2026, 7, 20, 14, 30, tzinfo=UTC),
        close="200",
    )
    source = [bar]

    feed = HistoricalFeed(source)
    source.clear()

    assert feed.total_bars == 1
    assert feed.next_bar() == bar
