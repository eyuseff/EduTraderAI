from __future__ import annotations

from decimal import Decimal

import pytest

from test_paper_qualification_integration_contracts import order_intent
from volcanoes.application.qualification.integration import (
    IntegrationOrderType,
    IntegrationTimeInForce,
    RuntimeRequestValidationError,
)
from volcanoes.application.qualification.integration.order_safety import (
    build_non_marketable_buy_limit_plan,
    require_non_marketable_buy_limit,
)


def test_builder_creates_one_share_day_limit_below_reference_best_ask() -> None:
    plan = build_non_marketable_buy_limit_plan(
        symbol=" aapl ",
        reference_best_ask=Decimal("100.50"),
    )

    assert plan.order_intent.symbol == "AAPL"
    assert plan.order_intent.quantity == 1
    assert plan.order_intent.order_type is IntegrationOrderType.LIMIT
    assert plan.order_intent.time_in_force is IntegrationTimeInForce.DAY
    assert plan.order_intent.limit_price == Decimal("100.49")
    assert plan.order_intent.limit_price < plan.reference_best_ask
    assert "one tick below" in plan.rationale.lower()


def test_builder_is_deterministic_for_off_tick_reference() -> None:
    first = build_non_marketable_buy_limit_plan(
        symbol="AAPL",
        reference_best_ask=Decimal("100.505"),
        tick_size=Decimal("0.01"),
    )
    second = build_non_marketable_buy_limit_plan(
        symbol="AAPL",
        reference_best_ask=Decimal("100.505"),
        tick_size=Decimal("0.01"),
    )

    assert first == second
    assert first.order_intent.limit_price == Decimal("100.49")


@pytest.mark.parametrize(
    "reference_best_ask",
    (Decimal("0"), Decimal("-1"), Decimal("NaN"), Decimal("Infinity")),
)
def test_invalid_reference_price_fails_closed(reference_best_ask: Decimal) -> None:
    with pytest.raises(RuntimeRequestValidationError) as error_info:
        build_non_marketable_buy_limit_plan(
            symbol="AAPL",
            reference_best_ask=reference_best_ask,
        )

    assert error_info.value.reason_code == "INVALID_QUALIFICATION_PRICE_REFERENCE"


def test_binary_float_reference_is_rejected() -> None:
    with pytest.raises(RuntimeRequestValidationError):
        build_non_marketable_buy_limit_plan(
            symbol="AAPL",
            reference_best_ask=100.50,  # type: ignore[arg-type]
        )


def test_price_too_small_for_one_tick_fails_closed() -> None:
    with pytest.raises(RuntimeRequestValidationError) as error_info:
        build_non_marketable_buy_limit_plan(
            symbol="AAPL",
            reference_best_ask=Decimal("0.01"),
            tick_size=Decimal("0.01"),
        )

    assert error_info.value.reason_code == "NO_SAFE_NON_MARKETABLE_LIMIT"


@pytest.mark.parametrize("limit_price", (Decimal("100.50"), Decimal("100.51")))
def test_marketable_or_crossing_buy_limit_is_blocked(limit_price: Decimal) -> None:
    intent = order_intent(quantity=1, limit_price=limit_price)

    with pytest.raises(RuntimeRequestValidationError) as error_info:
        require_non_marketable_buy_limit(
            intent,
            reference_best_ask=Decimal("100.50"),
        )

    assert error_info.value.reason_code == "QUALIFICATION_MARKETABLE_LIMIT_BLOCKED"


def test_existing_limit_below_ask_is_accepted() -> None:
    intent = order_intent(quantity=1, limit_price=Decimal("100.49"))

    assert (
        require_non_marketable_buy_limit(
            intent,
            reference_best_ask=Decimal("100.50"),
        )
        is intent
    )


def test_market_order_is_never_accepted_as_non_marketable_limit() -> None:
    intent = order_intent(
        quantity=1,
        order_type=IntegrationOrderType.MARKET,
        limit_price=None,
    )

    with pytest.raises(RuntimeRequestValidationError) as error_info:
        require_non_marketable_buy_limit(
            intent,
            reference_best_ask=Decimal("100.50"),
        )

    assert error_info.value.reason_code == "QUALIFICATION_LIMIT_ORDER_REQUIRED"
