"""Portfolio domain service for Volcanes."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from volcanoes.domain import Position


@dataclass
class Portfolio:
    """Represents the current trading account."""

    starting_cash: Decimal

    cash: Decimal = field(init=False)

    positions: dict[str, Position] = field(default_factory=dict)

    realized_pnl: Decimal = field(
        default_factory=lambda: Decimal("0.00")
    )

    def __post_init__(self) -> None:
        if self.starting_cash <= Decimal("0"):
            raise ValueError(
                "Starting cash must be greater than zero."
            )

        self.cash = self.starting_cash

    @property
    def invested_value(self) -> Decimal:
        """Cost basis of all open positions."""

        return sum(
            (
                position.market_value
                for position in self.positions.values()
            ),
            start=Decimal("0.00"),
        )

    @property
    def equity(self) -> Decimal:
        """Current account equity."""

        return self.cash + self.invested_value

    @property
    def buying_power(self) -> Decimal:
        """Available buying power."""

        return self.cash

    def has_position(self, symbol: str) -> bool:
        return symbol.strip().upper() in self.positions

    def get_position(self, symbol: str) -> Position | None:
        return self.positions.get(symbol.strip().upper())

    def buy(
        self,
        symbol: str,
        quantity: int,
        price: Decimal,
    ) -> None:
        """Record a purchase."""

        if quantity <= 0:
            raise ValueError(
                "Quantity must be positive."
            )

        cost = Decimal(quantity) * price

        if cost > self.cash:
            raise ValueError(
                "Insufficient cash."
            )

        symbol = symbol.strip().upper()

        self.cash -= cost

        if symbol not in self.positions:
            self.positions[symbol] = Position(
                symbol=symbol,
                quantity=quantity,
                average_price=price,
            )
            return

        self.positions[symbol].update_average_price(
            quantity,
            price,
        )

    def sell(
        self,
        symbol: str,
        quantity: int,
        price: Decimal,
    ) -> None:
        """Record a sale."""

        symbol = symbol.strip().upper()

        if symbol not in self.positions:
            raise ValueError(
                "No position exists."
            )

        position = self.positions[symbol]

        if quantity > position.quantity:
            raise ValueError(
                "Cannot sell more than owned."
            )

        proceeds = Decimal(quantity) * price

        pnl = (
            price - position.average_price
        ) * Decimal(quantity)

        self.realized_pnl += pnl

        self.cash += proceeds

        position.quantity -= quantity

        if position.quantity == 0:
            del self.positions[symbol]
