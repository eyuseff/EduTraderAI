"""Strategy that intentionally produces no trades."""

from __future__ import annotations

from volcanoes.domain.trade_intent import TradeIntent
from volcanoes.market import Bar

from .strategy import Strategy


class NoOpStrategy(Strategy):
    """Reference strategy that never trades."""

    def on_bar(
        self,
        bar: Bar,
    ) -> TradeIntent | None:
        return None
