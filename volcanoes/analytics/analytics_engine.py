"""Analytics engine."""

from decimal import Decimal

from volcanoes.analytics.performance_report import PerformanceReport
from volcanoes.analytics.portfolio_snapshot import PortfolioSnapshot


class AnalyticsEngine:
    """Generates analytics from immutable portfolio snapshots."""

    def analyze(
        self,
        snapshots: tuple[PortfolioSnapshot, ...],
    ) -> PerformanceReport:
        """Generate a performance report."""

        if not snapshots:
            return PerformanceReport(
                starting_equity=Decimal("0"),
                ending_equity=Decimal("0"),
                total_return=Decimal("0"),
                realized_pnl=Decimal("0"),
                unrealized_pnl=Decimal("0"),
                snapshot_count=0,
            )

        first = snapshots[0]
        last = snapshots[-1]

        starting = first.equity
        ending = last.equity

        if starting == Decimal("0"):
            total_return = Decimal("0")
        else:
            total_return = (ending - starting) / starting

        return PerformanceReport(
            starting_equity=starting,
            ending_equity=ending,
            total_return=total_return,
            realized_pnl=last.realized_pnl,
            unrealized_pnl=last.unrealized_pnl,
            snapshot_count=len(snapshots),
        )
