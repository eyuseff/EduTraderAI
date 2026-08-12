"""Tests for the read-only active-broker portfolio adapter."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from adapters.broker_portfolio_view import (
    BrokerPortfolioView,
    BrokerPositionView,
)
from broker.base import (
    AccountSnapshot,
    BrokerOrder,
    BrokerPosition,
)
from volcanoes.application.services import (
    PreviewTradeRequest,
    PreviewTradeService,
)
from volcanoes.domain import TradeSide
from volcanoes.risk import RiskPortfolioView


class SnapshotFailure(RuntimeError):
    """Sentinel exception used to prove adapter failure propagation."""


class RecordingBroker:
    """PaperBroker-compatible fake that records every method call."""

    name = "Recording paper broker"
    is_paper = True

    def __init__(
        self,
        account: AccountSnapshot,
        positions: list[BrokerPosition],
        *,
        failure: str | None = None,
    ) -> None:
        self.account = account
        self.positions = positions
        self.failure = failure
        self.calls: list[str] = []

    def get_account(self) -> AccountSnapshot:
        self.calls.append("get_account")
        if self.failure == "account":
            raise SnapshotFailure("account snapshot failed")
        return self.account

    def get_positions(self) -> list[BrokerPosition]:
        self.calls.append("get_positions")
        if self.failure == "positions":
            raise SnapshotFailure("position snapshot failed")
        return list(self.positions)

    def get_open_orders(self) -> list[BrokerOrder]:
        self.calls.append("get_open_orders")
        return []

    def submit_bracket_order(
        self,
        *,
        symbol: str,
        quantity: int,
        entry_price: float,
        stop_price: float,
        target_price: float,
    ) -> BrokerOrder:
        self.calls.append("submit_bracket_order")
        raise AssertionError("read-only adapter submitted an order")

    def cancel_all_orders(self) -> int:
        self.calls.append("cancel_all_orders")
        raise AssertionError("read-only adapter cancelled orders")

    def close_all_positions(self) -> int:
        self.calls.append("close_all_positions")
        raise AssertionError("read-only adapter closed positions")


def account_snapshot() -> AccountSnapshot:
    return AccountSnapshot(
        equity=101_250.75,
        cash=25_000.25,
        buying_power=50_000.50,
        daily_pnl=-125.25,
        paper=True,
    )


def position_snapshot() -> list[BrokerPosition]:
    return [
        BrokerPosition(
            symbol="aapl",
            quantity=10,
            average_entry_price=100.25,
            current_price=110.50,
        ),
        BrokerPosition(
            symbol="TSLA",
            quantity=-2,
            average_entry_price=275.00,
            current_price=250.00,
        ),
    ]


def test_account_snapshot_maps_exactly() -> None:
    account = account_snapshot()
    view = BrokerPortfolioView.from_snapshot(account, [])

    assert view.equity == Decimal(str(account.equity))
    assert view.cash == Decimal(str(account.cash))
    assert view.buying_power == Decimal(str(account.buying_power))
    assert view.daily_pnl == Decimal(str(account.daily_pnl))
    assert view.realized_pnl == Decimal(str(account.daily_pnl))
    assert view.paper is account.paper
    assert view.starting_cash == view.equity - view.daily_pnl


def test_positions_map_exactly() -> None:
    source_positions = position_snapshot()
    view = BrokerPortfolioView.from_snapshot(
        account_snapshot(),
        source_positions,
    )

    assert len(view.positions) == len(source_positions)

    for source, mapped in zip(
        source_positions,
        view.positions,
        strict=True,
    ):
        assert mapped.symbol == source.symbol.strip().upper()
        assert mapped.quantity == source.quantity
        assert mapped.average_entry_price == Decimal(str(source.average_entry_price))
        assert mapped.current_price == Decimal(str(source.current_price))
        assert mapped.market_value == Decimal(str(source.market_value))
        assert mapped.unrealized_pnl == Decimal(str(source.unrealized_pnl))


def test_exposure_is_gross_absolute_market_value() -> None:
    view = BrokerPortfolioView.from_snapshot(
        account_snapshot(),
        position_snapshot(),
    )

    expected = sum(
        (abs(Decimal(str(position.market_value))) for position in position_snapshot()),
        start=Decimal("0"),
    )

    assert view.invested_value == expected
    assert view.invested_value == Decimal("1605.0")


def test_symbol_lookup_is_normalized_and_snapshot_only() -> None:
    broker = RecordingBroker(account_snapshot(), position_snapshot())
    view = BrokerPortfolioView.from_broker(broker)

    position = view.get_position("  AaPl ")

    assert isinstance(position, BrokerPositionView)
    assert position.symbol == "AAPL"
    assert view.has_position("aapl") is True
    assert view.has_position("MSFT") is False
    assert view.open_positions == 2
    assert broker.calls == ["get_account", "get_positions"]


def test_view_and_positions_are_immutable_copies() -> None:
    source_positions = position_snapshot()
    view = BrokerPortfolioView.from_snapshot(
        account_snapshot(),
        source_positions,
    )

    source_positions.clear()

    assert len(view.positions) == 2
    assert isinstance(view.positions, tuple)

    with pytest.raises(FrozenInstanceError):
        view.equity = Decimal("0")  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        view.positions[0].quantity = 0  # type: ignore[misc]


def test_adapter_satisfies_risk_portfolio_view() -> None:
    view = BrokerPortfolioView.from_snapshot(account_snapshot(), [])

    assert isinstance(view, RiskPortfolioView)


def test_adapter_never_invokes_broker_mutation_or_order_methods() -> None:
    broker = RecordingBroker(account_snapshot(), position_snapshot())

    view = BrokerPortfolioView.from_broker(broker)
    view.get_position("AAPL")
    view.has_position("TSLA")
    _ = view.invested_value

    assert broker.calls == ["get_account", "get_positions"]
    assert "get_open_orders" not in broker.calls
    assert "submit_bracket_order" not in broker.calls
    assert "cancel_all_orders" not in broker.calls
    assert "close_all_positions" not in broker.calls


@pytest.mark.parametrize(
    ("failure", "message", "expected_calls"),
    [
        ("account", "account snapshot failed", ["get_account"]),
        (
            "positions",
            "position snapshot failed",
            ["get_account", "get_positions"],
        ),
    ],
)
def test_snapshot_failures_propagate_unchanged(
    failure: str,
    message: str,
    expected_calls: list[str],
) -> None:
    broker = RecordingBroker(
        account_snapshot(),
        position_snapshot(),
        failure=failure,
    )

    with pytest.raises(SnapshotFailure, match=message):
        BrokerPortfolioView.from_broker(broker)

    assert broker.calls == expected_calls


def test_from_broker_has_full_snapshot_parity() -> None:
    account = account_snapshot()
    positions = position_snapshot()
    broker = RecordingBroker(account, positions)

    view = BrokerPortfolioView.from_broker(broker)

    assert view == BrokerPortfolioView.from_snapshot(account, positions)
    assert view.equity == Decimal(str(account.equity))
    assert view.buying_power == Decimal(str(account.buying_power))
    assert view.cash == Decimal(str(account.cash))
    assert view.daily_pnl == Decimal(str(account.daily_pnl))
    assert tuple(position.quantity for position in view.positions) == tuple(
        position.quantity for position in positions
    )


def test_preview_service_accepts_view_without_additional_broker_calls() -> None:
    account = AccountSnapshot(
        equity=100_000.0,
        cash=100_000.0,
        buying_power=100_000.0,
        daily_pnl=0.0,
        paper=True,
    )
    broker = RecordingBroker(account, [])
    view = BrokerPortfolioView.from_broker(broker)

    result = PreviewTradeService().preview(
        view,
        PreviewTradeRequest(
            symbol="AAPL",
            side=TradeSide.BUY,
            entry_price=Decimal("100"),
            stop_price=Decimal("95"),
            target_price=Decimal("110"),
        ),
    )

    assert result.approved is True
    assert broker.calls == ["get_account", "get_positions"]
