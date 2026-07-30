"""Advisory readiness assessment for Paper qualification shadow validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import TypeAlias

from volcanoes.application.qualification.integration.validation import (
    ShadowValidationRatio,
    ShadowValidationSummary,
)

ReasonCodes: TypeAlias = tuple[str, ...]


class ShadowReadinessDecision(StrEnum):
    """Advisory readiness outcomes for the next engineering phase."""

    READY_FOR_NEXT_PHASE = "READY_FOR_NEXT_PHASE"
    NOT_READY = "NOT_READY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ShadowReadinessCriterionCategory(StrEnum):
    """Stable readiness criterion groups."""

    EVIDENCE = "EVIDENCE"
    DETERMINISM = "DETERMINISM"
    CONTINUITY = "CONTINUITY"
    AUTHORITY = "AUTHORITY"
    EXECUTION_SAFETY = "EXECUTION_SAFETY"
    ENVIRONMENT = "ENVIRONMENT"
    QUALIFICATION_STABILITY = "QUALIFICATION_STABILITY"
    COMPARISON_QUALITY = "COMPARISON_QUALITY"


class ShadowReadinessSeverity(StrEnum):
    """Stable severity for advisory criterion outcomes."""

    BLOCKING = "BLOCKING"
    WARNING = "WARNING"


class ShadowReadinessError(ValueError):
    """Typed safe readiness failure for invalid input contracts."""

    def __init__(self, reason_code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.reason_code = reason_code
        self.safe_message = safe_message

    def __str__(self) -> str:
        return self.safe_message


@dataclass(frozen=True, slots=True)
class ShadowReadinessPolicy:
    """Explicit immutable advisory policy for shadow-readiness assessment."""

    minimum_total_observations: int
    minimum_unique_observations: int
    minimum_repeatable_groups: int
    require_deterministic_replay: bool
    maximum_nondeterministic_replay_count: int
    maximum_conflicting_duplicate_count: int
    maximum_identity_continuity_failure_count: int
    maximum_revision_continuity_failure_count: int
    maximum_transition_continuity_failure_count: int
    maximum_legacy_authority_violation_count: int
    maximum_action_execution_violation_count: int
    maximum_runtime_connected_count: int
    maximum_qualification_error_count: int
    maximum_invalid_input_count: int
    maximum_incomparable_count: int
    maximum_mismatch_count: int
    minimum_match_ratio: ShadowValidationRatio
    maximum_mismatch_ratio: ShadowValidationRatio
    allowed_mismatch_classifications: tuple[str, ...] = ()
    prohibited_mismatch_classifications: tuple[str, ...] = ()
    require_zero_environment_violations: bool = True
    require_zero_unsupported_observations: bool = True
    policy_label: str = "shadow-readiness-policy"

    def __post_init__(self) -> None:
        _validate_policy(self)

    @classmethod
    def strict_validation_policy(cls) -> ShadowReadinessPolicy:
        """Conservative explicit policy for deterministic replay evidence."""

        return cls(
            minimum_total_observations=4,
            minimum_unique_observations=2,
            minimum_repeatable_groups=1,
            require_deterministic_replay=True,
            maximum_nondeterministic_replay_count=0,
            maximum_conflicting_duplicate_count=0,
            maximum_identity_continuity_failure_count=0,
            maximum_revision_continuity_failure_count=0,
            maximum_transition_continuity_failure_count=0,
            maximum_legacy_authority_violation_count=0,
            maximum_action_execution_violation_count=0,
            maximum_runtime_connected_count=0,
            maximum_qualification_error_count=0,
            maximum_invalid_input_count=0,
            maximum_incomparable_count=0,
            maximum_mismatch_count=0,
            minimum_match_ratio=ShadowValidationRatio(1, 1),
            maximum_mismatch_ratio=ShadowValidationRatio(0, 1),
            policy_label="strict-validation-policy",
        )

    @classmethod
    def development_observation_policy(
        cls,
        *,
        allowed_mismatch_classifications: tuple[str, ...] = (),
    ) -> ShadowReadinessPolicy:
        """Lower-sample advisory policy for development observation."""

        return cls(
            minimum_total_observations=1,
            minimum_unique_observations=1,
            minimum_repeatable_groups=0,
            require_deterministic_replay=False,
            maximum_nondeterministic_replay_count=0,
            maximum_conflicting_duplicate_count=0,
            maximum_identity_continuity_failure_count=0,
            maximum_revision_continuity_failure_count=0,
            maximum_transition_continuity_failure_count=0,
            maximum_legacy_authority_violation_count=0,
            maximum_action_execution_violation_count=0,
            maximum_runtime_connected_count=0,
            maximum_qualification_error_count=0,
            maximum_invalid_input_count=0,
            maximum_incomparable_count=0,
            maximum_mismatch_count=(0 if not allowed_mismatch_classifications else 10),
            minimum_match_ratio=ShadowValidationRatio(0, 1),
            maximum_mismatch_ratio=(
                ShadowValidationRatio(0, 1)
                if not allowed_mismatch_classifications
                else ShadowValidationRatio(1, 1)
            ),
            allowed_mismatch_classifications=allowed_mismatch_classifications,
            policy_label="development-observation-policy",
        )

    @property
    def policy_digest(self) -> str:
        return _digest("qrp", _policy_facts(self))


@dataclass(frozen=True, slots=True)
class ShadowReadinessCriterionResult:
    """One immutable criterion outcome."""

    criterion_id: str
    category: ShadowReadinessCriterionCategory
    passed: bool
    reason_code: str
    observed_value: str
    required_value: str
    severity: ShadowReadinessSeverity
    safe_explanation: str


@dataclass(frozen=True, slots=True)
class ShadowReadinessAssessment:
    """Immutable advisory assessment over one F4C validation summary."""

    decision: ShadowReadinessDecision
    policy_fingerprint: str
    validation_summary_fingerprint: str
    assessment_fingerprint: str
    total_criteria: int
    passed_criteria: int
    failed_criteria: int
    evidence_criteria: int
    safety_criteria: int
    quality_criteria: int
    criteria: tuple[ShadowReadinessCriterionResult, ...]
    satisfied_criterion_ids: tuple[str, ...]
    unsatisfied_criterion_ids: tuple[str, ...]
    reason_codes: ReasonCodes
    risks: ReasonCodes
    advisory_only: bool = True
    execution_authorized: bool = False
    runtime_changed: bool = False
    broker_accessed: bool = False
    simulator_accessed: bool = False
    live_authorized: bool = False
    safe_summary: str = "Advisory shadow readiness assessment only."


class ShadowReadinessAssessmentService:
    """Pure advisory assessment service for immutable validation summaries."""

    def assess(
        self,
        summary: ShadowValidationSummary,
        policy: ShadowReadinessPolicy,
    ) -> ShadowReadinessAssessment:
        """Assess one validation summary against one explicit policy."""

        if not isinstance(summary, ShadowValidationSummary):
            raise ShadowReadinessError(
                reason_code="INVALID_READINESS_SUMMARY",
                safe_message="Readiness assessment requires a validation summary.",
            )
        if not isinstance(policy, ShadowReadinessPolicy):
            raise ShadowReadinessError(
                reason_code="INVALID_READINESS_POLICY",
                safe_message="Readiness assessment requires an explicit policy.",
            )

        criteria = tuple(
            sorted(_criteria(summary, policy), key=lambda item: item.criterion_id)
        )
        evidence_failed = tuple(
            item
            for item in criteria
            if not item.passed
            and item.category is ShadowReadinessCriterionCategory.EVIDENCE
        )
        non_evidence_failed = tuple(
            item
            for item in criteria
            if not item.passed
            and item.category is not ShadowReadinessCriterionCategory.EVIDENCE
        )
        if evidence_failed and not non_evidence_failed:
            decision = ShadowReadinessDecision.INSUFFICIENT_EVIDENCE
        elif non_evidence_failed:
            decision = ShadowReadinessDecision.NOT_READY
        elif evidence_failed:
            decision = ShadowReadinessDecision.INSUFFICIENT_EVIDENCE
        else:
            decision = ShadowReadinessDecision.READY_FOR_NEXT_PHASE

        satisfied = tuple(item.criterion_id for item in criteria if item.passed)
        unsatisfied = tuple(item.criterion_id for item in criteria if not item.passed)
        reason_codes = tuple(
            sorted(item.reason_code for item in criteria if not item.passed)
        )
        risks = tuple(sorted(set(reason_codes)))
        fingerprint = _digest(
            "qra",
            (
                decision.value,
                policy.policy_digest,
                summary.summary_fingerprint,
                ",".join(satisfied),
                ",".join(unsatisfied),
                ",".join(reason_codes),
            ),
        )
        return ShadowReadinessAssessment(
            decision=decision,
            policy_fingerprint=policy.policy_digest,
            validation_summary_fingerprint=summary.summary_fingerprint,
            assessment_fingerprint=fingerprint,
            total_criteria=len(criteria),
            passed_criteria=len(satisfied),
            failed_criteria=len(unsatisfied),
            evidence_criteria=sum(
                1
                for item in criteria
                if item.category is ShadowReadinessCriterionCategory.EVIDENCE
            ),
            safety_criteria=sum(
                1
                for item in criteria
                if item.category
                in {
                    ShadowReadinessCriterionCategory.DETERMINISM,
                    ShadowReadinessCriterionCategory.CONTINUITY,
                    ShadowReadinessCriterionCategory.AUTHORITY,
                    ShadowReadinessCriterionCategory.EXECUTION_SAFETY,
                    ShadowReadinessCriterionCategory.ENVIRONMENT,
                }
            ),
            quality_criteria=sum(
                1
                for item in criteria
                if item.category
                in {
                    ShadowReadinessCriterionCategory.QUALIFICATION_STABILITY,
                    ShadowReadinessCriterionCategory.COMPARISON_QUALITY,
                }
            ),
            criteria=criteria,
            satisfied_criterion_ids=satisfied,
            unsatisfied_criterion_ids=unsatisfied,
            reason_codes=reason_codes,
            risks=risks,
            advisory_only=True,
            execution_authorized=False,
            runtime_changed=False,
            broker_accessed=False,
            simulator_accessed=False,
            live_authorized=False,
            safe_summary=(
                "Shadow validation evidence satisfies the supplied advisory policy."
                if decision is ShadowReadinessDecision.READY_FOR_NEXT_PHASE
                else "Shadow validation evidence does not satisfy the supplied advisory policy."
            ),
        )


def _criteria(
    summary: ShadowValidationSummary,
    policy: ShadowReadinessPolicy,
) -> tuple[ShadowReadinessCriterionResult, ...]:
    mismatch_counts = dict(summary.mismatch_classification_counts)
    prohibited_present = tuple(
        item
        for item in policy.prohibited_mismatch_classifications
        if mismatch_counts.get(item, 0) > 0
    )
    unallowed_present = tuple(
        item
        for item, count in mismatch_counts.items()
        if count > 0 and item not in policy.allowed_mismatch_classifications
    )
    return (
        _minimum(
            "evidence.total_observations",
            ShadowReadinessCriterionCategory.EVIDENCE,
            summary.total_observations,
            policy.minimum_total_observations,
            "READINESS_MINIMUM_TOTAL_OBSERVATIONS_NOT_MET",
        ),
        _minimum(
            "evidence.unique_observations",
            ShadowReadinessCriterionCategory.EVIDENCE,
            summary.unique_observations,
            policy.minimum_unique_observations,
            "READINESS_MINIMUM_UNIQUE_OBSERVATIONS_NOT_MET",
        ),
        _minimum(
            "evidence.repeatable_groups",
            ShadowReadinessCriterionCategory.EVIDENCE,
            summary.repeatable_observation_groups,
            policy.minimum_repeatable_groups,
            "READINESS_MINIMUM_REPEATABLE_GROUPS_NOT_MET",
        ),
        _boolean(
            "evidence.deterministic_replay_required",
            ShadowReadinessCriterionCategory.EVIDENCE,
            not policy.require_deterministic_replay
            or summary.deterministic_replay_count > 0,
            str(summary.deterministic_replay_count),
            ">=1" if policy.require_deterministic_replay else "not required",
            "READINESS_DETERMINISTIC_REPLAY_REQUIRED",
        ),
        _maximum(
            "determinism.nondeterministic_replay",
            ShadowReadinessCriterionCategory.DETERMINISM,
            summary.nondeterministic_replay_count,
            policy.maximum_nondeterministic_replay_count,
            "READINESS_NONDETERMINISTIC_REPLAY_LIMIT_EXCEEDED",
        ),
        _maximum(
            "determinism.conflicting_duplicates",
            ShadowReadinessCriterionCategory.DETERMINISM,
            summary.conflicting_duplicates,
            policy.maximum_conflicting_duplicate_count,
            "READINESS_CONFLICTING_DUPLICATE_LIMIT_EXCEEDED",
        ),
        _maximum(
            "continuity.identity",
            ShadowReadinessCriterionCategory.CONTINUITY,
            summary.identity_continuity_failure_count,
            policy.maximum_identity_continuity_failure_count,
            "READINESS_IDENTITY_CONTINUITY_FAILURE_LIMIT_EXCEEDED",
        ),
        _maximum(
            "continuity.revision",
            ShadowReadinessCriterionCategory.CONTINUITY,
            summary.revision_continuity_failure_count,
            policy.maximum_revision_continuity_failure_count,
            "READINESS_REVISION_CONTINUITY_FAILURE_LIMIT_EXCEEDED",
        ),
        _maximum(
            "continuity.transition",
            ShadowReadinessCriterionCategory.CONTINUITY,
            summary.transition_continuity_failure_count,
            policy.maximum_transition_continuity_failure_count,
            "READINESS_TRANSITION_CONTINUITY_FAILURE_LIMIT_EXCEEDED",
        ),
        _maximum(
            "authority.legacy_authority",
            ShadowReadinessCriterionCategory.AUTHORITY,
            summary.legacy_authority_violation_count,
            policy.maximum_legacy_authority_violation_count,
            "READINESS_LEGACY_AUTHORITY_VIOLATION_LIMIT_EXCEEDED",
        ),
        _maximum(
            "authority.legacy_behavior_changed",
            ShadowReadinessCriterionCategory.AUTHORITY,
            summary.legacy_behavior_changed_count,
            policy.maximum_legacy_authority_violation_count,
            "READINESS_LEGACY_BEHAVIOR_CHANGED_LIMIT_EXCEEDED",
        ),
        _maximum(
            "execution.action_executed",
            ShadowReadinessCriterionCategory.EXECUTION_SAFETY,
            summary.action_executed_count,
            policy.maximum_action_execution_violation_count,
            "READINESS_ACTION_EXECUTION_LIMIT_EXCEEDED",
        ),
        _maximum(
            "execution.runtime_connected",
            ShadowReadinessCriterionCategory.EXECUTION_SAFETY,
            summary.runtime_connected_count,
            policy.maximum_runtime_connected_count,
            "READINESS_RUNTIME_CONNECTED_LIMIT_EXCEEDED",
        ),
        _maximum(
            "environment.violations",
            ShadowReadinessCriterionCategory.ENVIRONMENT,
            summary.environment_violation_count,
            (
                0
                if policy.require_zero_environment_violations
                else summary.environment_violation_count
            ),
            "READINESS_ENVIRONMENT_VIOLATION_PRESENT",
        ),
        _maximum(
            "stability.qualification_errors",
            ShadowReadinessCriterionCategory.QUALIFICATION_STABILITY,
            summary.qualification_error_count,
            policy.maximum_qualification_error_count,
            "READINESS_QUALIFICATION_ERROR_LIMIT_EXCEEDED",
        ),
        _maximum(
            "stability.invalid_inputs",
            ShadowReadinessCriterionCategory.QUALIFICATION_STABILITY,
            summary.invalid_input_count,
            policy.maximum_invalid_input_count,
            "READINESS_INVALID_INPUT_LIMIT_EXCEEDED",
        ),
        _maximum(
            "stability.incomparable",
            ShadowReadinessCriterionCategory.QUALIFICATION_STABILITY,
            summary.incomparable_count,
            policy.maximum_incomparable_count,
            "READINESS_INCOMPARABLE_LIMIT_EXCEEDED",
        ),
        _maximum(
            "comparison.mismatch_count",
            ShadowReadinessCriterionCategory.COMPARISON_QUALITY,
            summary.mismatch_count,
            policy.maximum_mismatch_count,
            "READINESS_MISMATCH_LIMIT_EXCEEDED",
        ),
        _ratio_minimum(
            "comparison.match_ratio",
            summary.match_ratio,
            policy.minimum_match_ratio,
            "READINESS_MATCH_RATIO_TOO_LOW",
        ),
        _ratio_maximum(
            "comparison.mismatch_ratio",
            summary.mismatch_ratio,
            policy.maximum_mismatch_ratio,
            "READINESS_MISMATCH_RATIO_TOO_HIGH",
        ),
        _boolean(
            "comparison.prohibited_mismatches",
            ShadowReadinessCriterionCategory.COMPARISON_QUALITY,
            not prohibited_present,
            ",".join(prohibited_present),
            "none",
            "READINESS_PROHIBITED_MISMATCH_PRESENT",
        ),
        _boolean(
            "comparison.unallowed_mismatches",
            ShadowReadinessCriterionCategory.COMPARISON_QUALITY,
            not unallowed_present,
            ",".join(unallowed_present),
            "none",
            "READINESS_UNALLOWED_MISMATCH_PRESENT",
        ),
        _maximum(
            "stability.unsupported_observations",
            ShadowReadinessCriterionCategory.QUALIFICATION_STABILITY,
            summary.safely_rejected_count,
            (
                0
                if policy.require_zero_unsupported_observations
                else summary.safely_rejected_count
            ),
            "READINESS_UNSUPPORTED_OBSERVATION_PRESENT",
        ),
    )


def _minimum(
    criterion_id: str,
    category: ShadowReadinessCriterionCategory,
    observed: int,
    required: int,
    reason_code: str,
) -> ShadowReadinessCriterionResult:
    return _criterion(
        criterion_id,
        category,
        observed >= required,
        reason_code,
        str(observed),
        f">={required}",
    )


def _maximum(
    criterion_id: str,
    category: ShadowReadinessCriterionCategory,
    observed: int,
    required: int,
    reason_code: str,
) -> ShadowReadinessCriterionResult:
    return _criterion(
        criterion_id,
        category,
        observed <= required,
        reason_code,
        str(observed),
        f"<={required}",
    )


def _ratio_minimum(
    criterion_id: str,
    observed: ShadowValidationRatio,
    required: ShadowValidationRatio,
    reason_code: str,
) -> ShadowReadinessCriterionResult:
    passed = observed.denominator == 0 or _ratio_gte(observed, required)
    return _criterion(
        criterion_id,
        ShadowReadinessCriterionCategory.COMPARISON_QUALITY,
        passed,
        reason_code,
        _ratio_text(observed),
        f">={_ratio_text(required)}",
    )


def _ratio_maximum(
    criterion_id: str,
    observed: ShadowValidationRatio,
    required: ShadowValidationRatio,
    reason_code: str,
) -> ShadowReadinessCriterionResult:
    passed = observed.denominator == 0 or _ratio_lte(observed, required)
    return _criterion(
        criterion_id,
        ShadowReadinessCriterionCategory.COMPARISON_QUALITY,
        passed,
        reason_code,
        _ratio_text(observed),
        f"<={_ratio_text(required)}",
    )


def _boolean(
    criterion_id: str,
    category: ShadowReadinessCriterionCategory,
    passed: bool,
    observed: str,
    required: str,
    reason_code: str,
) -> ShadowReadinessCriterionResult:
    return _criterion(
        criterion_id,
        category,
        passed,
        reason_code,
        observed,
        required,
    )


def _criterion(
    criterion_id: str,
    category: ShadowReadinessCriterionCategory,
    passed: bool,
    reason_code: str,
    observed: str,
    required: str,
) -> ShadowReadinessCriterionResult:
    return ShadowReadinessCriterionResult(
        criterion_id=criterion_id,
        category=category,
        passed=passed,
        reason_code="READINESS_CRITERION_SATISFIED" if passed else reason_code,
        observed_value=observed,
        required_value=required,
        severity=ShadowReadinessSeverity.BLOCKING,
        safe_explanation=(
            "Criterion satisfied."
            if passed
            else "Advisory readiness criterion is not satisfied."
        ),
    )


def _validate_policy(policy: ShadowReadinessPolicy) -> None:
    count_fields = (
        "minimum_total_observations",
        "minimum_unique_observations",
        "minimum_repeatable_groups",
        "maximum_nondeterministic_replay_count",
        "maximum_conflicting_duplicate_count",
        "maximum_identity_continuity_failure_count",
        "maximum_revision_continuity_failure_count",
        "maximum_transition_continuity_failure_count",
        "maximum_legacy_authority_violation_count",
        "maximum_action_execution_violation_count",
        "maximum_runtime_connected_count",
        "maximum_qualification_error_count",
        "maximum_invalid_input_count",
        "maximum_incomparable_count",
        "maximum_mismatch_count",
    )
    for field in count_fields:
        value = getattr(policy, field)
        if not isinstance(value, int) or value < 0:
            raise ShadowReadinessError(
                reason_code="INVALID_READINESS_POLICY_COUNT",
                safe_message="Readiness policy count is invalid.",
            )
    _validate_ratio(policy.minimum_match_ratio)
    _validate_ratio(policy.maximum_mismatch_ratio)
    allowed = set(policy.allowed_mismatch_classifications)
    prohibited = set(policy.prohibited_mismatch_classifications)
    if allowed & prohibited:
        raise ShadowReadinessError(
            reason_code="CONTRADICTORY_MISMATCH_POLICY",
            safe_message="Readiness mismatch policy is contradictory.",
        )
    for value in (*allowed, *prohibited, policy.policy_label):
        _safe_text(value)


def _validate_ratio(ratio: ShadowValidationRatio) -> None:
    if not isinstance(ratio, ShadowValidationRatio):
        raise ShadowReadinessError(
            reason_code="INVALID_READINESS_POLICY_RATIO",
            safe_message="Readiness policy ratio is invalid.",
        )
    if ratio.denominator <= 0 or ratio.numerator < 0:
        raise ShadowReadinessError(
            reason_code="INVALID_READINESS_POLICY_RATIO",
            safe_message="Readiness policy ratio is invalid.",
        )
    if ratio.numerator > ratio.denominator:
        raise ShadowReadinessError(
            reason_code="INVALID_READINESS_POLICY_RATIO",
            safe_message="Readiness policy ratio is invalid.",
        )


def _ratio_gte(left: ShadowValidationRatio, right: ShadowValidationRatio) -> bool:
    return left.numerator * right.denominator >= right.numerator * left.denominator


def _ratio_lte(left: ShadowValidationRatio, right: ShadowValidationRatio) -> bool:
    return left.numerator * right.denominator <= right.numerator * left.denominator


def _ratio_text(ratio: ShadowValidationRatio) -> str:
    return f"{ratio.numerator}/{ratio.denominator}"


def _policy_facts(policy: ShadowReadinessPolicy) -> tuple[str, ...]:
    return (
        policy.policy_label,
        str(policy.minimum_total_observations),
        str(policy.minimum_unique_observations),
        str(policy.minimum_repeatable_groups),
        str(policy.require_deterministic_replay),
        str(policy.maximum_nondeterministic_replay_count),
        str(policy.maximum_conflicting_duplicate_count),
        str(policy.maximum_identity_continuity_failure_count),
        str(policy.maximum_revision_continuity_failure_count),
        str(policy.maximum_transition_continuity_failure_count),
        str(policy.maximum_legacy_authority_violation_count),
        str(policy.maximum_action_execution_violation_count),
        str(policy.maximum_runtime_connected_count),
        str(policy.maximum_qualification_error_count),
        str(policy.maximum_invalid_input_count),
        str(policy.maximum_incomparable_count),
        str(policy.maximum_mismatch_count),
        _ratio_text(policy.minimum_match_ratio),
        _ratio_text(policy.maximum_mismatch_ratio),
        ",".join(sorted(policy.allowed_mismatch_classifications)),
        ",".join(sorted(policy.prohibited_mismatch_classifications)),
        str(policy.require_zero_environment_violations),
        str(policy.require_zero_unsupported_observations),
    )


def _digest(prefix: str, facts: tuple[str, ...]) -> str:
    payload = "\x1f".join(_safe_text(fact) for fact in facts)
    return f"{prefix}-{sha256(payload.encode('utf-8')).hexdigest()}"


def _safe_text(value: object) -> str:
    text = "" if value is None else str(value)
    lowered = text.lower()
    unsafe = (
        "sentinel_f4d_secret_do_not_expose",
        "sentinel_f4d_token_do_not_expose",
        "sentinel_f4d_password_do_not_expose",
        "api_key",
        "secret",
        "token",
        "password",
    )
    if any(marker in lowered for marker in unsafe):
        return "REDACTED"
    return text


__all__ = [
    "ShadowReadinessAssessment",
    "ShadowReadinessAssessmentService",
    "ShadowReadinessCriterionCategory",
    "ShadowReadinessCriterionResult",
    "ShadowReadinessDecision",
    "ShadowReadinessError",
    "ShadowReadinessPolicy",
    "ShadowReadinessSeverity",
]
