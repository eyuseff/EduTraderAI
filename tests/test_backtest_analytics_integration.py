"""Integration tests for backtesting and analytics."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from volcanoes.analytics import PerformanceReport, PortfolioSnapshot
from volcanoes.backtest import BacktestEngine
from volcanoes.execution import ExecutionPipeline
from volcanoes.market import Bar, HistoricalFeed
from volcanoes.portfolio import Portfolio
from volcanoes.risk import RiskManager
from volcanoes.sizing import PositionSizer
from volcanoes.strategy import NoOpStrategy

# Use the same broker implementation already used by the project.
from volcanoes.execution.paper_broker import PaperBroker


def make_bar(index: int) -> Bar:
    """Create deterministic market data for integration testing."""
    price = Decimal("100") + Decimal(index)

    return Bar(
        symbol="AAPL",
        timestamp=(
            datetime(2026, 1, 1, tzinfo=timezone.utc)
            + timedelta(days=index)
        ),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=1000,
    )


def make_engine(bars: tuple[Bar, ...]) -> BacktestEngine:
    """Create a backtest engine using the no-op strategy."""
    portfolio = Portfolio(starting_cash=Decimal("10000"))

    pipeline = ExecutionPipeline(
        position_sizer=PositionSizer(),
        risk_manager=RiskManager(),
        broker=PaperBroker(portfolio),
    )

    return BacktestEngine(
        feed=HistoricalFeed(bars),
        strategy=NoOpStrategy(),
        pipeline=pipeline,
        portfolio=portfolio,
    )


def test_backtest_records_one_snapshot_per_bar() -> None:
    engine = make_engine(
        (
            make_bar(0),
            make_bar(1),
            make_bar(2),
        )
    )

    result = engine.run()

    assert result.total_bars == 3
    assert len(result.snapshots) == 3
    assert all(
        isinstance(snapshot, PortfolioSnapshot)
        for snapshot in result.snapshots
    )


def test_snapshot_timestamp_matches_processed_bar() -> None:
    bars = (
        make_bar(0),
        make_bar(1),
    )

    result = make_engine(bars).run()

    assert result.snapshots[0].timestamp == bars[0].timestamp
    assert result.snapshots[1].timestamp == bars[1].timestamp


def test_noop_backtest_preserves_equity() -> None:
    result = make_engine(
        (
            make_bar(0),
            make_bar(1),
        )
    ).run()

    assert result.snapshots[0].equity == Decimal("10000")
    assert result.snapshots[-1].equity == Decimal("10000")
    assert result.performance_report.total_return == Decimal("0")


def test_backtest_result_contains_performance_report() -> None:
    result = make_engine((make_bar(0),)).run()

    assert isinstance(result.performance_report, PerformanceReport)
    assert result.performance_report.starting_equity == Decimal("10000")
    assert result.performance_report.ending_equity == Decimal("10000")
    assert result.performance_report.snapshot_count == 1


def test_empty_feed_returns_empty_analytics() -> None:
    result = make_engine(()).run()

    assert result.total_bars == 0
    assert result.snapshots == ()
    assert result.performance_report.snapshot_count == 0
    assert result.performance_report.total_return == Decimal("0")
