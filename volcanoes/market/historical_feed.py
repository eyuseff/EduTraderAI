"""In-memory historical market-data feed for Volcanes."""

from __future__ import annotations

from collections.abc import Iterable

from volcanoes.market.bar import Bar
from volcanoes.market.feed import MarketFeed


class HistoricalFeed(MarketFeed):
    """Sequential in-memory feed of validated market bars."""

    def __init__(self, bars: Iterable[Bar]) -> None:
        normalized_bars = list(bars)

        if any(not isinstance(bar, Bar) for bar in normalized_bars):
            raise TypeError(
                "HistoricalFeed accepts only Bar instances."
            )

        self._bars = sorted(
            normalized_bars,
            key=lambda bar: (bar.timestamp, bar.symbol),
        )
        self._index = 0

    @property
    def current_index(self) -> int:
        """Return the zero-based position of the next unread bar."""

        return self._index

    @property
    def total_bars(self) -> int:
        """Return the total number of bars in the feed."""

        return len(self._bars)

    @property
    def remaining_bars(self) -> int:
        """Return the number of unread bars."""

        return len(self._bars) - self._index

    @property
    def finished(self) -> bool:
        """Return whether every bar has been consumed."""

        return not self.has_next()

    def has_next(self) -> bool:
        """Return whether another bar is available."""

        return self._index < len(self._bars)

    def next_bar(self) -> Bar:
        """Return the next bar and advance the feed."""

        if not self.has_next():
            raise StopIteration("No historical market bars remain.")

        bar = self._bars[self._index]
        self._index += 1

        return bar

    def peek(self) -> Bar:
        """Return the next bar without advancing the feed."""

        if not self.has_next():
            raise StopIteration("No historical market bars remain.")

        return self._bars[self._index]

    def reset(self) -> None:
        """Reset the feed to its initial position."""

        self._index = 0
