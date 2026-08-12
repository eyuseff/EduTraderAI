"""Tests for the fixed-fractional PositionSizer."""

from decimal import Decimal

from volcanoes.domain import TradeIntent, TradeSide
from volcanoes.sizing import (
    PositionSizer,
    PositionSizingRequest,
    PositionSizingResult,
)


def create_request(
    *,
    portfolio_equity: Decimal = Decimal("100000"),
    maximum_risk: Decimal = Decimal("0.01"),
    entry_price: Decimal = Decimal("100"),
    stop_price: Decimal = Decimal("95"),
    side: TradeSide = TradeSide.BUY,
) -> PositionSizingRequest:
    """Create a valid position-sizing request."""

    intent = TradeIntent(
        symbol="AAPL",
        side=side,
        entry_price=entry_price,
        stop_price=stop_price,
    )

    return PositionSizingRequest(
        portfolio_equity=portfolio_equity,
        trade_intent=intent,
        maximum_risk=maximum_risk,
    )


def test_position_sizer_calculates_exact_quantity():
    request = create_request()

    result = PositionSizer().size_position(request)

    assert isinstance(result, PositionSizingResult)
    assert result.quantity == 200
    assert result.dollar_risk == Decimal("1000")
    assert result.position_value == Decimal("20000")


def test_position_sizer_rounds_quantity_down():
    request = create_request(
        portfolio_equity=Decimal("10000"),
        maximum_risk=Decimal("0.01"),
        entry_price=Decimal("50"),
        stop_price=Decimal("47"),
    )

    result = PositionSizer().size_position(request)

    assert request.allowed_risk == Decimal("100.00")
    assert request.trade_intent.risk_per_share == Decimal("3")
    assert result.quantity == 33
    assert result.dollar_risk == Decimal("99")
    assert result.position_value == Decimal("1650")


def test_position_sizer_never_exceeds_allowed_risk():
    request = create_request(
        portfolio_equity=Decimal("12345"),
        maximum_risk=Decimal("0.0075"),
        entry_price=Decimal("81.25"),
        stop_price=Decimal("78.40"),
    )

    result = PositionSizer().size_position(request)

    assert result.dollar_risk <= request.allowed_risk
    assert (
        result.dollar_risk
        + request.trade_intent.risk_per_share
        > request.allowed_risk
    )


def test_position_sizer_supports_sell_intent():
    request = create_request(
        entry_price=Decimal("100"),
        stop_price=Decimal("105"),
        side=TradeSide.SELL,
    )

    result = PositionSizer().size_position(request)

    assert request.trade_intent.risk_per_share == Decimal("5")
    assert result.quantity == 200
    assert result.dollar_risk == Decimal("1000")
    assert result.position_value == Decimal("20000")


def test_position_sizer_returns_zero_when_one_unit_is_too_risky():
    request = create_request(
        portfolio_equity=Decimal("1000"),
        maximum_risk=Decimal("0.01"),
        entry_price=Decimal("100"),
        stop_price=Decimal("80"),
    )

    result = PositionSizer().size_position(request)

    assert request.allowed_risk == Decimal("10.00")
    assert request.trade_intent.risk_per_share == Decimal("20")
    assert result.quantity == 0
    assert result.dollar_risk == Decimal("0.00")
    assert result.position_value == Decimal("0.00")


def test_position_sizer_uses_fractional_price_risk():
    request = create_request(
        portfolio_equity=Decimal("25000"),
        maximum_risk=Decimal("0.01"),
        entry_price=Decimal("25.75"),
        stop_price=Decimal("24.50"),
    )

    result = PositionSizer().size_position(request)

    assert request.allowed_risk == Decimal("250.00")
    assert request.trade_intent.risk_per_share == Decimal("1.25")
    assert result.quantity == 200
    assert result.dollar_risk == Decimal("250.00")
    assert result.position_value == Decimal("5150.00")


def test_position_sizer_is_deterministic():
    request = create_request()
    sizer = PositionSizer()

    first_result = sizer.size_position(request)
    second_result = sizer.size_position(request)

    assert first_result == second_result


def test_position_sizer_does_not_modify_request():
    request = create_request()

    original_equity = request.portfolio_equity
    original_maximum_risk = request.maximum_risk
    original_intent = request.trade_intent

    PositionSizer().size_position(request)

    assert request.portfolio_equity == original_equity
    assert request.maximum_risk == original_maximum_risk
    assert request.trade_intent is original_intent
