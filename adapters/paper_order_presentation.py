"""Operator-facing values for the Streamlit Paper Order page."""

from __future__ import annotations

from trading.risk_manager import RiskDecision

REJECTED_APPROVED_QUANTITY = "—"


def approved_quantity_display(decision: RiskDecision) -> int | str:
    """Show an approved size only when the decision is actually approved."""

    if not decision.approved:
        return REJECTED_APPROVED_QUANTITY
    return decision.quantity
