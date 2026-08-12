"""Tests for AnalyticsEngine."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from volcanoes.analytics.analytics_engine import AnalyticsEngine
from volcanoes.analytics.portfolio_snapshot import PortfolioSnapshot


def snapshot(
    equity: str,
    index: int = 0,
    *,
    realized_pnl: str = "25",
    unrealized_pnl: str = "10",
) -> PortfolioSnapshot:
    """Create a deterministic portfolio snapshot."""
    value = Decimal(equity)

    return PortfolioSnapshot(
        timestamp=(
            datetime(2026, 1, 1, tzinfo=timezone.utc)
            + timedelta(days=index)
        ),
        cash=value,
        market_value=Decimal("0"),
        equity=value,
        realized_pnl=Decimal(realized_pnl),
        unrealized_pnl=Decimal(unrealized_pnl),
        open_positions=1,
    )


def test_empty_snapshot_list() -> None:
    engine = AnalyticsEngine()

    report = engine.analyze(())

    assert report.snapshot_count == 0
    assert report.starting_equity == Decimal("0")
    assert report.ending_equity == Decimal("0")
    assert report.total_return == Decimal("0")
    assert report.peak_equity == Decimal("0")
    assert report.current_drawdown == Decimal("0")
    assert report.maximum_drawdown == Decimal("0")
    assert report.maximum_drawdown_amount == Decimal("0")


def test_single_snapshot() -> None:
    engine = AnalyticsEngine()

    report = engine.analyze((snapshot("1000"),))

    assert report.starting_equity == Decimal("1000")
    assert report.ending_equity == Decimal("1000")
    assert report.total_return == Decimal("0")
    assert report.peak_equity == Decimal("1000")
    assert report.current_drawdown == Decimal("0")
    assert report.maximum_drawdown == Decimal("0")


def test_multiple_snapshots() -> None:
    engine = AnalyticsEngine()

    report = engine.analyze(
        (
            snapshot("1000", 0),
            snapshot("1050", 1),
            snapshot(
                "1100",
                2,
                realized_pnl="75",
                unrealized_pnl="25",
            ),
        )
    )

    assert report.starting_equity == Decimal("1000")
    assert report.ending_equity == Decimal("1100")
    assert report.snapshot_count == 3
    assert report.total_return == Decimal("0.1")
    assert report.realized_pnl == Decimal("75")
    assert report.unrealized_pnl == Decimal("25")
    assert report.peak_equity == Decimal("1100")
    assert report.current_drawdown == Decimal("0")
    assert report.maximum_drawdown == Decimal("0")


def test_analytics_engine_integrates_drawdown_metrics() -> None:
    engine = AnalyticsEngine()

    report = engine.analyze(
        (
            snapshot("1000", 0),
            snapshot("1200", 1),
            snapshot("900", 2),
            snapshot("1100", 3),
        )
    )

    assert report.peak_equity == Decimal("1200")
    assert report.maximum_drawdown == Decimal("0.25")
    assert report.maximum_drawdown_amount == Decimal("300")
    assert report.current_drawdown == (
        Decimal("100") / Decimal("1200")
    )


def test_recovery_to_new_peak_resets_current_drawdown() -> None:
    engine = AnalyticsEngine()

    report = engine.analyze(
        (
            snapshot("1000", 0),
            snapshot("800", 1),
            snapshot("1100", 2),
        )
    )

    assert report.peak_equity == Decimal("1100")
    assert report.current_drawdown == Decimal("0")
    assert report.maximum_drawdown == Decimal("0.20")
    assert report.maximum_drawdown_amount == Decimal("200")


def test_zero_starting_equity_returns_zero_total_return() -> None:
    engine = AnalyticsEngine()

    report = engine.analyze(
        (
            snapshot("0", 0),
            snapshot("100", 1),
        )
    )

    assert report.starting_equity == Decimal("0")
    assert report.ending_equity == Decimal("100")
    assert report.total_return == Decimal("0")
    assert report.peak_equity == Decimal("100")
