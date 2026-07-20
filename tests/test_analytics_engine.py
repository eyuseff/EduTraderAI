from datetime import datetime, timezone
from decimal import Decimal

from volcanoes.analytics.analytics_engine import AnalyticsEngine
from volcanoes.analytics.portfolio_snapshot import PortfolioSnapshot


def snapshot(equity: str) -> PortfolioSnapshot:
    value = Decimal(equity)

    return PortfolioSnapshot(
        timestamp=datetime.now(timezone.utc),
        cash=value,
        market_value=Decimal("0"),
        equity=value,
        realized_pnl=Decimal("25"),
        unrealized_pnl=Decimal("10"),
        open_positions=1,
    )


def test_empty_snapshot_list():
    engine = AnalyticsEngine()

    report = engine.analyze(())

    assert report.snapshot_count == 0
    assert report.total_return == Decimal("0")


def test_single_snapshot():
    engine = AnalyticsEngine()

    report = engine.analyze(
        (
            snapshot("1000"),
        )
    )

    assert report.starting_equity == Decimal("1000")
    assert report.ending_equity == Decimal("1000")
    assert report.total_return == Decimal("0")


def test_multiple_snapshots():
    engine = AnalyticsEngine()

    report = engine.analyze(
        (
            snapshot("1000"),
            snapshot("1050"),
            snapshot("1100"),
        )
    )

    assert report.starting_equity == Decimal("1000")
    assert report.ending_equity == Decimal("1100")
    assert report.snapshot_count == 3
    assert report.total_return == Decimal("0.1")
