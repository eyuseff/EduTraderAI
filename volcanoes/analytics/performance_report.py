"""Immutable analytics summary for a completed evaluation period."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PerformanceReport:
    """Summarize portfolio performance over a snapshot series."""

    starting_equity: Decimal
    ending_equity: Decimal
    total_return: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    snapshot_count: int

    peak_equity: Decimal = Decimal("0")
    current_drawdown: Decimal = Decimal("0")
    maximum_drawdown: Decimal = Decimal("0")
    maximum_drawdown_amount: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        """Validate report invariants."""
        if self.snapshot_count < 0:
            raise ValueError("snapshot_count cannot be negative")

        if self.starting_equity < Decimal("0"):
            raise ValueError("starting_equity cannot be negative")

        if self.ending_equity < Decimal("0"):
            raise ValueError("ending_equity cannot be negative")

        if self.peak_equity < Decimal("0"):
            raise ValueError("peak_equity cannot be negative")

        if self.current_drawdown < Decimal("0"):
            raise ValueError("current_drawdown cannot be negative")

        if self.maximum_drawdown < Decimal("0"):
            raise ValueError("maximum_drawdown cannot be negative")

        if self.maximum_drawdown_amount < Decimal("0"):
            raise ValueError(
                "maximum_drawdown_amount cannot be negative"
            )

        if self.current_drawdown > Decimal("1"):
            raise ValueError("current_drawdown cannot exceed one")

        if self.maximum_drawdown > Decimal("1"):
            raise ValueError("maximum_drawdown cannot exceed one")

        if self.current_drawdown > self.maximum_drawdown:
            raise ValueError(
                "current_drawdown cannot exceed maximum_drawdown"
            )
