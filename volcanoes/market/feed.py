"""Market-feed abstraction for Volcanes."""

from __future__ import annotations

from abc import ABC, abstractmethod

from volcanoes.market.bar import Bar


class MarketFeed(ABC):
    """Abstract sequential source of historical market bars."""

    @abstractmethod
    def has_next(self) -> bool:
        """Return whether another bar is available."""
        raise NotImplementedError

    @abstractmethod
    def next_bar(self) -> Bar:
        """Return the next available market bar."""
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        """Reset the feed to its initial position."""
        raise NotImplementedError
