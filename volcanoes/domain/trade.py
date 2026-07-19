"""Trade domain model for Volcanes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from volcanoes.domain.enums import TradeSide, TradeStatus


@dataclass
class Trade:
    """Represents an executed trade."""

    symbol: str
    side: TradeSide
    quantity: int
    entry_price: float

    exit_price: float | None = None

    status: TradeStatus = TradeStatus.OPEN

    order_id: int | None = None
    id: int | None = None

    opened_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )
    closed_at: datetime | None = None

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()

        if not self.symbol:
            raise ValueError("Trade symbol cannot be empty.")

        if self.quantity <= 0:
            raise ValueError("Trade quantity must be positive.")

        if self.entry_price <= 0:
            raise ValueError("Entry price must be greater than zero.")

        if self.exit_price is not None and self.exit_price <= 0:
            raise ValueError("Exit price must be greater than zero.")

    @property
    def is_open(self) -> bool:
        return self.status == TradeStatus.OPEN

    @property
    def is_closed(self) -> bool:
        return self.status == TradeStatus.CLOSED

    @property
    def realized_pnl(self) -> float | None:
        """Return realized P&L once the trade is closed."""

        if self.exit_price is None:
            return None

        if self.side == TradeSide.BUY:
            return (self.exit_price - self.entry_price) * self.quantity

        return (self.entry_price - self.exit_price) * self.quantity
