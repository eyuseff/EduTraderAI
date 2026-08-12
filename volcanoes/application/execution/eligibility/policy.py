"""Immutable Paper execution eligibility policy."""

from __future__ import annotations

from dataclasses import dataclass, field

from volcanoes.application.execution.contracts._validation import normalize_alias
from volcanoes.application.execution.enums import PaperExecutionOperation
from volcanoes.application.execution.eligibility.errors import (
    PaperExecutionEligibilityError,
)
from volcanoes.application.execution.fingerprints import (
    eligibility_policy_fingerprint,
)


@dataclass(frozen=True, slots=True)
class PaperExecutionEligibilityPolicy:
    """Explicit deterministic policy for pure eligibility evaluation."""

    policy_version: str
    allowed_operations: tuple[PaperExecutionOperation, ...] = (
        PaperExecutionOperation.SUBMIT,
        PaperExecutionOperation.CANCEL,
        PaperExecutionOperation.REPLACE,
    )
    require_paper_mode: bool = True
    require_explicit_approval: bool = True
    require_approval_binding: bool = True
    require_unexpired_approval: bool = True
    require_policy_snapshot_compatibility: bool = True
    require_expected_revision: bool = True
    require_initial_submit_revision: bool = True
    require_idempotency_key: bool = True
    require_idempotency_key_consistency: bool = False
    require_command_identity_consistency: bool = True
    require_payload_fingerprint_consistency: bool = True
    require_context_identity_consistency: bool = True
    require_aggregate_identity_consistency: bool = True
    require_correlation_identity_consistency: bool = True
    require_supported_intent: bool = True
    require_external_market_capability: bool = False
    require_external_emergency_stop_clearance: bool = False
    require_external_risk_clearance: bool = False
    require_external_account_clearance: bool = False
    policy_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "policy_version",
            normalize_alias(self.policy_version, "policy_version"),
        )
        if not isinstance(self.allowed_operations, tuple):
            raise PaperExecutionEligibilityError(
                "INVALID_ALLOWED_OPERATIONS",
                "Allowed operations must be an immutable tuple.",
            )
        normalized = tuple(
            sorted(set(self.allowed_operations), key=lambda item: item.value)
        )
        if not normalized or any(
            not isinstance(item, PaperExecutionOperation) for item in normalized
        ):
            raise PaperExecutionEligibilityError(
                "INVALID_ALLOWED_OPERATIONS",
                "Allowed operations must contain execution operations.",
            )
        object.__setattr__(self, "allowed_operations", normalized)
        for name in (
            "require_paper_mode",
            "require_explicit_approval",
            "require_approval_binding",
            "require_unexpired_approval",
            "require_policy_snapshot_compatibility",
            "require_expected_revision",
            "require_initial_submit_revision",
            "require_idempotency_key",
            "require_idempotency_key_consistency",
            "require_command_identity_consistency",
            "require_payload_fingerprint_consistency",
            "require_context_identity_consistency",
            "require_aggregate_identity_consistency",
            "require_correlation_identity_consistency",
            "require_supported_intent",
            "require_external_market_capability",
            "require_external_emergency_stop_clearance",
            "require_external_risk_clearance",
            "require_external_account_clearance",
        ):
            if not isinstance(getattr(self, name), bool):
                raise PaperExecutionEligibilityError(
                    "INVALID_POLICY_FLAG",
                    f"{name} must be a boolean.",
                )
        if self.require_approval_binding and not self.require_explicit_approval:
            raise PaperExecutionEligibilityError(
                "CONTRADICTORY_POLICY",
                "Approval binding cannot be required when approval is optional.",
            )
        if self.require_unexpired_approval and not self.require_explicit_approval:
            raise PaperExecutionEligibilityError(
                "CONTRADICTORY_POLICY",
                "Approval expiry cannot be required when approval is optional.",
            )
        object.__setattr__(
            self,
            "policy_fingerprint",
            eligibility_policy_fingerprint(self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "policy_fingerprint": self.policy_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "allowed_operations": self.allowed_operations,
            "policy_version": self.policy_version,
            "require_aggregate_identity_consistency": (
                self.require_aggregate_identity_consistency
            ),
            "require_approval_binding": self.require_approval_binding,
            "require_command_identity_consistency": (
                self.require_command_identity_consistency
            ),
            "require_context_identity_consistency": (
                self.require_context_identity_consistency
            ),
            "require_correlation_identity_consistency": (
                self.require_correlation_identity_consistency
            ),
            "require_expected_revision": self.require_expected_revision,
            "require_explicit_approval": self.require_explicit_approval,
            "require_external_account_clearance": (
                self.require_external_account_clearance
            ),
            "require_external_emergency_stop_clearance": (
                self.require_external_emergency_stop_clearance
            ),
            "require_external_market_capability": (
                self.require_external_market_capability
            ),
            "require_external_risk_clearance": self.require_external_risk_clearance,
            "require_idempotency_key": self.require_idempotency_key,
            "require_idempotency_key_consistency": (
                self.require_idempotency_key_consistency
            ),
            "require_initial_submit_revision": self.require_initial_submit_revision,
            "require_paper_mode": self.require_paper_mode,
            "require_payload_fingerprint_consistency": (
                self.require_payload_fingerprint_consistency
            ),
            "require_policy_snapshot_compatibility": (
                self.require_policy_snapshot_compatibility
            ),
            "require_supported_intent": self.require_supported_intent,
            "require_unexpired_approval": self.require_unexpired_approval,
        }
