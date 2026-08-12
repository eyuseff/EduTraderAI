"""Position domain model for Volcanes."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class Position:
    """Represents an open portfolio position."""

    symbol: str
    quantity: int
    average_price: Decimal

    id: int |None = None

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()

        if not self.symbol:
            raise ValueError("Position symbol cannot be empty.")

        if self.quantity < 0:
            raise ValueError("Position quantity cannot be negative.")

        if self.average_price < Decimal("0"):
            raise ValueError("Average price cannot be negative.")

    @property
    def market_value(self) -> Decimal:
        """Current position cost basis."""

        return Decimal(self.quantity) * self.average_price

    def update_average_price(
        self,
        purchase_quantity: int,
        purchase_price: Decimal,
    ) -> None:
        """Update weighted average price after a purchase."""

        if purchase_quantity <= 0:
            raise ValueError("Purchase quantity must be positive.")

        if purchase_price <= Decimal("0"):
            raise ValueError("Purchase price must be positive.")

        total_cost = (
            self.market_value
            + Decimal(purchase_quantity) * purchase_price
        )

        self.quantity += purchase_quantity
        self.average_price = total_cost / Decimal(self.quantity)
