"""Deterministic portfolio drawdown metrics."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from volcanoes.analytics.portfolio_snapshot import PortfolioSnapshot


@dataclass(frozen=True, slots=True)
class DrawdownMetrics:
    """Summarize equity drawdown across a snapshot series."""

    peak_equity: Decimal
    current_drawdown: Decimal
    maximum_drawdown: Decimal
    maximum_drawdown_amount: Decimal
    snapshot_count: int

    def __post_init__(self) -> None:
        """Validate drawdown metric invariants."""
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

        if self.snapshot_count < 0:
            raise ValueError("snapshot_count cannot be negative")


class DrawdownCalculator:
    """Calculate drawdown from immutable portfolio snapshots."""

    def calculate(
        self,
        snapshots: tuple[PortfolioSnapshot, ...],
    ) -> DrawdownMetrics:
        """Return drawdown metrics for a snapshot series."""
        if not snapshots:
            return DrawdownMetrics(
                peak_equity=Decimal("0"),
                current_drawdown=Decimal("0"),
                maximum_drawdown=Decimal("0"),
                maximum_drawdown_amount=Decimal("0"),
                snapshot_count=0,
            )

        peak_equity = snapshots[0].equity
        maximum_drawdown = Decimal("0")
        maximum_drawdown_amount = Decimal("0")
        current_drawdown = Decimal("0")

        for snapshot in snapshots:
            equity = snapshot.equity

            if equity > peak_equity:
                peak_equity = equity

            drawdown_amount = peak_equity - equity

            if peak_equity == Decimal("0"):
                drawdown = Decimal("0")
            else:
                drawdown = drawdown_amount / peak_equity

            current_drawdown = drawdown

            if drawdown > maximum_drawdown:
                maximum_drawdown = drawdown
                maximum_drawdown_amount = drawdown_amount

        return DrawdownMetrics(
            peak_equity=peak_equity,
            current_drawdown=current_drawdown,
            maximum_drawdown=maximum_drawdown,
            maximum_drawdown_amount=maximum_drawdown_amount,
            snapshot_count=len(snapshots),
        )
