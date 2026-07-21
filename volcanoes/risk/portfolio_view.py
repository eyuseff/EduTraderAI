"""Read-only portfolio contracts required by deterministic risk rules."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable


@runtime_checkable
class RiskPositionView(Protocol):
    """Minimum position information required during risk validation."""

    symbol: str
    quantity: int


@runtime_checkable
class RiskPortfolioView(Protocol):
    """Read-only account state consumed by sizing and risk validation."""

    @property
    def starting_cash(self) -> Decimal:
        """Return equity captured at the start of the risk period."""
        ...

    @property
    def realized_pnl(self) -> Decimal:
        """Return realized profit and loss for the risk period."""
        ...

    @property
    def equity(self) -> Decimal:
        """Return current account equity."""
        ...

    @property
    def buying_power(self) -> Decimal:
        """Return currently available buying power."""
        ...

    @property
    def invested_value(self) -> Decimal:
        """Return current gross invested value."""
        ...

    @property
    def open_positions(self) -> int:
        """Return the number of open positions."""
        ...

    def has_position(self, symbol: str) -> bool:
        """Return whether an open position exists for a symbol."""
        ...

    def get_position(self, symbol: str) -> RiskPositionView | None:
        """Return a read-only position view for a symbol."""
        ...
