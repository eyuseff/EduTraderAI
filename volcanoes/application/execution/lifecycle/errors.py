"""Typed lifecycle errors for invalid API usage."""

from __future__ import annotations

from volcanoes.application.execution.errors import PaperExecutionContractError


class PaperExecutionLifecycleError(PaperExecutionContractError):
    """Base class for Paper execution lifecycle API errors."""


class InvalidLifecycleTransitionError(PaperExecutionLifecycleError):
    """Raised for impossible lifecycle specifications."""


class StaleExecutionRevisionError(PaperExecutionLifecycleError):
    """Raised when callers request exception-style stale revision handling."""


class LifecycleGuardError(PaperExecutionLifecycleError):
    """Raised for invalid guard construction."""


class LifecycleCommandConflictError(PaperExecutionLifecycleError):
    """Raised for invalid command-conflict API usage."""


class LifecycleIdempotencyConflictError(PaperExecutionLifecycleError):
    """Raised for invalid idempotency-conflict API usage."""


class LifecycleBrokerObservationConflictError(PaperExecutionLifecycleError):
    """Raised for invalid broker-observation conflict API usage."""


class LifecycleTerminalStateError(PaperExecutionLifecycleError):
    """Raised for invalid terminal-state API usage."""


class LifecycleInvariantError(PaperExecutionLifecycleError):
    """Raised for impossible lifecycle invariant violations."""
