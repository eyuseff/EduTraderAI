"""Trade request domain model."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class TradeRequest:
    """Immutable trade request."""

    symbol: str
    quantity: int
    price: Decimal

    @property
    def cost(self) -> Decimal:
        """Total trade cost."""

        return Decimal(self.quantity) * self.price
