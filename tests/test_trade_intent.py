"""Tests for the TradeIntent domain model."""

from decimal import Decimal

import pytest

from volcanoes.domain import TradeIntent, TradeSide


def test_buy_trade_intent():
    intent = TradeIntent(
        symbol="AAPL",
        side=TradeSide.BUY,
        entry_price=Decimal("100"),
        stop_price=Decimal("95"),
    )

    assert intent.symbol == "AAPL"
    assert intent.side is TradeSide.BUY
    assert intent.entry_price == Decimal("100")
    assert intent.stop_price == Decimal("95")
    assert intent.risk_per_share == Decimal("5")


def test_sell_trade_intent():
    intent = TradeIntent(
        symbol="AAPL",
        side=TradeSide.SELL,
        entry_price=Decimal("100"),
        stop_price=Decimal("105"),
    )

    assert intent.symbol == "AAPL"
    assert intent.side is TradeSide.SELL
    assert intent.entry_price == Decimal("100")
    assert intent.stop_price == Decimal("105")
    assert intent.risk_per_share == Decimal("5")


def test_symbol_is_normalized():
    intent = TradeIntent(
        symbol="  aapl  ",
        side=TradeSide.BUY,
        entry_price=Decimal("100"),
        stop_price=Decimal("95"),
    )

    assert intent.symbol == "AAPL"


def test_empty_symbol_is_rejected():
    with pytest.raises(
        ValueError,
        match="Trade intent symbol cannot be empty.",
    ):
        TradeIntent(
            symbol="   ",
            side=TradeSide.BUY,
            entry_price=Decimal("100"),
            stop_price=Decimal("95"),
        )


@pytest.mark.parametrize(
    "entry_price",
    [
        Decimal("0"),
        Decimal("-1"),
    ],
)
def test_non_positive_entry_price_is_rejected(
    entry_price: Decimal,
):
    with pytest.raises(
        ValueError,
        match="Entry price must be greater than zero.",
    ):
        TradeIntent(
            symbol="AAPL",
            side=TradeSide.BUY,
            entry_price=entry_price,
            stop_price=Decimal("95"),
        )


@pytest.mark.parametrize(
    "stop_price",
    [
        Decimal("0"),
        Decimal("-1"),
    ],
)
def test_non_positive_stop_price_is_rejected(
    stop_price: Decimal,
):
    with pytest.raises(
        ValueError,
        match="Stop price must be greater than zero.",
    ):
        TradeIntent(
            symbol="AAPL",
            side=TradeSide.BUY,
            entry_price=Decimal("100"),
            stop_price=stop_price,
        )


@pytest.mark.parametrize(
    "stop_price",
    [
        Decimal("100"),
        Decimal("101"),
    ],
)
def test_buy_stop_must_be_below_entry(
    stop_price: Decimal,
):
    with pytest.raises(
        ValueError,
        match="Buy stop price must be below entry price.",
    ):
        TradeIntent(
            symbol="AAPL",
            side=TradeSide.BUY,
            entry_price=Decimal("100"),
            stop_price=stop_price,
        )


@pytest.mark.parametrize(
    "stop_price",
    [
        Decimal("100"),
        Decimal("99"),
    ],
)
def test_sell_stop_must_be_above_entry(
    stop_price: Decimal,
):
    with pytest.raises(
        ValueError,
        match="Sell stop price must be above entry price.",
    ):
        TradeIntent(
            symbol="AAPL",
            side=TradeSide.SELL,
            entry_price=Decimal("100"),
            stop_price=stop_price,
        )


def test_trade_intent_is_immutable():
    intent = TradeIntent(
        symbol="AAPL",
        side=TradeSide.BUY,
        entry_price=Decimal("100"),
        stop_price=Decimal("95"),
    )

    with pytest.raises(AttributeError):
        intent.symbol = "MSFT"
