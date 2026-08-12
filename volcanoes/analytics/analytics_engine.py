"""Analytics engine."""

from decimal import Decimal

from volcanoes.analytics.metrics.drawdown import DrawdownCalculator
from volcanoes.analytics.performance_report import PerformanceReport
from volcanoes.analytics.portfolio_snapshot import PortfolioSnapshot


class AnalyticsEngine:
    """Generate analytics from immutable portfolio snapshots."""

    def __init__(
        self,
        drawdown_calculator: DrawdownCalculator | None = None,
    ) -> None:
        """Initialize deterministic analytics dependencies."""
        self._drawdown_calculator = (
            drawdown_calculator or DrawdownCalculator()
        )

    def analyze(
        self,
        snapshots: tuple[PortfolioSnapshot, ...],
    ) -> PerformanceReport:
        """Generate a performance report."""
        drawdown = self._drawdown_calculator.calculate(snapshots)

        if not snapshots:
            return PerformanceReport(
                starting_equity=Decimal("0"),
                ending_equity=Decimal("0"),
                total_return=Decimal("0"),
                realized_pnl=Decimal("0"),
                unrealized_pnl=Decimal("0"),
                snapshot_count=0,
                peak_equity=drawdown.peak_equity,
                current_drawdown=drawdown.current_drawdown,
                maximum_drawdown=drawdown.maximum_drawdown,
                maximum_drawdown_amount=(
                    drawdown.maximum_drawdown_amount
                ),
            )

        first = snapshots[0]
        last = snapshots[-1]

        starting_equity = first.equity
        ending_equity = last.equity

        if starting_equity == Decimal("0"):
            total_return = Decimal("0")
        else:
            total_return = (
                ending_equity - starting_equity
            ) / starting_equity

        return PerformanceReport(
            starting_equity=starting_equity,
            ending_equity=ending_equity,
            total_return=total_return,
            realized_pnl=last.realized_pnl,
            unrealized_pnl=last.unrealized_pnl,
            snapshot_count=len(snapshots),
            peak_equity=drawdown.peak_equity,
            current_drawdown=drawdown.current_drawdown,
            maximum_drawdown=drawdown.maximum_drawdown,
            maximum_drawdown_amount=(
                drawdown.maximum_drawdown_amount
            ),
        )
