"""Fixed-fractional position-sizing engine."""

from decimal import ROUND_FLOOR

from volcanoes.sizing.models import (
    PositionSizingRequest,
    PositionSizingResult,
)


class PositionSizer:
    """
    Calculate position size using fixed-fractional risk sizing.

    The calculation uses portfolio equity, maximum permitted risk,
    entry price, and stop price to determine the maximum whole-unit
    quantity that does not exceed the allowed dollar risk.
    """

    def size_position(
        self,
        request: PositionSizingRequest,
    ) -> PositionSizingResult:
        """
        Calculate and return a risk-based position size.

        Quantity is always rounded down so the calculated dollar risk
        never exceeds the request's allowed risk.
        """

        risk_per_share = request.trade_intent.risk_per_share

        quantity_decimal = (
            request.allowed_risk / risk_per_share
        ).to_integral_value(rounding=ROUND_FLOOR)

        quantity = int(quantity_decimal)

        if quantity == 0:
            return PositionSizingResult(
                quantity=0,
                dollar_risk=request.allowed_risk * 0,
                position_value=request.allowed_risk * 0,
            )

        dollar_risk = (
            risk_per_share
            * quantity
        )

        position_value = (
            request.trade_intent.entry_price
            * quantity
        )

        return PositionSizingResult(
            quantity=quantity,
            dollar_risk=dollar_risk,
            position_value=position_value,
        )
