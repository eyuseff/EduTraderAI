"""Immutable portfolio state captured at a specific point in time."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    """A read-only snapshot of portfolio accounting state.

    The snapshot contains only observed portfolio facts. Derived analytics
    such as drawdown, Sharpe ratio, and win rate belong elsewhere.
    """

    timestamp: datetime
    cash: Decimal
    market_value: Decimal
    equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    open_positions: int

    def __post_init__(self) -> None:
        """Validate snapshot invariants."""
        if self.open_positions < 0:
            raise ValueError("open_positions cannot be negative")

        expected_equity = self.cash + self.market_value
        if self.equity != expected_equity:
            raise ValueError(
                "equity must equal cash plus market_value "
                f"({self.equity} != {expected_equity})"
            )
