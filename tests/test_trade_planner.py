"""Tests for broker-free deterministic trade planning."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from volcanoes.domain import TradeIntent, TradeSide
from volcanoes.execution import TradePlan, TradePlanner
from volcanoes.portfolio import Portfolio
from volcanoes.risk import RiskConfig, RiskManager


def buy_intent(
    *,
    symbol: str = "AAPL",
    entry: str = "100",
    stop: str = "95",
) -> TradeIntent:
    return TradeIntent(
        symbol=symbol,
        side=TradeSide.BUY,
        entry_price=Decimal(entry),
        stop_price=Decimal(stop),
    )


def portfolio_state(portfolio: Portfolio) -> tuple[object, ...]:
    return (
        portfolio.cash,
        portfolio.realized_pnl,
        tuple(
            (
                symbol,
                position.quantity,
                position.average_price,
            )
            for symbol, position in sorted(portfolio.positions.items())
        ),
        tuple(portfolio.ledger.entries),
    )


def test_planner_returns_approved_deterministic_plan() -> None:
    portfolio = Portfolio(starting_cash=Decimal("100000"))
    planner = TradePlanner()
    intent = buy_intent()

    first = planner.plan(portfolio, intent)
    second = planner.plan(portfolio, intent)

    assert first == second
    assert first.approved is True
    assert first.risk_code is None
    assert first.sizing_result.quantity == 200
    assert first.sizing_result.dollar_risk == Decimal("1000")
    assert first.sizing_result.position_value == Decimal("20000")
    assert first.trade_request is not None
    assert first.trade_request.symbol == "AAPL"


def test_trade_plan_is_immutable() -> None:
    plan = TradePlanner().plan(
        Portfolio(starting_cash=Decimal("100000")),
        buy_intent(),
    )

    with pytest.raises(FrozenInstanceError):
        plan.approved = False  # type: ignore[misc]

    assert isinstance(plan, TradePlan)


def test_planner_returns_zero_quantity_rejection() -> None:
    portfolio = Portfolio(starting_cash=Decimal("100"))

    plan = TradePlanner().plan(
        portfolio,
        buy_intent(entry="1000", stop="500"),
    )

    assert plan.approved is False
    assert plan.risk_code is None
    assert plan.sizing_result.quantity == 0
    assert plan.trade_request is None
    assert plan.reason == TradePlanner.ZERO_QUANTITY_REASON


@pytest.mark.parametrize(
    ("config", "prepare", "expected_code"),
    [
        (
            RiskConfig(max_position_size=Decimal("0.10")),
            lambda portfolio: None,
            "MAX_POSITION_SIZE",
        ),
        (
            RiskConfig(),
            lambda portfolio: setattr(
                portfolio,
                "realized_pnl",
                Decimal("-3000"),
            ),
            "MAX_DAILY_LOSS",
        ),
    ],
)
def test_planner_maps_risk_violations_to_codes(
    config: RiskConfig,
    prepare: object,
    expected_code: str,
) -> None:
    portfolio = Portfolio(starting_cash=Decimal("100000"))
    prepare(portfolio)  # type: ignore[operator]
    planner = TradePlanner(risk_manager=RiskManager(config))

    plan = planner.plan(portfolio, buy_intent())

    assert plan.approved is False
    assert plan.risk_code == expected_code
    assert plan.trade_request is not None


def test_planner_does_not_mutate_portfolio() -> None:
    portfolio = Portfolio(starting_cash=Decimal("100000"))
    portfolio.buy(
        symbol="MSFT",
        quantity=10,
        price=Decimal("100"),
    )
    before = portfolio_state(portfolio)

    TradePlanner().plan(portfolio, buy_intent())

    assert portfolio_state(portfolio) == before


def test_planner_requires_no_broker() -> None:
    planner = TradePlanner()

    plan = planner.plan(
        Portfolio(starting_cash=Decimal("100000")),
        buy_intent(),
    )

    assert plan.approved is True


@pytest.mark.parametrize(
    ("prepare", "expected_code"),
    [
        (
            lambda portfolio: portfolio.buy(
                symbol="MSFT",
                quantity=950,
                price=Decimal("100"),
            ),
            "INSUFFICIENT_BUYING_POWER",
        ),
        (
            lambda portfolio: [
                portfolio.buy(
                    symbol=f"SYM{index}",
                    quantity=1,
                    price=Decimal("1"),
                )
                for index in range(10)
            ],
            "MAX_OPEN_POSITIONS",
        ),
        (
            lambda portfolio: portfolio.buy(
                symbol="MSFT",
                quantity=700,
                price=Decimal("100"),
            ),
            "MAX_PORTFOLIO_EXPOSURE",
        ),
    ],
)
def test_default_policy_profile_preserves_execution_risk_order(
    prepare: object,
    expected_code: str,
) -> None:
    portfolio = Portfolio(starting_cash=Decimal("100000"))
    prepare(portfolio)  # type: ignore[operator]

    plan = TradePlanner().plan(portfolio, buy_intent())

    assert plan.approved is False
    assert plan.risk_code == expected_code
