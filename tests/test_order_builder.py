"""Tests for the OrderBuilder."""

from decimal import Decimal

from volcanoes.domain import (
    TradeIntent,
    TradeRequest,
    TradeSide,
)
from volcanoes.execution import OrderBuilder
from volcanoes.sizing import PositionSizingResult


def create_trade_intent() -> TradeIntent:
    return TradeIntent(
        symbol="AAPL",
        side=TradeSide.BUY,
        entry_price=Decimal("100"),
        stop_price=Decimal("95"),
    )


def create_sizing_result() -> PositionSizingResult:
    return PositionSizingResult(
        quantity=200,
        dollar_risk=Decimal("1000"),
        position_value=Decimal("20000"),
    )


def test_order_builder_creates_trade_request():
    builder = OrderBuilder()

    request = builder.build(
        create_trade_intent(),
        create_sizing_result(),
    )

    assert isinstance(request, TradeRequest)
    assert request.symbol == "AAPL"
    assert request.quantity == 200
    assert request.price == Decimal("100")


def test_order_builder_uses_entry_price():
    builder = OrderBuilder()

    intent = TradeIntent(
        symbol="MSFT",
        side=TradeSide.BUY,
        entry_price=Decimal("245.75"),
        stop_price=Decimal("240"),
    )

    result = PositionSizingResult(
        quantity=50,
        dollar_risk=Decimal("287.50"),
        position_value=Decimal("12287.50"),
    )

    request = builder.build(
        intent,
        result,
    )

    assert request.price == Decimal("245.75")


def test_order_builder_preserves_symbol():
    builder = OrderBuilder()

    intent = TradeIntent(
        symbol="NVDA",
        side=TradeSide.BUY,
        entry_price=Decimal("150"),
        stop_price=Decimal("145"),
    )

    result = PositionSizingResult(
        quantity=10,
        dollar_risk=Decimal("50"),
        position_value=Decimal("1500"),
    )

    request = builder.build(
        intent,
        result,
    )

    assert request.symbol == "NVDA"


def test_order_builder_supports_zero_quantity():
    builder = OrderBuilder()

    result = PositionSizingResult(
        quantity=0,
        dollar_risk=Decimal("0"),
        position_value=Decimal("0"),
    )

    request = builder.build(
        create_trade_intent(),
        result,
    )

    assert request.quantity == 0


def test_order_builder_is_deterministic():
    builder = OrderBuilder()

    first = builder.build(
        create_trade_intent(),
        create_sizing_result(),
    )

    second = builder.build(
        create_trade_intent(),
        create_sizing_result(),
    )

    assert first == second
