"""Tests for the daily loss risk limit."""

from decimal import Decimal

import pytest

from volcanoes.domain import TradeRequest
from volcanoes.portfolio import Portfolio
from volcanoes.risk import (
    RiskManager,
    RiskViolation,
)


def create_small_trade() -> TradeRequest:
    """Return a trade that passes the other risk rules."""

    return TradeRequest(
        symbol="AAPL",
        quantity=1,
        price=Decimal("100"),
    )


def test_trade_allowed_before_daily_loss_limit():
    portfolio = Portfolio(
        starting_cash=Decimal("10000")
    )
    portfolio.realized_pnl = Decimal("-299")

    manager = RiskManager()

    assert manager.validate_trade(
        portfolio,
        create_small_trade(),
    ) is True


def test_trade_rejected_at_daily_loss_limit():
    portfolio = Portfolio(
        starting_cash=Decimal("10000")
    )
    portfolio.realized_pnl = Decimal("-300")

    manager = RiskManager()

    with pytest.raises(RiskViolation) as error:
        manager.validate_trade(
            portfolio,
            create_small_trade(),
        )

    assert error.value.code == "MAX_DAILY_LOSS"
    assert (
        error.value.message
        == "Maximum daily loss limit has been reached."
    )


def test_trade_rejected_beyond_daily_loss_limit():
    portfolio = Portfolio(
        starting_cash=Decimal("10000")
    )
    portfolio.realized_pnl = Decimal("-350")

    manager = RiskManager()

    with pytest.raises(RiskViolation) as error:
        manager.validate_trade(
            portfolio,
            create_small_trade(),
        )

    assert error.value.code == "MAX_DAILY_LOSS"
