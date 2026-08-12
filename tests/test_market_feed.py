"""Tests for the MarketFeed abstraction."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from volcanoes.market import Bar, MarketFeed


class InMemoryTestFeed(MarketFeed):
    """Minimal feed implementation used to verify the interface."""

    def __init__(self, bars: list[Bar]) -> None:
        self._bars = list(bars)
        self._index = 0

    def has_next(self) -> bool:
        return self._index < len(self._bars)

    def next_bar(self) -> Bar:
        if not self.has_next():
            raise StopIteration("No market bars remain.")

        bar = self._bars[self._index]
        self._index += 1
        return bar

    def reset(self) -> None:
        self._index = 0


def create_bar(symbol: str, close: str) -> Bar:
    price = Decimal(close)

    return Bar(
        symbol=symbol,
        timestamp=datetime(2026, 7, 20, 14, 30, tzinfo=UTC),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=100,
    )


def test_market_feed_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        MarketFeed()  # type: ignore[abstract]


def test_market_feed_returns_bars_in_sequence() -> None:
    first = create_bar("AAPL", "200")
    second = create_bar("MSFT", "500")
    feed = InMemoryTestFeed([first, second])

    assert feed.has_next() is True
    assert feed.next_bar() == first
    assert feed.has_next() is True
    assert feed.next_bar() == second
    assert feed.has_next() is False


def test_market_feed_raises_stop_iteration_when_exhausted() -> None:
    feed = InMemoryTestFeed([])

    with pytest.raises(StopIteration, match="No market bars remain"):
        feed.next_bar()


def test_market_feed_reset_restarts_sequence() -> None:
    bar = create_bar("AAPL", "200")
    feed = InMemoryTestFeed([bar])

    assert feed.next_bar() == bar
    assert feed.has_next() is False

    feed.reset()

    assert feed.has_next() is True
    assert feed.next_bar() == bar
