"""Typed errors for Paper qualification transitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QualificationTransitionError(Exception):
    """Base error with stable safe metadata."""

    reason_code: str
    safe_message: str
    transition_id: str | None = None

    def __post_init__(self) -> None:
        if not self.reason_code.strip():
            raise ValueError("reason_code cannot be empty.")
        if not self.safe_message.strip():
            raise ValueError("safe_message cannot be empty.")
        Exception.__init__(self, self.safe_message)

    def __str__(self) -> str:
        return self.safe_message


class InvalidTransitionError(QualificationTransitionError):
    """Raised when a source/event pair is not accepted."""


class GuardConditionError(QualificationTransitionError):
    """Raised when deterministic guard facts are missing."""


class IdempotencyConflictError(QualificationTransitionError):
    """Raised when one idempotency key is reused for different payload."""


class StaleRevisionError(QualificationTransitionError):
    """Raised when expected revision does not match current state revision."""


class QualificationTerminalError(QualificationTransitionError):
    """Raised when a terminal workflow state is mutated."""


class BrokerStateUnresolvedError(QualificationTransitionError):
    """Raised when broker truth is unresolved and cannot be advanced."""


class ReconciliationRequiredError(QualificationTransitionError):
    """Raised when reconciliation must occur before a requested transition."""


class UnsupportedScenarioError(QualificationTransitionError):
    """Raised when scenario-specific criteria are not supported by the context."""
