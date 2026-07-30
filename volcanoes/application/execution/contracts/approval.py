"""Immutable Paper execution approval evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from volcanoes.application.execution.contracts._validation import (
    normalize_alias,
    require_datetime,
)
from volcanoes.application.execution.enums import PaperExecutionApprovalKind
from volcanoes.application.execution.errors import PaperExecutionInvariantError
from volcanoes.application.execution.fingerprints import approval_fingerprint


@dataclass(frozen=True, slots=True)
class PaperExecutionApproval:
    """Evidence that approval was recorded; it does not decide approval."""

    approval_kind: PaperExecutionApprovalKind
    approver_reference: str
    approval_reference: str
    bound_fingerprint: str
    approved_at: datetime
    expires_at: datetime | None = None
    approval_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.approval_kind, PaperExecutionApprovalKind):
            raise PaperExecutionInvariantError(
                "INVALID_APPROVAL_KIND",
                "Unsupported approval kind.",
            )
        object.__setattr__(
            self,
            "approver_reference",
            normalize_alias(self.approver_reference, "approver_reference"),
        )
        object.__setattr__(
            self,
            "approval_reference",
            normalize_alias(self.approval_reference, "approval_reference"),
        )
        object.__setattr__(
            self,
            "bound_fingerprint",
            normalize_alias(self.bound_fingerprint, "bound_fingerprint"),
        )
        object.__setattr__(
            self, "approved_at", require_datetime(self.approved_at, "approved_at")
        )
        if self.expires_at is not None:
            object.__setattr__(
                self,
                "expires_at",
                require_datetime(self.expires_at, "expires_at"),
            )
            if self.expires_at < self.approved_at:
                raise PaperExecutionInvariantError(
                    "APPROVAL_EXPIRY_BEFORE_APPROVAL",
                    "Approval expiry cannot be before approval time.",
                )
        object.__setattr__(
            self,
            "approval_fingerprint",
            approval_fingerprint(self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "approval_fingerprint": self.approval_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "approval_kind": self.approval_kind,
            "approval_reference": self.approval_reference,
            "approved_at": self.approved_at,
            "approver_reference": self.approver_reference,
            "bound_fingerprint": self.bound_fingerprint,
            "expires_at": self.expires_at,
        }
