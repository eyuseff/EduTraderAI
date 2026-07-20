"""Central risk validation engine."""

from decimal import Decimal

from volcanoes.domain import TradeRequest
from volcanoes.portfolio import Portfolio
from volcanoes.risk.exceptions import RiskViolation
from volcanoes.risk.risk_config import RiskConfig


class RiskManager:
    """Validate proposed trades against configured risk rules."""

    def __init__(self, config: RiskConfig | None = None):
        self.config = config or RiskConfig()

    def validate_trade(
        self,
        portfolio: Portfolio,
        trade: TradeRequest,
    ) -> bool:
        """
        Validate a proposed trade.

        Returns:
            True when every risk rule approves the trade.

        Raises:
            RiskViolation: When the trade violates a risk rule.
        """

        self._validate_buying_power(portfolio, trade)
        self._validate_position_size(portfolio, trade)

        return True

    def _validate_buying_power(
        self,
        portfolio: Portfolio,
        trade: TradeRequest,
    ) -> None:
        """Reject trades whose cost exceeds available buying power."""

        if trade.cost > portfolio.buying_power:
            raise RiskViolation(
                code="INSUFFICIENT_BUYING_POWER",
                message="Trade exceeds available buying power.",
            )

    def _validate_position_size(
        self,
        portfolio: Portfolio,
        trade: TradeRequest,
    ) -> None:
        """Reject trades that create an oversized position."""

        maximum_position_value = (
            portfolio.equity
            * self.config.max_position_size
        )

        existing_position = portfolio.get_position(
            trade.symbol
        )

        existing_position_value = Decimal("0.00")

        if existing_position is not None:
            existing_position_value = (
                Decimal(existing_position.quantity)
                * trade.price
            )

        projected_position_value = (
            existing_position_value
            + trade.cost
        )

        if projected_position_value > maximum_position_value:
            raise RiskViolation(
                code="MAX_POSITION_SIZE",
                message=(
                    "Trade exceeds maximum position size."
                ),
            )
