"""Abstract trading strategy."""

from __future__ import annotations

from abc import ABC, abstractmethod

from volcanoes.domain.trade_intent import TradeIntent
from volcanoes.market import Bar


class Strategy(ABC):
    """Base class for every trading strategy."""

    @abstractmethod
    def on_bar(
        self,
        bar: Bar,
    ) -> TradeIntent | None:
        """
        Process one market bar.

        Returns
        -------
        TradeIntent | None
            Trade to execute, or None if no signal exists.
        """
        raise NotImplementedError
