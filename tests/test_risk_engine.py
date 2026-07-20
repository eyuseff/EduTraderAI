"""Tests for the risk engine."""

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
        quantity=100,
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

    assert (
        error.value.code
        == "INSUFFICIENT_BUYING_POWER"
    )

    assert (
        error.value.message
        == "Trade exceeds available buying power."
    )
