"""Fail-closed order-safety guards for Paper qualification integration."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR

from volcanoes.application.qualification.integration.contracts import (
    IntegrationOrderType,
    IntegrationTimeInForce,
    SafeOrderIntent,
)
from volcanoes.application.qualification.integration.errors import (
    RuntimeRequestValidationError,
)


@dataclass(frozen=True, slots=True)
class NonMarketableBuyLimitPlan:
    """Offline evidence for a one-share BUY limit below a supplied best ask."""

    order_intent: SafeOrderIntent
    reference_best_ask: Decimal
    tick_size: Decimal
    rationale: str

    def __post_init__(self) -> None:
        require_one_share_order_intent(self.order_intent)
        if self.order_intent.order_type is not IntegrationOrderType.LIMIT:
            raise RuntimeRequestValidationError(
                reason_code="QUALIFICATION_LIMIT_ORDER_REQUIRED",
                safe_message="Paper qualification requires a limit order intent.",
            )
        if self.order_intent.limit_price is None:
            raise RuntimeRequestValidationError(
                reason_code="QUALIFICATION_LIMIT_PRICE_REQUIRED",
                safe_message="Paper qualification requires a limit price.",
            )
        if self.order_intent.limit_price >= self.reference_best_ask:
            raise RuntimeRequestValidationError(
                reason_code="QUALIFICATION_MARKETABLE_LIMIT_BLOCKED",
                safe_message="Qualification BUY limit must remain below the reference best ask.",
            )


def require_one_share_order_intent(
    order_intent: SafeOrderIntent | None,
) -> SafeOrderIntent | None:
    """Allow no order or exactly one share; reject qualification sizing overrides."""

    if order_intent is None:
        return None
    if not isinstance(order_intent, SafeOrderIntent):
        raise RuntimeRequestValidationError(
            reason_code="INVALID_QUALIFICATION_ORDER_INTENT",
            safe_message="Qualification order intent is invalid.",
        )
    if order_intent.quantity != 1:
        raise RuntimeRequestValidationError(
            reason_code="QUALIFICATION_ONE_SHARE_REQUIRED",
            safe_message="Paper qualification orders must use exactly one share.",
        )
    return order_intent


def build_non_marketable_buy_limit_plan(
    *,
    symbol: str,
    reference_best_ask: Decimal,
    tick_size: Decimal = Decimal("0.01"),
) -> NonMarketableBuyLimitPlan:
    """Build a deterministic one-share BUY limit strictly below a supplied best ask."""

    ask = _require_positive_decimal(reference_best_ask, "reference_best_ask")
    tick = _require_positive_decimal(tick_size, "tick_size")
    aligned_at_or_below_ask = (ask / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
    limit_price = aligned_at_or_below_ask - tick
    if limit_price <= 0 or limit_price >= ask:
        raise RuntimeRequestValidationError(
            reason_code="NO_SAFE_NON_MARKETABLE_LIMIT",
            safe_message="No positive non-marketable qualification limit can be constructed.",
        )
    intent = SafeOrderIntent(
        symbol=symbol,
        quantity=1,
        order_type=IntegrationOrderType.LIMIT,
        limit_price=limit_price,
        time_in_force=IntegrationTimeInForce.DAY,
    )
    return NonMarketableBuyLimitPlan(
        order_intent=intent,
        reference_best_ask=ask,
        tick_size=tick,
        rationale=(
            "One-share Paper qualification BUY limit is one tick below the "
            "best tick-aligned price at or below the supplied best ask."
        ),
    )


def require_non_marketable_buy_limit(
    order_intent: SafeOrderIntent,
    *,
    reference_best_ask: Decimal,
) -> SafeOrderIntent:
    """Fail closed unless an existing one-share BUY limit is below the reference ask."""

    require_one_share_order_intent(order_intent)
    ask = _require_positive_decimal(reference_best_ask, "reference_best_ask")
    if order_intent.order_type is not IntegrationOrderType.LIMIT:
        raise RuntimeRequestValidationError(
            reason_code="QUALIFICATION_LIMIT_ORDER_REQUIRED",
            safe_message="Paper qualification requires a limit order intent.",
        )
    if order_intent.limit_price is None or order_intent.limit_price >= ask:
        raise RuntimeRequestValidationError(
            reason_code="QUALIFICATION_MARKETABLE_LIMIT_BLOCKED",
            safe_message="Qualification BUY limit must remain below the reference best ask.",
        )
    return order_intent


def _require_positive_decimal(value: object, field_name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise RuntimeRequestValidationError(
            reason_code="INVALID_QUALIFICATION_PRICE_REFERENCE",
            safe_message=f"{field_name} must be a positive finite Decimal.",
        )
    return value
