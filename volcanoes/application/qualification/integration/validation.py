"""In-memory validation harness for Paper qualification shadow observations."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import TypeAlias

from volcanoes.application.qualification.integration.boundary import (
    QualificationRuntimeBoundaryResult,
)
from volcanoes.application.qualification.integration.contracts import (
    PaperIntegrationEnvironment,
    normalize_metadata,
    normalize_optional_decimal,
    normalize_symbol,
    normalize_timestamp,
    require_paper_environment,
    validate_identifier,
    validate_non_negative_int,
    validate_positive_int,
)
from volcanoes.application.qualification.integration.shadow import (
    ShadowComparisonStatus,
    ShadowMismatchClassification,
)

CountPairs: TypeAlias = tuple[tuple[str, int], ...]
SafeContext: TypeAlias = tuple[tuple[str, str], ...]

_EMPTY_RATIO_DENOMINATOR = 0


class ShadowValidationClassification(StrEnum):
    """Stable categories for one completed boundary observation."""

    MATCH = "MATCH"
    MATCH_WITH_NONCONSEQUENTIAL_DIFFERENCE = "MATCH_WITH_NONCONSEQUENTIAL_DIFFERENCE"
    MISMATCH = "MISMATCH"
    INCOMPARABLE = "INCOMPARABLE"
    QUALIFICATION_ERROR = "QUALIFICATION_ERROR"
    INVALID_SHADOW_INPUT = "INVALID_SHADOW_INPUT"


class ShadowValidationConflictType(StrEnum):
    """Safe conflict categories emitted by the validation harness."""

    DUPLICATE_IDENTITY_CONFLICT = "DUPLICATE_IDENTITY_CONFLICT"
    COMPARISON_STATUS_DRIFT = "COMPARISON_STATUS_DRIFT"
    MISMATCH_CLASSIFICATION_DRIFT = "MISMATCH_CLASSIFICATION_DRIFT"
    REVISION_DRIFT = "REVISION_DRIFT"
    TRANSITION_DRIFT = "TRANSITION_DRIFT"
    IDENTITY_CONTINUITY_FAILURE = "IDENTITY_CONTINUITY_FAILURE"
    REVISION_CONTINUITY_FAILURE = "REVISION_CONTINUITY_FAILURE"
    TRANSITION_CONTINUITY_FAILURE = "TRANSITION_CONTINUITY_FAILURE"
    LEGACY_AUTHORITY_VIOLATION = "LEGACY_AUTHORITY_VIOLATION"
    ACTION_EXECUTION_VIOLATION = "ACTION_EXECUTION_VIOLATION"
    ENVIRONMENT_VIOLATION = "ENVIRONMENT_VIOLATION"
    RUNTIME_CONNECTION_VIOLATION = "RUNTIME_CONNECTION_VIOLATION"
    UNSUPPORTED_OBSERVATION = "UNSUPPORTED_OBSERVATION"


class ShadowValidationError(ValueError):
    """Typed safe validation failure for unsupported harness input."""

    def __init__(self, reason_code: str, safe_message: str) -> None:
        super().__init__(safe_message)
        self.reason_code = reason_code
        self.safe_message = safe_message

    def __str__(self) -> str:
        return self.safe_message


@dataclass(frozen=True, slots=True)
class ShadowValidationRatio:
    """Exact deterministic ratio with a defined empty denominator."""

    numerator: int
    denominator: int


@dataclass(frozen=True, slots=True)
class ShadowValidationConflict:
    """One immutable safe validation conflict."""

    conflict_type: ShadowValidationConflictType
    observation_id: str
    existing_fingerprint: str | None = None
    incoming_fingerprint: str | None = None
    safe_context: SafeContext = ()


@dataclass(frozen=True, slots=True)
class ShadowValidationObservation:
    """Immutable validation view derived from one boundary result."""

    observation_id: str
    observation_fingerprint: str
    classification: ShadowValidationClassification
    boundary_invocation_id: str
    shadow_invocation_id: str
    runtime_request_id: str
    qualification_run_id: str
    command_id: str
    correlation_id: str
    idempotency_key: str
    comparison_status: ShadowComparisonStatus | None
    mismatch_classifications: tuple[ShadowMismatchClassification, ...]
    expected_revision: int
    previous_revision: int
    next_revision: int | None
    transition_id: str | None
    action_executed: bool
    legacy_behavior_authoritative: bool
    legacy_behavior_changed: bool
    runtime_connected: bool
    conflicts: tuple[ShadowValidationConflict, ...] = ()


@dataclass(frozen=True, slots=True)
class ShadowValidationSummary:
    """Immutable deterministic aggregate of recorded shadow observations."""

    total_observations: int
    unique_observations: int
    duplicate_observations: int
    conflicting_duplicates: int
    match_count: int
    nonconsequential_difference_count: int
    mismatch_count: int
    incomparable_count: int
    qualification_error_count: int
    invalid_input_count: int
    status_counts: CountPairs
    mismatch_classification_counts: CountPairs
    repeatable_observation_groups: int
    nonrepeatable_observation_groups: int
    identity_continuity_failure_count: int
    revision_continuity_failure_count: int
    transition_continuity_failure_count: int
    deterministic_replay_count: int
    nondeterministic_replay_count: int
    safely_rejected_count: int
    action_executed_count: int
    legacy_authority_violation_count: int
    legacy_behavior_changed_count: int
    runtime_connected_count: int
    environment_violation_count: int
    validation_conflicts: tuple[ShadowValidationConflict, ...]
    match_ratio: ShadowValidationRatio
    mismatch_ratio: ShadowValidationRatio
    qualification_error_ratio: ShadowValidationRatio
    invalid_input_ratio: ShadowValidationRatio
    summary_fingerprint: str


class ShadowObservationValidationHarness:
    """Deterministic in-memory accumulator for completed boundary results."""

    def __init__(self) -> None:
        self._observations: list[ShadowValidationObservation] = []

    def record(
        self,
        result: QualificationRuntimeBoundaryResult,
    ) -> ShadowValidationObservation:
        """Record one completed boundary result without controlling runtime."""

        observation = _observation_from_result(result)
        prior = tuple(
            item
            for item in self._observations
            if item.observation_id == observation.observation_id
        )
        conflicts = _conflicts_for_duplicate(observation, prior)
        if conflicts:
            observation = _with_conflicts(observation, conflicts)
        self._observations.append(observation)
        return observation

    def summarize(self) -> ShadowValidationSummary:
        """Return an immutable deterministic summary of received observations."""

        return _summary_for(tuple(self._observations))


def _observation_from_result(
    result: QualificationRuntimeBoundaryResult,
) -> ShadowValidationObservation:
    if not isinstance(result, QualificationRuntimeBoundaryResult):
        raise ShadowValidationError(
            reason_code="INVALID_SHADOW_VALIDATION_INPUT",
            safe_message="Shadow validation accepts boundary results only.",
        )

    shadow = result.shadow_result
    mismatches = tuple(
        sorted(result.mismatch_classifications, key=lambda item: item.value)
    )
    classification = _classification_for(result.comparison_status)
    facts = (
        _text(result.boundary_invocation_id),
        _text(shadow.shadow_invocation_id),
        _text(result.runtime_request_id),
        _text(result.qualification_run_id),
        _text(result.command_id),
        _text(result.correlation_id),
        _text(result.idempotency_key),
        _text(result.expected_revision),
    )
    observation_id = _digest("qiv", facts)
    conflicts = _continuity_conflicts(result, observation_id)
    if conflicts:
        classification = ShadowValidationClassification.INVALID_SHADOW_INPUT
    fingerprint = _fingerprint_for(result, classification, mismatches)
    return ShadowValidationObservation(
        observation_id=observation_id,
        observation_fingerprint=fingerprint,
        classification=classification,
        boundary_invocation_id=_text(result.boundary_invocation_id),
        shadow_invocation_id=_text(shadow.shadow_invocation_id),
        runtime_request_id=_text(result.runtime_request_id),
        qualification_run_id=_text(result.qualification_run_id),
        command_id=_text(result.command_id),
        correlation_id=_text(result.correlation_id),
        idempotency_key=_text(result.idempotency_key),
        comparison_status=result.comparison_status,
        mismatch_classifications=mismatches,
        expected_revision=int(result.expected_revision),
        previous_revision=int(result.previous_revision),
        next_revision=(
            None if result.next_revision is None else int(result.next_revision)
        ),
        transition_id=result.transition_id,
        action_executed=bool(result.action_executed),
        legacy_behavior_authoritative=bool(result.legacy_behavior_authoritative),
        legacy_behavior_changed=bool(result.legacy_behavior_changed),
        runtime_connected=bool(result.runtime_connected),
        conflicts=conflicts,
    )


def _classification_for(
    status: object,
) -> ShadowValidationClassification:
    if status is ShadowComparisonStatus.MATCH:
        return ShadowValidationClassification.MATCH
    if status is ShadowComparisonStatus.MATCH_WITH_NONCONSEQUENTIAL_DIFFERENCE:
        return ShadowValidationClassification.MATCH_WITH_NONCONSEQUENTIAL_DIFFERENCE
    if status is ShadowComparisonStatus.MISMATCH:
        return ShadowValidationClassification.MISMATCH
    if status is ShadowComparisonStatus.INCOMPARABLE:
        return ShadowValidationClassification.INCOMPARABLE
    if status is ShadowComparisonStatus.QUALIFICATION_ERROR:
        return ShadowValidationClassification.QUALIFICATION_ERROR
    return ShadowValidationClassification.INVALID_SHADOW_INPUT


def _continuity_conflicts(
    result: QualificationRuntimeBoundaryResult,
    observation_id: str,
) -> tuple[ShadowValidationConflict, ...]:
    shadow = result.shadow_result
    conflicts: list[ShadowValidationConflict] = []
    missing_fields = tuple(
        name
        for name, value in (
            ("boundary_invocation_id", result.boundary_invocation_id),
            ("shadow_invocation_id", shadow.shadow_invocation_id),
            ("runtime_request_id", result.runtime_request_id),
            ("qualification_run_id", result.qualification_run_id),
            ("command_id", result.command_id),
            ("correlation_id", result.correlation_id),
            ("idempotency_key", result.idempotency_key),
        )
        if not _text(value).strip()
    )
    if missing_fields:
        conflicts.append(
            _conflict(
                ShadowValidationConflictType.IDENTITY_CONTINUITY_FAILURE,
                observation_id,
                ("fields", ",".join(sorted(missing_fields))),
            )
        )
    identity_mismatches = tuple(
        name
        for name, left, right in (
            (
                "qualification_run_id",
                result.qualification_run_id,
                shadow.qualification_run_id,
            ),
            ("command_id", result.command_id, shadow.command_id),
            ("correlation_id", result.correlation_id, shadow.correlation_id),
            ("idempotency_key", result.idempotency_key, shadow.idempotency_key),
            (
                "runtime_request_id",
                result.runtime_request_id,
                shadow.legacy_decision.runtime_request_id,
            ),
        )
        if _text(left) != _text(right)
    )
    if identity_mismatches:
        conflicts.append(
            _conflict(
                ShadowValidationConflictType.IDENTITY_CONTINUITY_FAILURE,
                observation_id,
                ("fields", ",".join(sorted(identity_mismatches))),
            )
        )
    if shadow.legacy_decision.environment is not PaperIntegrationEnvironment.PAPER:
        conflicts.append(
            _conflict(
                ShadowValidationConflictType.ENVIRONMENT_VIOLATION,
                observation_id,
                ("environment", _text(shadow.legacy_decision.environment)),
            )
        )
    if result.previous_revision != result.expected_revision:
        conflicts.append(
            _conflict(
                ShadowValidationConflictType.REVISION_CONTINUITY_FAILURE,
                observation_id,
                ("field", "previous_revision"),
            )
        )
    if (
        result.next_revision is not None
        and result.next_revision < result.previous_revision
    ):
        conflicts.append(
            _conflict(
                ShadowValidationConflictType.REVISION_CONTINUITY_FAILURE,
                observation_id,
                ("field", "next_revision"),
            )
        )
    if result.transition_id != shadow.transition_id:
        conflicts.append(
            _conflict(
                ShadowValidationConflictType.TRANSITION_CONTINUITY_FAILURE,
                observation_id,
                ("field", "transition_id"),
            )
        )
    if result.action_executed is not False:
        conflicts.append(
            _conflict(
                ShadowValidationConflictType.ACTION_EXECUTION_VIOLATION,
                observation_id,
                ("field", "action_executed"),
            )
        )
    if result.legacy_behavior_authoritative is not True:
        conflicts.append(
            _conflict(
                ShadowValidationConflictType.LEGACY_AUTHORITY_VIOLATION,
                observation_id,
                ("field", "legacy_behavior_authoritative"),
            )
        )
    if result.legacy_behavior_changed is not False:
        conflicts.append(
            _conflict(
                ShadowValidationConflictType.LEGACY_AUTHORITY_VIOLATION,
                observation_id,
                ("field", "legacy_behavior_changed"),
            )
        )
    if result.runtime_connected is not False:
        conflicts.append(
            _conflict(
                ShadowValidationConflictType.RUNTIME_CONNECTION_VIOLATION,
                observation_id,
                ("field", "runtime_connected"),
            )
        )
    return tuple(conflicts)


def _conflicts_for_duplicate(
    observation: ShadowValidationObservation,
    prior: tuple[ShadowValidationObservation, ...],
) -> tuple[ShadowValidationConflict, ...]:
    fingerprints = {item.observation_fingerprint for item in prior}
    if not fingerprints or observation.observation_fingerprint in fingerprints:
        return ()

    conflicts = [
        ShadowValidationConflict(
            conflict_type=ShadowValidationConflictType.DUPLICATE_IDENTITY_CONFLICT,
            observation_id=observation.observation_id,
            existing_fingerprint=sorted(fingerprints)[0],
            incoming_fingerprint=observation.observation_fingerprint,
            safe_context=(("field", "observation_fingerprint"),),
        )
    ]
    for item in prior:
        conflicts.extend(_drift_conflicts(item, observation))
    return tuple(sorted(conflicts, key=_conflict_sort_key))


def _drift_conflicts(
    existing: ShadowValidationObservation,
    incoming: ShadowValidationObservation,
) -> tuple[ShadowValidationConflict, ...]:
    conflicts: list[ShadowValidationConflict] = []
    if existing.comparison_status != incoming.comparison_status:
        conflicts.append(
            _conflict(
                ShadowValidationConflictType.COMPARISON_STATUS_DRIFT,
                incoming.observation_id,
                ("field", "comparison_status"),
                existing.observation_fingerprint,
                incoming.observation_fingerprint,
            )
        )
    if existing.mismatch_classifications != incoming.mismatch_classifications:
        conflicts.append(
            _conflict(
                ShadowValidationConflictType.MISMATCH_CLASSIFICATION_DRIFT,
                incoming.observation_id,
                ("field", "mismatch_classifications"),
                existing.observation_fingerprint,
                incoming.observation_fingerprint,
            )
        )
    if (
        existing.expected_revision,
        existing.previous_revision,
        existing.next_revision,
    ) != (
        incoming.expected_revision,
        incoming.previous_revision,
        incoming.next_revision,
    ):
        conflicts.append(
            _conflict(
                ShadowValidationConflictType.REVISION_DRIFT,
                incoming.observation_id,
                ("field", "revision"),
                existing.observation_fingerprint,
                incoming.observation_fingerprint,
            )
        )
    if existing.transition_id != incoming.transition_id:
        conflicts.append(
            _conflict(
                ShadowValidationConflictType.TRANSITION_DRIFT,
                incoming.observation_id,
                ("field", "transition_id"),
                existing.observation_fingerprint,
                incoming.observation_fingerprint,
            )
        )
    return tuple(conflicts)


def _summary_for(
    observations: tuple[ShadowValidationObservation, ...],
) -> ShadowValidationSummary:
    status_counts = Counter(item.classification.value for item in observations)
    mismatch_counts = Counter(
        classification.value
        for item in observations
        for classification in item.mismatch_classifications
    )
    groups: dict[str, list[ShadowValidationObservation]] = defaultdict(list)
    for observation in observations:
        groups[observation.observation_id].append(observation)

    duplicate_count = sum(
        len(items) - len({item.observation_fingerprint for item in items})
        for items in groups.values()
    )
    conflict_count = sum(
        1
        for items in groups.values()
        if len({item.observation_fingerprint for item in items}) > 1
    )
    repeatable_groups = sum(
        1
        for items in groups.values()
        if len(items) > 1 and len({item.observation_fingerprint for item in items}) == 1
    )
    nonrepeatable_groups = sum(
        1
        for items in groups.values()
        if len(items) > 1 and len({item.observation_fingerprint for item in items}) > 1
    )
    conflicts = tuple(
        sorted(
            (conflict for item in observations for conflict in item.conflicts),
            key=_conflict_sort_key,
        )
    )
    total = len(observations)
    summary_without_fingerprint = (
        str(total),
        str(len(groups)),
        str(duplicate_count),
        str(conflict_count),
        _pairs_text(status_counts),
        _pairs_text(mismatch_counts),
        _conflicts_text(conflicts),
        _group_text(groups),
    )
    fingerprint = _digest("qvs", summary_without_fingerprint)
    return ShadowValidationSummary(
        total_observations=total,
        unique_observations=len(groups),
        duplicate_observations=duplicate_count,
        conflicting_duplicates=conflict_count,
        match_count=status_counts[ShadowValidationClassification.MATCH.value],
        nonconsequential_difference_count=status_counts[
            ShadowValidationClassification.MATCH_WITH_NONCONSEQUENTIAL_DIFFERENCE.value
        ],
        mismatch_count=status_counts[ShadowValidationClassification.MISMATCH.value],
        incomparable_count=status_counts[
            ShadowValidationClassification.INCOMPARABLE.value
        ],
        qualification_error_count=status_counts[
            ShadowValidationClassification.QUALIFICATION_ERROR.value
        ],
        invalid_input_count=status_counts[
            ShadowValidationClassification.INVALID_SHADOW_INPUT.value
        ],
        status_counts=_counter_pairs(status_counts),
        mismatch_classification_counts=_counter_pairs(mismatch_counts),
        repeatable_observation_groups=repeatable_groups,
        nonrepeatable_observation_groups=nonrepeatable_groups,
        identity_continuity_failure_count=_conflict_count(
            conflicts,
            ShadowValidationConflictType.IDENTITY_CONTINUITY_FAILURE,
        ),
        revision_continuity_failure_count=_conflict_count(
            conflicts,
            ShadowValidationConflictType.REVISION_CONTINUITY_FAILURE,
        ),
        transition_continuity_failure_count=_conflict_count(
            conflicts,
            ShadowValidationConflictType.TRANSITION_CONTINUITY_FAILURE,
        ),
        deterministic_replay_count=duplicate_count,
        nondeterministic_replay_count=conflict_count,
        safely_rejected_count=status_counts[
            ShadowValidationClassification.INVALID_SHADOW_INPUT.value
        ],
        action_executed_count=_conflict_count(
            conflicts,
            ShadowValidationConflictType.ACTION_EXECUTION_VIOLATION,
        ),
        legacy_authority_violation_count=_conflict_count(
            conflicts,
            ShadowValidationConflictType.LEGACY_AUTHORITY_VIOLATION,
        ),
        legacy_behavior_changed_count=sum(
            1 for item in observations if item.legacy_behavior_changed
        ),
        runtime_connected_count=sum(
            1 for item in observations if item.runtime_connected
        ),
        environment_violation_count=_conflict_count(
            conflicts,
            ShadowValidationConflictType.ENVIRONMENT_VIOLATION,
        ),
        validation_conflicts=conflicts,
        match_ratio=ShadowValidationRatio(
            status_counts[ShadowValidationClassification.MATCH.value],
            total or _EMPTY_RATIO_DENOMINATOR,
        ),
        mismatch_ratio=ShadowValidationRatio(
            status_counts[ShadowValidationClassification.MISMATCH.value],
            total or _EMPTY_RATIO_DENOMINATOR,
        ),
        qualification_error_ratio=ShadowValidationRatio(
            status_counts[ShadowValidationClassification.QUALIFICATION_ERROR.value],
            total or _EMPTY_RATIO_DENOMINATOR,
        ),
        invalid_input_ratio=ShadowValidationRatio(
            status_counts[ShadowValidationClassification.INVALID_SHADOW_INPUT.value],
            total or _EMPTY_RATIO_DENOMINATOR,
        ),
        summary_fingerprint=fingerprint,
    )


def _with_conflicts(
    observation: ShadowValidationObservation,
    conflicts: tuple[ShadowValidationConflict, ...],
) -> ShadowValidationObservation:
    return ShadowValidationObservation(
        observation_id=observation.observation_id,
        observation_fingerprint=observation.observation_fingerprint,
        classification=ShadowValidationClassification.INVALID_SHADOW_INPUT,
        boundary_invocation_id=observation.boundary_invocation_id,
        shadow_invocation_id=observation.shadow_invocation_id,
        runtime_request_id=observation.runtime_request_id,
        qualification_run_id=observation.qualification_run_id,
        command_id=observation.command_id,
        correlation_id=observation.correlation_id,
        idempotency_key=observation.idempotency_key,
        comparison_status=observation.comparison_status,
        mismatch_classifications=observation.mismatch_classifications,
        expected_revision=observation.expected_revision,
        previous_revision=observation.previous_revision,
        next_revision=observation.next_revision,
        transition_id=observation.transition_id,
        action_executed=observation.action_executed,
        legacy_behavior_authoritative=observation.legacy_behavior_authoritative,
        legacy_behavior_changed=observation.legacy_behavior_changed,
        runtime_connected=observation.runtime_connected,
        conflicts=tuple(
            sorted((*observation.conflicts, *conflicts), key=_conflict_sort_key)
        ),
    )


def _fingerprint_for(
    result: QualificationRuntimeBoundaryResult,
    classification: ShadowValidationClassification,
    classifications: tuple[ShadowMismatchClassification, ...],
) -> str:
    shadow = result.shadow_result
    return _digest(
        "qvf",
        (
            classification.value,
            _text(result.boundary_status),
            _text(result.comparison_status),
            ",".join(item.value for item in classifications),
            _text(result.expected_revision),
            _text(result.previous_revision),
            _text(result.next_revision),
            _text(result.transition_id),
            _text(result.action_described),
            _text(result.action_executed),
            _text(result.legacy_behavior_authoritative),
            _text(result.legacy_behavior_changed),
            _text(result.runtime_connected),
            _text(shadow.legacy_decision.environment),
            _text(shadow.qualification_state),
            _text(shadow.qualification_result),
            _text(shadow.replayed),
        ),
    )


def _digest(prefix: str, values: tuple[str, ...]) -> str:
    payload = "\x1f".join(_safe_value(value) for value in values)
    return f"{prefix}-{sha256(payload.encode('utf-8')).hexdigest()}"


def _safe_value(value: object) -> str:
    text = _text(value)
    lowered = text.lower()
    unsafe_terms = (
        "sentinel_f4c_secret_do_not_expose",
        "sentinel_f4c_token_do_not_expose",
        "sentinel_f4c_password_do_not_expose",
        "api_key",
        "secret",
        "token",
        "password",
    )
    if any(term in lowered for term in unsafe_terms):
        return "REDACTED"
    return text


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, StrEnum):
        return value.value
    return str(value)


def _conflict(
    conflict_type: ShadowValidationConflictType,
    observation_id: str,
    context: tuple[str, str],
    existing_fingerprint: str | None = None,
    incoming_fingerprint: str | None = None,
) -> ShadowValidationConflict:
    return ShadowValidationConflict(
        conflict_type=conflict_type,
        observation_id=observation_id,
        existing_fingerprint=existing_fingerprint,
        incoming_fingerprint=incoming_fingerprint,
        safe_context=(context,),
    )


def _conflict_sort_key(conflict: ShadowValidationConflict) -> tuple[str, str, str, str]:
    return (
        conflict.observation_id,
        conflict.conflict_type.value,
        conflict.existing_fingerprint or "",
        conflict.incoming_fingerprint or "",
    )


def _counter_pairs(counter: Counter[str]) -> CountPairs:
    return tuple(sorted((key, count) for key, count in counter.items() if count))


def _pairs_text(counter: Counter[str]) -> str:
    return "|".join(f"{key}:{value}" for key, value in _counter_pairs(counter))


def _conflicts_text(conflicts: tuple[ShadowValidationConflict, ...]) -> str:
    return "|".join(
        ":".join(
            (
                conflict.observation_id,
                conflict.conflict_type.value,
                conflict.existing_fingerprint or "",
                conflict.incoming_fingerprint or "",
            )
        )
        for conflict in conflicts
    )


def _group_text(
    groups: dict[str, list[ShadowValidationObservation]],
) -> str:
    parts: list[str] = []
    for observation_id in sorted(groups):
        fingerprints = Counter(
            item.observation_fingerprint for item in groups[observation_id]
        )
        parts.append(
            observation_id
            + "="
            + ",".join(
                f"{fingerprint}:{count}"
                for fingerprint, count in sorted(fingerprints.items())
            )
        )
    return "|".join(parts)


def _conflict_count(
    conflicts: tuple[ShadowValidationConflict, ...],
    conflict_type: ShadowValidationConflictType,
) -> int:
    return sum(1 for conflict in conflicts if conflict.conflict_type is conflict_type)


__all__ = [
    "ShadowObservationValidationHarness",
    "ShadowValidationClassification",
    "ShadowValidationConflict",
    "ShadowValidationConflictType",
    "ShadowValidationError",
    "ShadowValidationObservation",
    "ShadowValidationRatio",
    "ShadowValidationSummary",
    "normalize_metadata",
    "normalize_optional_decimal",
    "normalize_symbol",
    "normalize_timestamp",
    "require_paper_environment",
    "validate_identifier",
    "validate_non_negative_int",
    "validate_positive_int",
]
