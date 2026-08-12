"""Tests for deterministic drawdown analytics."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from volcanoes.analytics.metrics.drawdown import (
    DrawdownCalculator,
    DrawdownMetrics,
)
from volcanoes.analytics.portfolio_snapshot import PortfolioSnapshot


def make_snapshot(
    equity: str,
    index: int = 0,
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
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        open_positions=0,
    )


def test_empty_snapshots_return_zero_metrics() -> None:
    calculator = DrawdownCalculator()

    metrics = calculator.calculate(())

    assert metrics == DrawdownMetrics(
        peak_equity=Decimal("0"),
        current_drawdown=Decimal("0"),
        maximum_drawdown=Decimal("0"),
        maximum_drawdown_amount=Decimal("0"),
        snapshot_count=0,
    )


def test_constant_equity_has_no_drawdown() -> None:
    calculator = DrawdownCalculator()

    metrics = calculator.calculate(
        (
            make_snapshot("1000", 0),
            make_snapshot("1000", 1),
            make_snapshot("1000", 2),
        )
    )

    assert metrics.peak_equity == Decimal("1000")
    assert metrics.current_drawdown == Decimal("0")
    assert metrics.maximum_drawdown == Decimal("0")
    assert metrics.maximum_drawdown_amount == Decimal("0")
    assert metrics.snapshot_count == 3


def test_rising_equity_has_no_drawdown() -> None:
    calculator = DrawdownCalculator()

    metrics = calculator.calculate(
        (
            make_snapshot("1000", 0),
            make_snapshot("1100", 1),
            make_snapshot("1200", 2),
        )
    )

    assert metrics.peak_equity == Decimal("1200")
    assert metrics.current_drawdown == Decimal("0")
    assert metrics.maximum_drawdown == Decimal("0")
    assert metrics.maximum_drawdown_amount == Decimal("0")


def test_calculates_maximum_drawdown() -> None:
    calculator = DrawdownCalculator()

    metrics = calculator.calculate(
        (
            make_snapshot("1000", 0),
            make_snapshot("1200", 1),
            make_snapshot("900", 2),
            make_snapshot("1100", 3),
        )
    )

    assert metrics.peak_equity == Decimal("1200")
    assert metrics.maximum_drawdown == Decimal("0.25")
    assert metrics.maximum_drawdown_amount == Decimal("300")
    assert metrics.current_drawdown == (
        Decimal("100") / Decimal("1200")
    )


def test_new_peak_resets_current_drawdown() -> None:
    calculator = DrawdownCalculator()

    metrics = calculator.calculate(
        (
            make_snapshot("1000", 0),
            make_snapshot("800", 1),
            make_snapshot("1100", 2),
        )
    )

    assert metrics.peak_equity == Decimal("1100")
    assert metrics.current_drawdown == Decimal("0")
    assert metrics.maximum_drawdown == Decimal("0.20")
    assert metrics.maximum_drawdown_amount == Decimal("200")


def test_maximum_drawdown_is_preserved_after_recovery() -> None:
    calculator = DrawdownCalculator()

    metrics = calculator.calculate(
        (
            make_snapshot("1000", 0),
            make_snapshot("700", 1),
            make_snapshot("1000", 2),
            make_snapshot("900", 3),
        )
    )

    assert metrics.current_drawdown == Decimal("0.10")
    assert metrics.maximum_drawdown == Decimal("0.30")
    assert metrics.maximum_drawdown_amount == Decimal("300")


def test_drawdown_metrics_are_immutable() -> None:
    metrics = DrawdownMetrics(
        peak_equity=Decimal("1000"),
        current_drawdown=Decimal("0.10"),
        maximum_drawdown=Decimal("0.20"),
        maximum_drawdown_amount=Decimal("200"),
        snapshot_count=3,
    )

    with pytest.raises(AttributeError):
        metrics.maximum_drawdown = Decimal("0.50")  # type: ignore[misc]


def test_rejects_current_drawdown_above_maximum() -> None:
    with pytest.raises(
        ValueError,
        match="current_drawdown cannot exceed maximum_drawdown",
    ):
        DrawdownMetrics(
            peak_equity=Decimal("1000"),
            current_drawdown=Decimal("0.30"),
            maximum_drawdown=Decimal("0.20"),
            maximum_drawdown_amount=Decimal("200"),
            snapshot_count=3,
        )
