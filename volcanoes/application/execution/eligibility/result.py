"""Immutable Paper execution eligibility result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from volcanoes.application.execution.contracts._validation import normalize_code
from volcanoes.application.execution.eligibility.enums import (
    PaperExecutionEligibilityCriterion,
    PaperExecutionEligibilityCriterionOutcome,
    PaperExecutionEligibilityDecision,
    PaperExecutionEligibilityFailureCode,
    PaperExecutionEligibilitySeverity,
)
from volcanoes.application.execution.fingerprints import (
    eligibility_result_fingerprint,
)
from volcanoes.application.execution.identities import (
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
)


@dataclass(frozen=True, slots=True)
class PaperExecutionEligibilityCriterionResult:
    """One deterministic criterion outcome."""

    criterion: PaperExecutionEligibilityCriterion
    outcome: PaperExecutionEligibilityCriterionOutcome
    severity: PaperExecutionEligibilitySeverity
    code: PaperExecutionEligibilityFailureCode
    safe_message: str
    authority_impacting: bool
    external_evidence_required: bool = False
    command_id: PaperExecutionCommandId | None = None
    aggregate_id: PaperExecutionAggregateId | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.criterion, PaperExecutionEligibilityCriterion):
            raise TypeError("criterion must be a PaperExecutionEligibilityCriterion.")
        if not isinstance(self.outcome, PaperExecutionEligibilityCriterionOutcome):
            raise TypeError(
                "outcome must be a PaperExecutionEligibilityCriterionOutcome."
            )
        if not isinstance(self.severity, PaperExecutionEligibilitySeverity):
            raise TypeError("severity must be a PaperExecutionEligibilitySeverity.")
        if not isinstance(self.code, PaperExecutionEligibilityFailureCode):
            raise TypeError("code must be a PaperExecutionEligibilityFailureCode.")
        object.__setattr__(
            self,
            "safe_message",
            normalize_code(self.safe_message, "safe_message"),
        )
        if not isinstance(self.authority_impacting, bool):
            raise TypeError("authority_impacting must be a boolean.")
        if not isinstance(self.external_evidence_required, bool):
            raise TypeError("external_evidence_required must be a boolean.")

    @property
    def passed(self) -> bool:
        return self.outcome is PaperExecutionEligibilityCriterionOutcome.PASS

    def to_primitive(self) -> dict[str, object]:
        return {
            "aggregate_id": self.aggregate_id,
            "authority_impacting": self.authority_impacting,
            "code": self.code,
            "command_id": self.command_id,
            "criterion": self.criterion,
            "external_evidence_required": self.external_evidence_required,
            "outcome": self.outcome,
            "safe_message": self.safe_message,
            "severity": self.severity,
        }


@dataclass(frozen=True, slots=True)
class PaperExecutionEligibilityResult:
    """Advisory result of pure eligibility evaluation."""

    decision: PaperExecutionEligibilityDecision
    command_id: PaperExecutionCommandId
    aggregate_id: PaperExecutionAggregateId
    correlation_id: PaperExecutionCorrelationId
    policy_fingerprint: str
    command_payload_fingerprint: str
    evaluated_at: datetime | None
    criteria: tuple[PaperExecutionEligibilityCriterionResult, ...]
    advisory_only: bool = True
    execution_authorized: bool = False
    action_executed: bool = False
    result_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.decision, PaperExecutionEligibilityDecision):
            raise TypeError("decision must be a PaperExecutionEligibilityDecision.")
        if not isinstance(self.criteria, tuple):
            raise TypeError("criteria must be an immutable tuple.")
        if not all(
            isinstance(item, PaperExecutionEligibilityCriterionResult)
            for item in self.criteria
        ):
            raise TypeError("criteria must contain criterion results.")
        object.__setattr__(
            self,
            "advisory_only",
            True,
        )
        object.__setattr__(self, "execution_authorized", False)
        object.__setattr__(self, "action_executed", False)
        object.__setattr__(
            self,
            "result_fingerprint",
            eligibility_result_fingerprint(self._primitive_without_fingerprint()),
        )

    @property
    def passed_criterion_count(self) -> int:
        return sum(
            item.outcome is PaperExecutionEligibilityCriterionOutcome.PASS
            for item in self.criteria
        )

    @property
    def failed_criterion_count(self) -> int:
        return sum(
            item.outcome is PaperExecutionEligibilityCriterionOutcome.FAIL
            for item in self.criteria
        )

    @property
    def unresolved_criterion_count(self) -> int:
        return sum(
            item.outcome is PaperExecutionEligibilityCriterionOutcome.UNRESOLVED
            for item in self.criteria
        )

    @property
    def eligible(self) -> bool:
        return self.decision is PaperExecutionEligibilityDecision.ELIGIBLE

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "failed_criterion_count": self.failed_criterion_count,
            "passed_criterion_count": self.passed_criterion_count,
            "result_fingerprint": self.result_fingerprint,
            "unresolved_criterion_count": self.unresolved_criterion_count,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "action_executed": self.action_executed,
            "advisory_only": self.advisory_only,
            "aggregate_id": self.aggregate_id,
            "command_id": self.command_id,
            "command_payload_fingerprint": self.command_payload_fingerprint,
            "correlation_id": self.correlation_id,
            "criteria": tuple(item.to_primitive() for item in self.criteria),
            "decision": self.decision,
            "evaluated_at": self.evaluated_at,
            "execution_authorized": self.execution_authorized,
            "policy_fingerprint": self.policy_fingerprint,
        }
