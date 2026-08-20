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

MINIMUM_CONNECTED_ASK_BUFFER_BPS = Decimal("100")
MINIMUM_CONNECTED_ASK_BUFFER_AMOUNT = Decimal("1.00")


@dataclass(frozen=True, slots=True)
class NonMarketableBuyLimitPlan:
    """Offline evidence for a buffered BUY limit below the supplied NBBO."""

    order_intent: SafeOrderIntent
    reference_best_bid: Decimal
    reference_best_ask: Decimal
    tick_size: Decimal
    minimum_ask_buffer_bps: Decimal
    minimum_ask_buffer_amount: Decimal
    effective_ask_buffer: Decimal
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
        if self.order_intent.limit_price >= self.reference_best_bid:
            raise RuntimeRequestValidationError(
                reason_code="QUALIFICATION_BID_CROSSING_LIMIT_BLOCKED",
                safe_message="Qualification BUY limit must remain below the reference best bid.",
            )
        if (
            self.reference_best_ask - self.order_intent.limit_price
            < self.effective_ask_buffer
        ):
            raise RuntimeRequestValidationError(
                reason_code="QUALIFICATION_ASK_BUFFER_REQUIRED",
                safe_message="Qualification BUY limit must preserve the configured ask buffer.",
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
    reference_best_bid: Decimal,
    reference_best_ask: Decimal,
    tick_size: Decimal = Decimal("0.01"),
    minimum_ask_buffer_bps: Decimal = MINIMUM_CONNECTED_ASK_BUFFER_BPS,
    minimum_ask_buffer_amount: Decimal = MINIMUM_CONNECTED_ASK_BUFFER_AMOUNT,
) -> NonMarketableBuyLimitPlan:
    """Build a deterministic BUY limit below bid with a material ask buffer."""

    bid = _require_positive_decimal(reference_best_bid, "reference_best_bid")
    ask = _require_positive_decimal(reference_best_ask, "reference_best_ask")
    tick = _require_positive_decimal(tick_size, "tick_size")
    buffer_bps = _require_positive_decimal(
        minimum_ask_buffer_bps, "minimum_ask_buffer_bps"
    )
    buffer_amount = _require_positive_decimal(
        minimum_ask_buffer_amount, "minimum_ask_buffer_amount"
    )
    if (
        buffer_bps < MINIMUM_CONNECTED_ASK_BUFFER_BPS
        or buffer_amount < MINIMUM_CONNECTED_ASK_BUFFER_AMOUNT
    ):
        raise RuntimeRequestValidationError(
            reason_code="QUALIFICATION_BUFFER_WEAKENING_BLOCKED",
            safe_message="Connected Paper qualification buffers cannot be weakened.",
        )
    if bid >= ask:
        raise RuntimeRequestValidationError(
            reason_code="INVALID_QUALIFICATION_SPREAD",
            safe_message="Qualification requires a positive, unlocked bid-ask spread.",
        )
    proportional_buffer = ask * buffer_bps / Decimal("10000")
    effective_buffer = max(buffer_amount, proportional_buffer)
    raw_limit_ceiling = min(bid - tick, ask - effective_buffer)
    limit_price = (raw_limit_ceiling / tick).to_integral_value(
        rounding=ROUND_FLOOR
    ) * tick
    if (
        limit_price <= 0
        or limit_price >= bid
        or limit_price >= ask
        or ask - limit_price < effective_buffer
    ):
        raise RuntimeRequestValidationError(
            reason_code="NO_SAFE_BUFFERED_LIMIT",
            safe_message="No positive buffered qualification limit can be constructed.",
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
        reference_best_bid=bid,
        reference_best_ask=ask,
        tick_size=tick,
        minimum_ask_buffer_bps=buffer_bps,
        minimum_ask_buffer_amount=buffer_amount,
        effective_ask_buffer=effective_buffer,
        rationale=(
            "One-share Paper qualification BUY limit is below the reference best bid "
            "and preserves the greater of the configured absolute or proportional "
            "distance below the reference best ask. This reduces but cannot eliminate "
            "fill risk."
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
