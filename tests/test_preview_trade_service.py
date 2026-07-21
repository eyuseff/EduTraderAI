"""Tests for the broker-free Preview Trade application service."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from volcanoes.application.services import (
    PreviewTradeRequest,
    PreviewTradeResult,
    PreviewTradeService,
)
from volcanoes.domain import TradeSide
from volcanoes.execution import TradePlanner
from volcanoes.portfolio import Portfolio
from volcanoes.risk import RiskConfig, RiskManager


def request(
    *,
    symbol: str = "AAPL",
    side: TradeSide = TradeSide.BUY,
    entry: str = "100",
    stop: str = "95",
    target: str = "110",
) -> PreviewTradeRequest:
    return PreviewTradeRequest(
        symbol=symbol,
        side=side,
        entry_price=Decimal(entry),
        stop_price=Decimal(stop),
        target_price=Decimal(target),
    )


def portfolio_state(portfolio: Portfolio) -> tuple[object, ...]:
    return (
        portfolio.cash,
        portfolio.realized_pnl,
        tuple(portfolio.positions.items()),
        tuple(portfolio.ledger.entries),
    )


def test_preview_returns_approved_result_and_reward_risk() -> None:
    result = PreviewTradeService().preview(
        Portfolio(starting_cash=Decimal("100000")),
        request(),
    )

    assert result.approved is True
    assert result.quantity == 200
    assert result.dollar_risk == Decimal("1000")
    assert result.position_value == Decimal("20000")
    assert result.reward_risk == Decimal("2")
    assert result.reasons == ()
    assert result.risk_code is None


def test_preview_supports_sell_reward_risk() -> None:
    result = PreviewTradeService().preview(
        Portfolio(starting_cash=Decimal("100000")),
        request(
            side=TradeSide.SELL,
            stop="105",
            target="90",
        ),
    )

    assert result.reward_risk == Decimal("2")


def test_preview_result_and_request_are_immutable() -> None:
    preview_request = request()
    result = PreviewTradeService().preview(
        Portfolio(starting_cash=Decimal("100000")),
        preview_request,
    )

    with pytest.raises(FrozenInstanceError):
        preview_request.symbol = "MSFT"  # type: ignore[misc]

    with pytest.raises(FrozenInstanceError):
        result.approved = False  # type: ignore[misc]

    assert isinstance(result, PreviewTradeResult)


@pytest.mark.parametrize(
    ("preview_request", "reason"),
    [
        (request(symbol="   "), "symbol cannot be empty"),
        (request(entry="0"), "Entry price must be greater than zero"),
        (request(stop="100"), "stop price must be below entry"),
        (request(target="100"), "target price must be above entry"),
        (request(target="0"), "Target price must be greater than zero"),
        (
            PreviewTradeRequest(
                symbol="AAPL",
                side=TradeSide.BUY,
                entry_price=100,  # type: ignore[arg-type]
                stop_price=Decimal("95"),
                target_price=Decimal("110"),
            ),
            "entry_price must be a Decimal",
        ),
    ],
)
def test_preview_maps_invalid_requests_to_rejections(
    preview_request: PreviewTradeRequest,
    reason: str,
) -> None:
    result = PreviewTradeService().preview(
        Portfolio(starting_cash=Decimal("100000")),
        preview_request,
    )

    assert result.approved is False
    assert result.quantity == 0
    assert result.reward_risk == Decimal("0")
    assert result.risk_code == PreviewTradeService.INVALID_REQUEST
    assert reason in result.reasons[0]


def test_preview_maps_planner_risk_code() -> None:
    planner = TradePlanner(
        risk_manager=RiskManager(RiskConfig(max_position_size=Decimal("0.10")))
    )
    service = PreviewTradeService(planner)

    result = service.preview(
        Portfolio(starting_cash=Decimal("100000")),
        request(),
    )

    assert result.approved is False
    assert result.risk_code == "MAX_POSITION_SIZE"
    assert result.reasons == ("Trade exceeds maximum position size.",)


def test_preview_is_deterministic_and_does_not_mutate_portfolio() -> None:
    portfolio = Portfolio(starting_cash=Decimal("100000"))
    before = portfolio_state(portfolio)
    service = PreviewTradeService()
    preview_request = request()

    first = service.preview(portfolio, preview_request)
    second = service.preview(portfolio, preview_request)

    assert first == second
    assert portfolio_state(portfolio) == before


def test_preview_requires_no_broker() -> None:
    service = PreviewTradeService()

    result = service.preview(
        Portfolio(starting_cash=Decimal("100000")),
        request(),
    )

    assert result.approved is True
