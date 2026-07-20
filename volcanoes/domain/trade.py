"""Trade domain model for Volcanes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from volcanoes.domain.enums import TradeSide, TradeStatus


@dataclass
class Trade:
    """Represents an executed trade."""

    symbol: str
    side: TradeSide
    quantity: int
    entry_price: Decimal

    id: int | None = None

    exit_price: Decimal | None = None

    status: TradeStatus = TradeStatus.OPEN

    commission: Decimal = field(default_factory=lambda: Decimal("0"))

    opened_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )
    closed_at: datetime | None = None

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()

        if not self.symbol:
            raise ValueError("Trade symbol cannot be empty.")

        if not isinstance(self.side, TradeSide):
            raise TypeError("Trade side must be a TradeSide value.")

        if self.quantity <= 0:
            raise ValueError("Trade quantity must be positive.")

        if self.entry_price <= Decimal("0"):
            raise ValueError("Entry price must be greater than zero.")

        if self.exit_price is not None and self.exit_price <= Decimal("0"):
            raise ValueError("Exit price must be greater than zero.")

    @property
    def is_open(self) -> bool:
        return self.status == TradeStatus.OPEN

    @property
    def is_closed(self) -> bool:
        return self.status == TradeStatus.CLOSED

    @property
    def entry_value(self) -> Decimal:
        """Total value at trade entry."""

        return Decimal(self.quantity) * self.entry_price

    @property
    def exit_value(self) -> Decimal | None:
        """Total value at trade exit."""

        if self.exit_price is None:
            return None

        return Decimal(self.quantity) * self.exit_price

    @property
    def realized_pnl(self) -> Decimal | None:
        """Realized profit/loss after commissions."""

        if self.exit_price is None:
            return None

        gross = (self.exit_price - self.entry_price) * Decimal(self.quantity)

        if self.side == TradeSide.SELL:
            gross = -gross

        return gross - self.commission
