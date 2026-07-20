"""Tests for the Volcanes risk engine."""

from decimal import Decimal

import pytest

from volcanoes.domain import TradeRequest
from volcanoes.portfolio import Portfolio
from volcanoes.risk import (
    RiskConfig,
    RiskManager,
    RiskViolation,
)


def test_default_config():
    config = RiskConfig()

    assert config.max_risk_per_trade == Decimal("0.01")
    assert config.max_daily_loss == Decimal("0.03")
    assert config.max_portfolio_exposure == Decimal("0.80")
    assert config.max_position_size == Decimal("0.20")
    assert config.max_open_positions == 10


def test_manager_uses_default_config():
    manager = RiskManager()

    assert isinstance(manager.config, RiskConfig)


def test_trade_within_buying_power():
    portfolio = Portfolio(
        starting_cash=Decimal("10000")
    )

    trade = TradeRequest(
        symbol="AAPL",
        quantity=10,
        price=Decimal("50"),
    )

    manager = RiskManager()

    assert manager.validate_trade(
        portfolio,
        trade,
    ) is True


def test_trade_exceeds_buying_power():
    portfolio = Portfolio(
        starting_cash=Decimal("10000")
    )

    trade = TradeRequest(
        symbol="AAPL",
        quantity=500,
        price=Decimal("50"),
    )

    manager = RiskManager()

    with pytest.raises(RiskViolation) as error:
        manager.validate_trade(
            portfolio,
            trade,
        )

    assert error.value.code == "INSUFFICIENT_BUYING_POWER"
    assert (
        error.value.message
        == "Trade exceeds available buying power."
    )


def test_trade_within_maximum_position_size():
    portfolio = Portfolio(
        starting_cash=Decimal("10000")
    )

    trade = TradeRequest(
        symbol="AAPL",
        quantity=20,
        price=Decimal("100"),
    )

    manager = RiskManager()

    assert manager.validate_trade(
        portfolio,
        trade,
    ) is True


def test_trade_exceeds_maximum_position_size():
    portfolio = Portfolio(
        starting_cash=Decimal("10000")
    )

    trade = TradeRequest(
        symbol="AAPL",
        quantity=21,
        price=Decimal("100"),
    )

    manager = RiskManager()

    with pytest.raises(RiskViolation) as error:
        manager.validate_trade(
            portfolio,
            trade,
        )

    assert error.value.code == "MAX_POSITION_SIZE"
    assert (
        error.value.message
        == "Trade exceeds maximum position size."
    )


def test_additional_trade_uses_existing_position():
    portfolio = Portfolio(
        starting_cash=Decimal("10000")
    )

    portfolio.buy(
        symbol="AAPL",
        quantity=15,
        price=Decimal("100"),
    )

    trade = TradeRequest(
        symbol="AAPL",
        quantity=6,
        price=Decimal("100"),
    )

    manager = RiskManager()

    with pytest.raises(RiskViolation) as error:
        manager.validate_trade(
            portfolio,
            trade,
        )

    assert error.value.code == "MAX_POSITION_SIZE"


def test_maximum_open_positions_exceeded():
    portfolio = Portfolio(
        starting_cash=Decimal("100000")
    )

    for index in range(10):
        portfolio.buy(
            symbol=f"SYM{index}",
            quantity=1,
            price=Decimal("100"),
        )

    trade = TradeRequest(
        symbol="NEW",
        quantity=1,
        price=Decimal("100"),
    )

    manager = RiskManager()

    with pytest.raises(RiskViolation) as error:
        manager.validate_trade(
            portfolio,
            trade,
        )

    assert error.value.code == "MAX_OPEN_POSITIONS"
    assert (
        error.value.message
        == "Maximum number of open positions exceeded."
    )


def test_existing_position_does_not_count_again():
    portfolio = Portfolio(
        starting_cash=Decimal("100000")
    )

    for index in range(10):
        portfolio.buy(
            symbol=f"SYM{index}",
            quantity=1,
            price=Decimal("100"),
        )

    trade = TradeRequest(
        symbol="SYM5",
        quantity=1,
        price=Decimal("100"),
    )

    manager = RiskManager()

    assert manager.validate_trade(
        portfolio,
        trade,
    ) is True


def test_trade_within_maximum_portfolio_exposure():
    portfolio = Portfolio(
        starting_cash=Decimal("100000")
    )

    for index in range(5):
        portfolio.buy(
            symbol=f"ASSET{index}",
            quantity=150,
            price=Decimal("100"),
        )

    trade = TradeRequest(
        symbol="NEW",
        quantity=40,
        price=Decimal("100"),
    )

    manager = RiskManager()

    assert portfolio.invested_value == Decimal("75000")
    assert trade.cost == Decimal("4000")

    assert manager.validate_trade(
        portfolio,
        trade,
    ) is True


def test_trade_at_maximum_portfolio_exposure():
    portfolio = Portfolio(
        starting_cash=Decimal("100000")
    )

    for index in range(5):
        portfolio.buy(
            symbol=f"ASSET{index}",
            quantity=150,
            price=Decimal("100"),
        )

    trade = TradeRequest(
        symbol="NEW",
        quantity=50,
        price=Decimal("100"),
    )

    manager = RiskManager()

    assert portfolio.invested_value == Decimal("75000")
    assert trade.cost == Decimal("5000")

    assert manager.validate_trade(
        portfolio,
        trade,
    ) is True


def test_trade_exceeds_maximum_portfolio_exposure():
    portfolio = Portfolio(
        starting_cash=Decimal("100000")
    )

    for index in range(5):
        portfolio.buy(
            symbol=f"ASSET{index}",
            quantity=150,
            price=Decimal("100"),
        )

    trade = TradeRequest(
        symbol="NEW",
        quantity=51,
        price=Decimal("100"),
    )

    manager = RiskManager()

    with pytest.raises(RiskViolation) as error:
        manager.validate_trade(
            portfolio,
            trade,
        )

    assert error.value.code == "MAX_PORTFOLIO_EXPOSURE"
    assert (
        error.value.message
        == "Trade exceeds maximum portfolio exposure."
    )


def test_portfolio_reports_open_position_count():
    portfolio = Portfolio(
        starting_cash=Decimal("10000")
    )

    assert portfolio.open_positions == 0

    portfolio.buy(
        symbol="AAPL",
        quantity=1,
        price=Decimal("100"),
    )

    portfolio.buy(
        symbol="MSFT",
        quantity=1,
        price=Decimal("100"),
    )

    assert portfolio.open_positions == 2

    portfolio.sell(
        symbol="AAPL",
        quantity=1,
        price=Decimal("100"),
    )

    assert portfolio.open_positions == 1
