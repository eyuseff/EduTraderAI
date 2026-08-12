"""Typed local errors for Paper execution contract construction."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PaperExecutionContractError(ValueError):
    """Base safe error for invalid inert execution contracts."""

    reason_code: str
    safe_message: str

    def __post_init__(self) -> None:
        if not self.reason_code.strip():
            raise ValueError("reason_code cannot be empty.")
        if not self.safe_message.strip():
            raise ValueError("safe_message cannot be empty.")
        ValueError.__init__(self, self.safe_message)

    def __str__(self) -> str:
        return self.safe_message


class PaperExecutionIdentityError(PaperExecutionContractError):
    """Raised when an execution identity is malformed."""


class PaperExecutionRevisionError(PaperExecutionContractError):
    """Raised when an execution revision is malformed."""


class PaperExecutionInvariantError(PaperExecutionContractError):
    """Raised when immutable execution contracts violate invariants."""


class PaperExecutionSerializationError(PaperExecutionContractError):
    """Raised when canonical serialization cannot be made deterministic."""
