"""Guardian decision domain model for Volcanes."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GuardianDecision:
    """Guardian's final risk decision for a candidate."""

    approved: bool
    reason: str
    risk_score: int | None = None

    def __post_init__(self) -> None:
        reason = self.reason.strip()

        if not reason:
            raise ValueError("Guardian decision reason cannot be empty.")

        if self.risk_score is not None and not 0 <= self.risk_score <= 100:
            raise ValueError("Risk score must be between 0 and 100.")

        object.__setattr__(self, "reason", reason)

    @classmethod
    def approve(
        cls,
        reason: str,
        risk_score: int | None = None,
    ) -> "GuardianDecision":
        """Create an approved Guardian decision."""

        return cls(
            approved=True,
            reason=reason,
            risk_score=risk_score,
        )

    @classmethod
    def reject(
        cls,
        reason: str,
        risk_score: int | None = None,
    ) -> "GuardianDecision":
        """Create a rejected Guardian decision."""

        return cls(
            approved=False,
            reason=reason,
            risk_score=risk_score,
        )
