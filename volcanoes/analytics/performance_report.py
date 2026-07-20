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

    def __post_init__(self) -> None:
        """Validate report invariants."""
        if self.snapshot_count < 0:
            raise ValueError("snapshot_count cannot be negative")

        if self.starting_equity < Decimal("0"):
            raise ValueError("starting_equity cannot be negative")

        if self.ending_equity < Decimal("0"):
            raise ValueError("ending_equity cannot be negative")
