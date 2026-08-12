"""Tests for position-sizing request and result models."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from volcanoes.domain import TradeIntent, TradeSide
from volcanoes.sizing import (
    PositionSizingRequest,
    PositionSizingResult,
)


def create_trade_intent() -> TradeIntent:
    """Return a valid buy trade intent."""

    return TradeIntent(
        symbol="AAPL",
        side=TradeSide.BUY,
        entry_price=Decimal("100"),
        stop_price=Decimal("95"),
    )


def test_position_sizing_request():
    intent = create_trade_intent()

    request = PositionSizingRequest(
        portfolio_equity=Decimal("100000"),
        trade_intent=intent,
        maximum_risk=Decimal("0.01"),
    )

    assert request.portfolio_equity == Decimal("100000")
    assert request.trade_intent is intent
    assert request.maximum_risk == Decimal("0.01")
    assert request.allowed_risk == Decimal("1000.00")


def test_position_sizing_request_accepts_full_equity_risk():
    request = PositionSizingRequest(
        portfolio_equity=Decimal("100000"),
        trade_intent=create_trade_intent(),
        maximum_risk=Decimal("1"),
    )

    assert request.allowed_risk == Decimal("100000")


@pytest.mark.parametrize(
    "portfolio_equity",
    [
        Decimal("0"),
        Decimal("-1"),
    ],
)
def test_non_positive_portfolio_equity_is_rejected(
    portfolio_equity: Decimal,
):
    with pytest.raises(
        ValueError,
        match="Portfolio equity must be greater than zero.",
    ):
        PositionSizingRequest(
            portfolio_equity=portfolio_equity,
            trade_intent=create_trade_intent(),
            maximum_risk=Decimal("0.01"),
        )


@pytest.mark.parametrize(
    "maximum_risk",
    [
        Decimal("0"),
        Decimal("-0.01"),
    ],
)
def test_non_positive_maximum_risk_is_rejected(
    maximum_risk: Decimal,
):
    with pytest.raises(
        ValueError,
        match="Maximum risk must be greater than zero.",
    ):
        PositionSizingRequest(
            portfolio_equity=Decimal("100000"),
            trade_intent=create_trade_intent(),
            maximum_risk=maximum_risk,
        )


def test_maximum_risk_above_one_is_rejected():
    with pytest.raises(
        ValueError,
        match="Maximum risk cannot exceed one.",
    ):
        PositionSizingRequest(
            portfolio_equity=Decimal("100000"),
            trade_intent=create_trade_intent(),
            maximum_risk=Decimal("1.01"),
        )


def test_position_sizing_request_is_immutable():
    request = PositionSizingRequest(
        portfolio_equity=Decimal("100000"),
        trade_intent=create_trade_intent(),
        maximum_risk=Decimal("0.01"),
    )

    with pytest.raises(FrozenInstanceError):
        request.maximum_risk = Decimal("0.02")


def test_position_sizing_result():
    result = PositionSizingResult(
        quantity=200,
        dollar_risk=Decimal("1000"),
        position_value=Decimal("20000"),
    )

    assert result.quantity == 200
    assert result.dollar_risk == Decimal("1000")
    assert result.position_value == Decimal("20000")


def test_zero_quantity_result():
    result = PositionSizingResult(
        quantity=0,
        dollar_risk=Decimal("0"),
        position_value=Decimal("0"),
    )

    assert result.quantity == 0
    assert result.dollar_risk == Decimal("0")
    assert result.position_value == Decimal("0")


@pytest.mark.parametrize(
    "quantity",
    [
        -1,
        -100,
    ],
)
def test_negative_quantity_is_rejected(quantity: int):
    with pytest.raises(
        ValueError,
        match="Quantity cannot be negative.",
    ):
        PositionSizingResult(
            quantity=quantity,
            dollar_risk=Decimal("100"),
            position_value=Decimal("1000"),
        )


@pytest.mark.parametrize(
    "quantity",
    [
        Decimal("1"),
        1.5,
        True,
    ],
)
def test_non_integer_quantity_is_rejected(quantity):
    with pytest.raises(
        ValueError,
        match="Quantity must be a whole number.",
    ):
        PositionSizingResult(
            quantity=quantity,
            dollar_risk=Decimal("100"),
            position_value=Decimal("1000"),
        )


def test_negative_dollar_risk_is_rejected():
    with pytest.raises(
        ValueError,
        match="Dollar risk cannot be negative.",
    ):
        PositionSizingResult(
            quantity=1,
            dollar_risk=Decimal("-1"),
            position_value=Decimal("100"),
        )


def test_negative_position_value_is_rejected():
    with pytest.raises(
        ValueError,
        match="Position value cannot be negative.",
    ):
        PositionSizingResult(
            quantity=1,
            dollar_risk=Decimal("5"),
            position_value=Decimal("-100"),
        )


def test_zero_quantity_requires_zero_dollar_risk():
    with pytest.raises(
        ValueError,
        match="Zero quantity must have zero dollar risk.",
    ):
        PositionSizingResult(
            quantity=0,
            dollar_risk=Decimal("5"),
            position_value=Decimal("0"),
        )


def test_zero_quantity_requires_zero_position_value():
    with pytest.raises(
        ValueError,
        match="Zero quantity must have zero position value.",
    ):
        PositionSizingResult(
            quantity=0,
            dollar_risk=Decimal("0"),
            position_value=Decimal("100"),
        )


def test_positive_quantity_requires_positive_dollar_risk():
    with pytest.raises(
        ValueError,
        match="Positive quantity requires positive dollar risk.",
    ):
        PositionSizingResult(
            quantity=1,
            dollar_risk=Decimal("0"),
            position_value=Decimal("100"),
        )


def test_positive_quantity_requires_positive_position_value():
    with pytest.raises(
        ValueError,
        match="Positive quantity requires positive position value.",
    ):
        PositionSizingResult(
            quantity=1,
            dollar_risk=Decimal("5"),
            position_value=Decimal("0"),
        )


def test_position_sizing_result_is_immutable():
    result = PositionSizingResult(
        quantity=200,
        dollar_risk=Decimal("1000"),
        position_value=Decimal("20000"),
    )

    with pytest.raises(FrozenInstanceError):
        result.quantity = 100
