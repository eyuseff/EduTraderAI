"""Typed errors for invalid eligibility API usage."""

from __future__ import annotations

from volcanoes.application.execution.errors import PaperExecutionContractError


class PaperExecutionEligibilityError(PaperExecutionContractError):
    """Raised for invalid eligibility service inputs or contradictory policies."""
