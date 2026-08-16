"""Fail-closed order-safety guards for Paper qualification integration."""

from __future__ import annotations

from volcanoes.application.qualification.integration.contracts import SafeOrderIntent
from volcanoes.application.qualification.integration.errors import (
    RuntimeRequestValidationError,
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
