"""Tests for PortfolioSnapshot."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from volcanoes.analytics.portfolio_snapshot import PortfolioSnapshot


def make_snapshot() -> PortfolioSnapshot:
    """Create a valid snapshot for testing."""
    return PortfolioSnapshot(
        timestamp=datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc),
        cash=Decimal("1000.00"),
        market_value=Decimal("250.00"),
        equity=Decimal("1250.00"),
        realized_pnl=Decimal("50.00"),
        unrealized_pnl=Decimal("25.00"),
        open_positions=2,
    )


def test_portfolio_snapshot_stores_values() -> None:
    snapshot = make_snapshot()

    assert snapshot.cash == Decimal("1000.00")
    assert snapshot.market_value == Decimal("250.00")
    assert snapshot.equity == Decimal("1250.00")
    assert snapshot.realized_pnl == Decimal("50.00")
    assert snapshot.unrealized_pnl == Decimal("25.00")
    assert snapshot.open_positions == 2


def test_portfolio_snapshot_is_immutable() -> None:
    snapshot = make_snapshot()

    with pytest.raises(FrozenInstanceError):
        snapshot.cash = Decimal("500.00")  # type: ignore[misc]


def test_portfolio_snapshot_rejects_negative_open_positions() -> None:
    with pytest.raises(ValueError, match="open_positions cannot be negative"):
        PortfolioSnapshot(
            timestamp=datetime(2026, 7, 20, tzinfo=timezone.utc),
            cash=Decimal("1000.00"),
            market_value=Decimal("0.00"),
            equity=Decimal("1000.00"),
            realized_pnl=Decimal("0.00"),
            unrealized_pnl=Decimal("0.00"),
            open_positions=-1,
        )


def test_portfolio_snapshot_rejects_inconsistent_equity() -> None:
    with pytest.raises(
        ValueError,
        match="equity must equal cash plus market_value",
    ):
        PortfolioSnapshot(
            timestamp=datetime(2026, 7, 20, tzinfo=timezone.utc),
            cash=Decimal("1000.00"),
            market_value=Decimal("250.00"),
            equity=Decimal("1300.00"),
            realized_pnl=Decimal("0.00"),
            unrealized_pnl=Decimal("0.00"),
            open_positions=1,
        )
