"""Tests for PerformanceReport."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from volcanoes.analytics.performance_report import PerformanceReport


def make_report() -> PerformanceReport:
    """Create a valid report for testing."""
    return PerformanceReport(
        starting_equity=Decimal("1000.00"),
        ending_equity=Decimal("1100.00"),
        total_return=Decimal("0.10"),
        realized_pnl=Decimal("80.00"),
        unrealized_pnl=Decimal("20.00"),
        snapshot_count=10,
        peak_equity=Decimal("1250.00"),
        current_drawdown=Decimal("0.12"),
        maximum_drawdown=Decimal("0.20"),
        maximum_drawdown_amount=Decimal("250.00"),
    )


def test_performance_report_stores_values() -> None:
    report = make_report()

    assert report.starting_equity == Decimal("1000.00")
    assert report.ending_equity == Decimal("1100.00")
    assert report.total_return == Decimal("0.10")
    assert report.realized_pnl == Decimal("80.00")
    assert report.unrealized_pnl == Decimal("20.00")
    assert report.snapshot_count == 10
    assert report.peak_equity == Decimal("1250.00")
    assert report.current_drawdown == Decimal("0.12")
    assert report.maximum_drawdown == Decimal("0.20")
    assert report.maximum_drawdown_amount == Decimal("250.00")


def test_performance_report_is_immutable() -> None:
    report = make_report()

    with pytest.raises(FrozenInstanceError):
        report.ending_equity = Decimal("1300.00")  # type: ignore[misc]


def test_new_drawdown_fields_default_to_zero() -> None:
    report = PerformanceReport(
        starting_equity=Decimal("1000.00"),
        ending_equity=Decimal("1000.00"),
        total_return=Decimal("0"),
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        snapshot_count=1,
    )

    assert report.peak_equity == Decimal("0")
    assert report.current_drawdown == Decimal("0")
    assert report.maximum_drawdown == Decimal("0")
    assert report.maximum_drawdown_amount == Decimal("0")


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


def test_performance_report_rejects_negative_peak_equity() -> None:
    with pytest.raises(ValueError, match="peak_equity cannot be negative"):
        PerformanceReport(
            starting_equity=Decimal("1000"),
            ending_equity=Decimal("1000"),
            total_return=Decimal("0"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            snapshot_count=1,
            peak_equity=Decimal("-1"),
        )


def test_performance_report_rejects_negative_current_drawdown() -> None:
    with pytest.raises(
        ValueError,
        match="current_drawdown cannot be negative",
    ):
        PerformanceReport(
            starting_equity=Decimal("1000"),
            ending_equity=Decimal("1000"),
            total_return=Decimal("0"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            snapshot_count=1,
            peak_equity=Decimal("1000"),
            current_drawdown=Decimal("-0.01"),
            maximum_drawdown=Decimal("0"),
        )


def test_performance_report_rejects_negative_maximum_drawdown() -> None:
    with pytest.raises(
        ValueError,
        match="maximum_drawdown cannot be negative",
    ):
        PerformanceReport(
            starting_equity=Decimal("1000"),
            ending_equity=Decimal("1000"),
            total_return=Decimal("0"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            snapshot_count=1,
            peak_equity=Decimal("1000"),
            maximum_drawdown=Decimal("-0.01"),
        )


def test_performance_report_rejects_negative_drawdown_amount() -> None:
    with pytest.raises(
        ValueError,
        match="maximum_drawdown_amount cannot be negative",
    ):
        PerformanceReport(
            starting_equity=Decimal("1000"),
            ending_equity=Decimal("1000"),
            total_return=Decimal("0"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            snapshot_count=1,
            peak_equity=Decimal("1000"),
            maximum_drawdown_amount=Decimal("-1"),
        )


def test_performance_report_rejects_current_drawdown_above_one() -> None:
    with pytest.raises(
        ValueError,
        match="current_drawdown cannot exceed one",
    ):
        PerformanceReport(
            starting_equity=Decimal("1000"),
            ending_equity=Decimal("0"),
            total_return=Decimal("-1"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            snapshot_count=1,
            peak_equity=Decimal("1000"),
            current_drawdown=Decimal("1.01"),
            maximum_drawdown=Decimal("1.01"),
        )


def test_performance_report_rejects_maximum_drawdown_above_one() -> None:
    with pytest.raises(
        ValueError,
        match="maximum_drawdown cannot exceed one",
    ):
        PerformanceReport(
            starting_equity=Decimal("1000"),
            ending_equity=Decimal("0"),
            total_return=Decimal("-1"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("0"),
            snapshot_count=1,
            peak_equity=Decimal("1000"),
            current_drawdown=Decimal("0"),
            maximum_drawdown=Decimal("1.01"),
        )


def test_performance_report_rejects_current_above_maximum() -> None:
    with pytest.raises(
        ValueError,
        match="current_drawdown cannot exceed maximum_drawdown",
    ):
        PerformanceReport(
            starting_equity=Decimal("1000"),
            ending_equity=Decimal("800"),
            total_return=Decimal("-0.20"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("-200"),
            snapshot_count=2,
            peak_equity=Decimal("1000"),
            current_drawdown=Decimal("0.20"),
            maximum_drawdown=Decimal("0.10"),
            maximum_drawdown_amount=Decimal("100"),
        )
