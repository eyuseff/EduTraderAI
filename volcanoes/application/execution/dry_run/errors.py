"""Typed errors for invalid dry-run API usage."""

from __future__ import annotations

from volcanoes.application.execution.errors import PaperExecutionContractError


class PaperDryRunError(PaperExecutionContractError):
    """Base dry-run API error."""
