"""Immutable domain models for position sizing."""

from dataclasses import dataclass
from decimal import Decimal

from volcanoes.domain import TradeIntent


@dataclass(frozen=True)
class PositionSizingRequest:
    """
    Represent the inputs required to calculate a position size.

    The maximum risk is expressed as a decimal fraction of portfolio
    equity. For example, Decimal("0.01") represents one percent.
    """

    portfolio_equity: Decimal
    trade_intent: TradeIntent
    maximum_risk: Decimal

    def __post_init__(self) -> None:
        """Validate the position-sizing inputs."""

        if self.portfolio_equity <= Decimal("0"):
            raise ValueError(
                "Portfolio equity must be greater than zero."
            )

        if self.maximum_risk <= Decimal("0"):
            raise ValueError(
                "Maximum risk must be greater than zero."
            )

        if self.maximum_risk > Decimal("1"):
            raise ValueError(
                "Maximum risk cannot exceed one."
            )

    @property
    def allowed_risk(self) -> Decimal:
        """Return the maximum dollar amount that may be risked."""

        return self.portfolio_equity * self.maximum_risk


@dataclass(frozen=True)
class PositionSizingResult:
    """
    Represent the output produced by a position-sizing calculation.

    Quantity is the number of whole units that may be traded.
    Dollar risk is the total amount at risk at the stop price.
    Position value is the total notional value at the entry price.
    """

    quantity: int
    dollar_risk: Decimal
    position_value: Decimal

    def __post_init__(self) -> None:
        """Validate the position-sizing result."""

        if isinstance(self.quantity, bool):
            raise ValueError(
                "Quantity must be a whole number."
            )

        if not isinstance(self.quantity, int):
            raise ValueError(
                "Quantity must be a whole number."
            )

        if self.quantity < 0:
            raise ValueError(
                "Quantity cannot be negative."
            )

        if self.dollar_risk < Decimal("0"):
            raise ValueError(
                "Dollar risk cannot be negative."
            )

        if self.position_value < Decimal("0"):
            raise ValueError(
                "Position value cannot be negative."
            )

        if self.quantity == 0:
            if self.dollar_risk != Decimal("0"):
                raise ValueError(
                    "Zero quantity must have zero dollar risk."
                )

            if self.position_value != Decimal("0"):
                raise ValueError(
                    "Zero quantity must have zero position value."
                )

        if self.quantity > 0:
            if self.dollar_risk <= Decimal("0"):
                raise ValueError(
                    "Positive quantity requires positive dollar risk."
                )

            if self.position_value <= Decimal("0"):
                raise ValueError(
                    "Positive quantity requires positive position value."
                )
