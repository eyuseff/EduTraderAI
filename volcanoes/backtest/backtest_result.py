"""Immutable result of a completed backtest."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from volcanoes.analytics.performance_report import PerformanceReport
from volcanoes.analytics.portfolio_snapshot import PortfolioSnapshot
from volcanoes.portfolio import Portfolio


def _empty_performance_report() -> PerformanceReport:
    """Create the default analytics report for backward compatibility."""
    return PerformanceReport(
        starting_equity=Decimal("0"),
        ending_equity=Decimal("0"),
        total_return=Decimal("0"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        snapshot_count=0,
    )


@dataclass(frozen=True, slots=True)
class BacktestResult:
    """Summary and research artifacts produced by a completed backtest."""

    total_bars: int
    signals: int
    executed_trades: int
    rejected_trades: int
    portfolio: Portfolio
    snapshots: tuple[PortfolioSnapshot, ...] = ()
    performance_report: PerformanceReport = field(
        default_factory=_empty_performance_report
    )

    def __post_init__(self) -> None:
        """Validate result counters."""
        counters = (
            self.total_bars,
            self.signals,
            self.executed_trades,
            self.rejected_trades,
        )

        if any(value < 0 for value in counters):
            raise ValueError("backtest counters cannot be negative")

        if self.executed_trades + self.rejected_trades > self.signals:
            raise ValueError(
                "executed and rejected trades cannot exceed signals"
            )
