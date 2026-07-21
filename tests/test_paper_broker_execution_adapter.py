"""Tests for root-paper-broker execution translation."""

from __future__ import annotations

from decimal import Decimal

import pytest

from adapters.paper_broker_execution import PaperBrokerExecutionAdapter
from broker.base import AccountSnapshot, BrokerOrder, BrokerPosition
from volcanoes.domain import Order, OrderStatus, TradeSide


class RecordingPaperBroker:
    name = "Recording paper broker"
    is_paper = True

    def __init__(self, *, status: str = "accepted") -> None:
        self.status = status
        self.submissions: list[dict[str, str | int | float]] = []
        self.error: Exception | None = None

    def get_account(self) -> AccountSnapshot:
        return AccountSnapshot(equity=100_000.0, cash=80_000.0, buying_power=75_000.0)

    def get_positions(self) -> list[BrokerPosition]:
        return [BrokerPosition("AAPL", 7, 90.0, 100.0)]

    def get_open_orders(self) -> list[BrokerOrder]:
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
        values: dict[str, str | int | float] = {
            "symbol": symbol,
            "quantity": quantity,
            "entry_price": entry_price,
            "stop_price": stop_price,
            "target_price": target_price,
        }
        self.submissions.append(values)
        if self.error is not None:
            raise self.error
        return BrokerOrder(
            order_id="root-456",
            symbol=symbol,
            quantity=quantity,
            side="buy",
            status=self.status,
            order_type="bracket-limit",
            submitted_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            message="Root broker response.",
        )

    def cancel_all_orders(self) -> int:
        raise AssertionError("execution adapter cancelled orders")

    def close_all_positions(self) -> int:
        raise AssertionError("execution adapter closed positions")


def bracket_order(*, side: TradeSide = TradeSide.BUY) -> Order:
    return Order(
        symbol="aapl",
        side=side,
        quantity=42,
        price=Decimal("100.25"),
        stop_price=Decimal("97.50"),
        target_price=Decimal("106.75"),
    )


def test_new_bracket_metadata_preserves_legacy_positional_order_signature() -> None:
    order = Order(
        "AAPL",
        TradeSide.BUY,
        1,
        Decimal("100"),
        OrderStatus.FILLED,
    )

    assert order.status is OrderStatus.FILLED
    assert order.stop_price is None
    assert order.target_price is None


def test_adapter_maps_exact_bracket_fields_and_success_metadata() -> None:
    broker = RecordingPaperBroker()
    adapter = PaperBrokerExecutionAdapter(broker)

    result = adapter.submit_order(bracket_order())

    assert broker.submissions == [
        {
            "symbol": "AAPL",
            "quantity": 42,
            "entry_price": 100.25,
            "stop_price": 97.5,
            "target_price": 106.75,
        }
    ]
    assert result.side is TradeSide.BUY
    assert result.status is OrderStatus.PENDING
    assert result.broker_order_id == "root-456"
    assert result.broker_status == "accepted"
    assert result.broker_message == "Root broker response."


def test_adapter_maps_broker_rejection() -> None:
    adapter = PaperBrokerExecutionAdapter(RecordingPaperBroker(status="rejected"))

    result = adapter.submit_order(bracket_order())

    assert result.status is OrderStatus.REJECTED
    assert result.rejection_reason == "Root broker response."


def test_adapter_propagates_broker_exception() -> None:
    broker = RecordingPaperBroker()
    broker.error = RuntimeError("root broker failed")

    with pytest.raises(RuntimeError, match="root broker failed"):
        PaperBrokerExecutionAdapter(broker).submit_order(bracket_order())


def test_adapter_read_methods_map_cash_and_symbol_position() -> None:
    adapter = PaperBrokerExecutionAdapter(RecordingPaperBroker())

    assert adapter.get_cash_balance() == Decimal("80000.0")
    assert adapter.get_position_quantity(" aapl ") == 7
    assert adapter.get_position_quantity("MSFT") == 0


def test_unsupported_side_is_rejected_before_broker_mutation() -> None:
    broker = RecordingPaperBroker()

    with pytest.raises(ValueError, match="buy brackets only"):
        PaperBrokerExecutionAdapter(broker).submit_order(
            bracket_order(side=TradeSide.SELL)
        )

    assert broker.submissions == []
