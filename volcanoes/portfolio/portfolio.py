"""Portfolio domain service for Volcanes."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from volcanoes.domain import (
    LedgerEntry,
    LedgerEntryType,
    Position,
)
from volcanoes.ledger import Ledger


@dataclass
class Portfolio:
    """Represent the current trading account."""

    starting_cash: Decimal
    ledger: Ledger = field(default_factory=Ledger)

    cash: Decimal = field(init=False)
    positions: dict[str, Position] = field(default_factory=dict)
    realized_pnl: Decimal = field(
        default_factory=lambda: Decimal("0.00")
    )

    def __post_init__(self) -> None:
        if not isinstance(self.starting_cash, Decimal):
            raise TypeError(
                "Starting cash must be a Decimal."
            )

        if self.starting_cash <= Decimal("0"):
            raise ValueError(
                "Starting cash must be greater than zero."
            )

        if not isinstance(self.ledger, Ledger):
            raise TypeError(
                "ledger must be a Ledger instance."
            )

        self.cash = self.starting_cash

    @property
    def invested_value(self) -> Decimal:
        """Return the market value of all open positions."""

        return sum(
            (
                position.market_value
                for position in self.positions.values()
            ),
            start=Decimal("0.00"),
        )

    @property
    def equity(self) -> Decimal:
        """Return current account equity."""

        return self.cash + self.invested_value

    @property
    def buying_power(self) -> Decimal:
        """Return available buying power."""

        return self.cash

    @property
    def open_positions(self) -> int:
        """Return the number of currently open positions."""

        return len(self.positions)

    def has_position(self, symbol: str) -> bool:
        """Return whether the portfolio holds a symbol."""

        return self._normalize_symbol(symbol) in self.positions

    def get_position(self, symbol: str) -> Position | None:
        """Return an open position for a symbol."""

        return self.positions.get(
            self._normalize_symbol(symbol)
        )

    def buy(
        self,
        symbol: str,
        quantity: int,
        price: Decimal,
    ) -> None:
        """Record a purchase and its ledger movement."""

        normalized_symbol = self._normalize_symbol(symbol)
        self._validate_trade_inputs(quantity, price)

        cost = Decimal(quantity) * price

        if cost > self.cash:
            raise ValueError(
                "Insufficient cash."
            )

        self.cash -= cost

        if normalized_symbol not in self.positions:
            self.positions[normalized_symbol] = Position(
                symbol=normalized_symbol,
                quantity=quantity,
                average_price=price,
            )
        else:
            self.positions[
                normalized_symbol
            ].update_average_price(
                quantity,
                price,
            )

        self.ledger.record(
            LedgerEntry(
                entry_type=LedgerEntryType.BUY,
                amount=-cost,
                description=(
                    f"Bought {quantity} shares of "
                    f"{normalized_symbol} at {price}"
                ),
                symbol=normalized_symbol,
                quantity=quantity,
            )
        )

    def sell(
        self,
        symbol: str,
        quantity: int,
        price: Decimal,
    ) -> None:
        """Record a sale and its ledger movement."""

        normalized_symbol = self._normalize_symbol(symbol)
        self._validate_trade_inputs(quantity, price)

        position = self.positions.get(normalized_symbol)

        if position is None:
            raise ValueError(
                "No position exists."
            )

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
            del self.positions[normalized_symbol]

        self.ledger.record(
            LedgerEntry(
                entry_type=LedgerEntryType.SELL,
                amount=proceeds,
                description=(
                    f"Sold {quantity} shares of "
                    f"{normalized_symbol} at {price}"
                ),
                symbol=normalized_symbol,
                quantity=quantity,
            )
        )

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """Normalize and validate a market symbol."""

        if not isinstance(symbol, str):
            raise TypeError(
                "Symbol must be a string."
            )

        normalized_symbol = symbol.strip().upper()

        if not normalized_symbol:
            raise ValueError(
                "Symbol cannot be empty."
            )

        return normalized_symbol

    @staticmethod
    def _validate_trade_inputs(
        quantity: int,
        price: Decimal,
    ) -> None:
        """Validate quantity and price values."""

        if isinstance(quantity, bool) or not isinstance(
            quantity,
            int,
        ):
            raise TypeError(
                "Quantity must be an integer."
            )

        if quantity <= 0:
            raise ValueError(
                "Quantity must be positive."
            )

        if not isinstance(price, Decimal):
            raise TypeError(
                "Price must be a Decimal."
            )

        if price <= Decimal("0"):
            raise ValueError(
                "Price must be greater than zero."
            )
