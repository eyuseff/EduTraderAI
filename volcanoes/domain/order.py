"""Order domain model for Volcanes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from volcanoes.domain.enums import OrderStatus, TradeSide


@dataclass
class Order:
    """Represents an order submitted to a broker."""

    symbol: str
    side: TradeSide
    quantity: int
    price: Decimal
    stop_price: Decimal | None = field(default=None, kw_only=True)
    target_price: Decimal | None = field(default=None, kw_only=True)

    status: OrderStatus = OrderStatus.PENDING
    broker_order_id: str | None = None
    broker_status: str | None = field(default=None, kw_only=True)
    broker_message: str = field(default="", kw_only=True)
    rejection_reason: str | None = None

    id: int | None = None

    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    filled_at: datetime | None = None

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()

        if not self.symbol:
            raise ValueError("Order symbol cannot be empty.")

        if not isinstance(self.side, TradeSide):
            raise TypeError("Order side must be a TradeSide value.")

        if self.quantity <= 0:
            raise ValueError("Order quantity must be positive.")

        if self.price <= Decimal("0"):
            raise ValueError("Order price must be greater than zero.")

        if self.stop_price is not None and self.stop_price <= Decimal("0"):
            raise ValueError("Order stop price must be greater than zero.")

        if self.target_price is not None and self.target_price <= Decimal("0"):
            raise ValueError("Order target price must be greater than zero.")

    @property
    def notional_value(self) -> Decimal:
        """Return the total monetary value of the order."""

        return Decimal(self.quantity) * self.price

    @property
    def is_pending(self) -> bool:
        return self.status == OrderStatus.PENDING

    @property
    def is_filled(self) -> bool:
        return self.status == OrderStatus.FILLED

    @property
    def is_rejected(self) -> bool:
        return self.status == OrderStatus.REJECTED
