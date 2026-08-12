"""Build executable trade requests from trading decisions."""

from volcanoes.domain import (
    TradeIntent,
    TradeRequest,
)
from volcanoes.sizing import PositionSizingResult


class OrderBuilder:
    """
    Convert a TradeIntent and a PositionSizingResult into a TradeRequest.

    This component isolates execution from strategy and sizing.
    """

    def build(
        self,
        trade_intent: TradeIntent,
        sizing_result: PositionSizingResult,
    ) -> TradeRequest:
        """Create an executable trade request."""

        return TradeRequest(
            symbol=trade_intent.symbol,
            quantity=sizing_result.quantity,
            price=trade_intent.entry_price,
        )
