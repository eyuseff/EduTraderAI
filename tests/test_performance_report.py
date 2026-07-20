"""Tests for PerformanceReport."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from volcanoes.analytics.performance_report import PerformanceReport


def make_report() -> PerformanceReport:
    """Create a valid report for testing."""
    return PerformanceReport(
        starting_equity=Decimal("1000.00"),
        ending_equity=Decimal("1250.00"),
        total_return=Decimal("0.25"),
        realized_pnl=Decimal("200.00"),
        unrealized_pnl=Decimal("50.00"),
        snapshot_count=10,
    )


def test_performance_report_stores_values() -> None:
    report = make_report()

    assert report.starting_equity == Decimal("1000.00")
    assert report.ending_equity == Decimal("1250.00")
    assert report.total_return == Decimal("0.25")
    assert report.realized_pnl == Decimal("200.00")
    assert report.unrealized_pnl == Decimal("50.00")
    assert report.snapshot_count == 10


def test_performance_report_is_immutable() -> None:
    report = make_report()

    with pytest.raises(FrozenInstanceError):
        report.ending_equity = Decimal("1300.00")  # type: ignore[misc]


def test_performance_report_rejects_negative_snapshot_count() -> None:
    with pytest.raises(ValueError, match="snapshot_count cannot be negative"):
        PerformanceReport(
            starting_equity=Decimal("1000.00"),
            ending_equity=Decimal("1000.00"),
            total_return=Decimal("0.00"),
            realized_pnl=Decimal("0.00"),
            unrealized_pnl=Decimal("0.00"),
            snapshot_count=-1,
        )


def test_performance_report_rejects_negative_starting_equity() -> None:
    with pytest.raises(ValueError, match="starting_equity cannot be negative"):
        PerformanceReport(
            starting_equity=Decimal("-1.00"),
            ending_equity=Decimal("1000.00"),
            total_return=Decimal("0.00"),
            realized_pnl=Decimal("0.00"),
            unrealized_pnl=Decimal("0.00"),
            snapshot_count=1,
        )


def test_performance_report_rejects_negative_ending_equity() -> None:
    with pytest.raises(ValueError, match="ending_equity cannot be negative"):
        PerformanceReport(
            starting_equity=Decimal("1000.00"),
            ending_equity=Decimal("-1.00"),
            total_return=Decimal("0.00"),
            realized_pnl=Decimal("0.00"),
            unrealized_pnl=Decimal("0.00"),
            snapshot_count=1,
        )
