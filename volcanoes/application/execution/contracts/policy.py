"""Immutable Paper execution policy snapshot."""

from __future__ import annotations

from dataclasses import dataclass, field

from volcanoes.application.execution.contracts._validation import normalize_alias
from volcanoes.application.execution.enums import PaperExecutionOperation
from volcanoes.application.execution.errors import PaperExecutionInvariantError
from volcanoes.application.execution.fingerprints import policy_fingerprint


@dataclass(frozen=True, slots=True)
class PaperExecutionPolicySnapshot:
    """Descriptive policy facts for later eligibility evaluation."""

    policy_version: str
    allowed_operations: tuple[PaperExecutionOperation, ...]
    paper_only_required: bool = True
    explicit_approval_required: bool = True
    execution_revision_required: bool = True
    deterministic_idempotency_required: bool = True
    market_capability_validation_required: bool = True
    emergency_stop_clearance_required: bool = True
    policy_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_version",
            normalize_alias(self.policy_version, "policy_version"),
        )
        if not isinstance(self.allowed_operations, tuple):
            raise PaperExecutionInvariantError(
                "INVALID_ALLOWED_OPERATIONS",
                "Allowed operations must be an immutable tuple.",
            )
        normalized = tuple(
            sorted(set(self.allowed_operations), key=lambda item: item.value)
        )
        if not normalized or any(
            not isinstance(item, PaperExecutionOperation) for item in normalized
        ):
            raise PaperExecutionInvariantError(
                "INVALID_ALLOWED_OPERATIONS",
                "Allowed operations must contain execution operations.",
            )
        object.__setattr__(self, "allowed_operations", normalized)
        for name in (
            "paper_only_required",
            "explicit_approval_required",
            "execution_revision_required",
            "deterministic_idempotency_required",
            "market_capability_validation_required",
            "emergency_stop_clearance_required",
        ):
            if not isinstance(getattr(self, name), bool):
                raise PaperExecutionInvariantError(
                    "INVALID_POLICY_FLAG",
                    f"{name} must be a boolean.",
                )
        object.__setattr__(
            self,
            "policy_fingerprint",
            policy_fingerprint(self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "policy_fingerprint": self.policy_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "allowed_operations": self.allowed_operations,
            "deterministic_idempotency_required": (
                self.deterministic_idempotency_required
            ),
            "emergency_stop_clearance_required": (
                self.emergency_stop_clearance_required
            ),
            "execution_revision_required": self.execution_revision_required,
            "explicit_approval_required": self.explicit_approval_required,
            "market_capability_validation_required": (
                self.market_capability_validation_required
            ),
            "paper_only_required": self.paper_only_required,
            "policy_version": self.policy_version,
        }
