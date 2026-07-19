"""Position domain model for Volcanes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from volcanoes.domain.enums import TradeSide


@dataclass
class Position:
    """Represents the current holdings for a symbol."""

    symbol: str
    quantity: int
    average_price: float
    side: TradeSide = TradeSide.BUY

    current_price: float | None = None
    id: int | None = None

    updated_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()

        if not self.symbol:
            raise ValueError("Position symbol cannot be empty.")

        if self.quantity < 0:
            raise ValueError("Position quantity cannot be negative.")

        if self.average_price <= 0:
            raise ValueError("Average price must be greater than zero.")

        if self.current_price is not None and self.current_price <= 0:
            raise ValueError("Current price must be greater than zero.")

    @property
    def market_value(self) -> float | None:
        """Return the current market value."""

        if self.current_price is None:
            return None

        return self.current_price * self.quantity

    @property
    def unrealized_pnl(self) -> float | None:
        """Return the unrealized profit or loss."""

        if self.current_price is None:
            return None

        if self.side == TradeSide.BUY:
            return (
                self.current_price - self.average_price
            ) * self.quantity

        return (
            self.average_price - self.current_price
        ) * self.quantity

    @property
    def cost_basis(self) -> float:
        """Return the original cost basis."""

        return self.average_price * self.quantity
