from __future__ import annotations

import builtins
import os
import random
import socket
import subprocess
import time
import uuid
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest

from volcanoes.application.qualification.integration import (
    PaperQualificationFacade,
    PaperQualificationShadowRunner,
    QualificationRuntimeIntegrationBoundary,
    ShadowObservationValidationHarness,
    ShadowReadinessAssessment,
    ShadowReadinessAssessmentService,
    ShadowReadinessCriterionResult,
    ShadowReadinessDecision,
    ShadowReadinessError,
    ShadowReadinessPolicy,
    ShadowValidationConflict,
    ShadowValidationConflictType,
    ShadowValidationRatio,
    ShadowValidationSummary,
)
from volcanoes.application.qualification.service import PaperQualificationService


def summary(**overrides: Any) -> ShadowValidationSummary:
    values: dict[str, Any] = {
        "total_observations": 4,
        "unique_observations": 3,
        "duplicate_observations": 1,
        "conflicting_duplicates": 0,
        "match_count": 4,
        "nonconsequential_difference_count": 0,
        "mismatch_count": 0,
        "incomparable_count": 0,
        "qualification_error_count": 0,
        "invalid_input_count": 0,
        "status_counts": (("MATCH", 4),),
        "mismatch_classification_counts": (),
        "repeatable_observation_groups": 1,
        "nonrepeatable_observation_groups": 0,
        "identity_continuity_failure_count": 0,
        "revision_continuity_failure_count": 0,
        "transition_continuity_failure_count": 0,
        "deterministic_replay_count": 1,
        "nondeterministic_replay_count": 0,
        "safely_rejected_count": 0,
        "action_executed_count": 0,
        "legacy_authority_violation_count": 0,
        "legacy_behavior_changed_count": 0,
        "runtime_connected_count": 0,
        "environment_violation_count": 0,
        "validation_conflicts": (),
        "match_ratio": ShadowValidationRatio(4, 4),
        "mismatch_ratio": ShadowValidationRatio(0, 4),
        "qualification_error_ratio": ShadowValidationRatio(0, 4),
        "invalid_input_ratio": ShadowValidationRatio(0, 4),
        "summary_fingerprint": "qvs-clean",
    }
    values.update(overrides)
    return ShadowValidationSummary(**values)


def strict_policy(**overrides: Any) -> ShadowReadinessPolicy:
    base = ShadowReadinessPolicy.strict_validation_policy()
    return replace(base, **overrides)


def assess(
    validation_summary: ShadowValidationSummary | None = None,
    policy: ShadowReadinessPolicy | None = None,
) -> ShadowReadinessAssessment:
    return ShadowReadinessAssessmentService().assess(
        validation_summary or summary(),
        policy or strict_policy(),
    )


def test_service_accepts_valid_summary_and_policy() -> None:
    assessment = assess()

    assert assessment.decision is ShadowReadinessDecision.READY_FOR_NEXT_PHASE
    assert assessment.policy_fingerprint.startswith("qrp-")
    assert assessment.assessment_fingerprint.startswith("qra-")
    assert assessment.validation_summary_fingerprint == "qvs-clean"


def test_service_does_not_invoke_validation_boundary_shadow_facade_service_or_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("readiness assessment invoked lower layer")

    monkeypatch.setattr(ShadowObservationValidationHarness, "record", fail)
    monkeypatch.setattr(ShadowObservationValidationHarness, "summarize", fail)
    monkeypatch.setattr(
        QualificationRuntimeIntegrationBoundary, "evaluate_shadow", fail
    )
    monkeypatch.setattr(PaperQualificationShadowRunner, "evaluate", fail)
    monkeypatch.setattr(PaperQualificationFacade, "handle", fail)
    monkeypatch.setattr(PaperQualificationService, "execute", fail)
    monkeypatch.setattr(
        "volcanoes.application.qualification.state_machine.apply_transition",
        fail,
    )

    assert assess().decision is ShadowReadinessDecision.READY_FOR_NEXT_PHASE


def test_summary_policy_assessment_and_criteria_are_immutable() -> None:
    validation_summary = summary()
    policy = strict_policy()
    assessment = assess(validation_summary, policy)
    criterion = assessment.criteria[0]

    with pytest.raises(FrozenInstanceError):
        validation_summary.total_observations = 99  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        policy.minimum_total_observations = 99  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        assessment.execution_authorized = True  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        criterion.passed = False  # type: ignore[misc]
    assert isinstance(criterion, ShadowReadinessCriterionResult)


def test_empty_summary_is_insufficient_and_zero_observations_never_ready() -> None:
    empty = summary(
        total_observations=0,
        unique_observations=0,
        duplicate_observations=0,
        match_count=0,
        status_counts=(),
        repeatable_observation_groups=0,
        deterministic_replay_count=0,
        match_ratio=ShadowValidationRatio(0, 0),
        mismatch_ratio=ShadowValidationRatio(0, 0),
        summary_fingerprint="qvs-empty",
    )
    assessment = assess(empty)

    assert assessment.decision is ShadowReadinessDecision.INSUFFICIENT_EVIDENCE
    assert "READINESS_MINIMUM_TOTAL_OBSERVATIONS_NOT_MET" in assessment.reason_codes


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        (
            "total_observations",
            3,
            "READINESS_MINIMUM_TOTAL_OBSERVATIONS_NOT_MET",
        ),
        (
            "unique_observations",
            1,
            "READINESS_MINIMUM_UNIQUE_OBSERVATIONS_NOT_MET",
        ),
        (
            "repeatable_observation_groups",
            0,
            "READINESS_MINIMUM_REPEATABLE_GROUPS_NOT_MET",
        ),
        (
            "deterministic_replay_count",
            0,
            "READINESS_DETERMINISTIC_REPLAY_REQUIRED",
        ),
    ],
)
def test_evidence_sufficiency_thresholds_enforced(
    field: str,
    value: int,
    reason: str,
) -> None:
    assessment = assess(
        summary(**{field: value, "summary_fingerprint": f"qvs-{field}"})
    )

    assert assessment.decision is ShadowReadinessDecision.INSUFFICIENT_EVIDENCE
    assert reason in assessment.reason_codes


def test_sufficient_evidence_with_hard_failure_is_not_ready() -> None:
    assessment = assess(summary(identity_continuity_failure_count=1))

    assert assessment.decision is ShadowReadinessDecision.NOT_READY
    assert "READINESS_IDENTITY_CONTINUITY_FAILURE_LIMIT_EXCEEDED" in (
        assessment.reason_codes
    )


def test_decision_precedence_keeps_safety_visible() -> None:
    assessment = assess(
        summary(
            total_observations=0,
            unique_observations=0,
            identity_continuity_failure_count=1,
            match_ratio=ShadowValidationRatio(0, 0),
            mismatch_ratio=ShadowValidationRatio(0, 0),
            summary_fingerprint="qvs-insufficient-and-unsafe",
        )
    )

    assert assessment.decision is ShadowReadinessDecision.NOT_READY
    assert "READINESS_MINIMUM_TOTAL_OBSERVATIONS_NOT_MET" in assessment.reason_codes
    assert "READINESS_IDENTITY_CONTINUITY_FAILURE_LIMIT_EXCEEDED" in (
        assessment.reason_codes
    )


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        (
            "identity_continuity_failure_count",
            "READINESS_IDENTITY_CONTINUITY_FAILURE_LIMIT_EXCEEDED",
        ),
        (
            "revision_continuity_failure_count",
            "READINESS_REVISION_CONTINUITY_FAILURE_LIMIT_EXCEEDED",
        ),
        (
            "transition_continuity_failure_count",
            "READINESS_TRANSITION_CONTINUITY_FAILURE_LIMIT_EXCEEDED",
        ),
        (
            "legacy_authority_violation_count",
            "READINESS_LEGACY_AUTHORITY_VIOLATION_LIMIT_EXCEEDED",
        ),
        (
            "legacy_behavior_changed_count",
            "READINESS_LEGACY_BEHAVIOR_CHANGED_LIMIT_EXCEEDED",
        ),
        ("action_executed_count", "READINESS_ACTION_EXECUTION_LIMIT_EXCEEDED"),
        ("runtime_connected_count", "READINESS_RUNTIME_CONNECTED_LIMIT_EXCEEDED"),
        ("environment_violation_count", "READINESS_ENVIRONMENT_VIOLATION_PRESENT"),
        ("conflicting_duplicates", "READINESS_CONFLICTING_DUPLICATE_LIMIT_EXCEEDED"),
        (
            "nondeterministic_replay_count",
            "READINESS_NONDETERMINISTIC_REPLAY_LIMIT_EXCEEDED",
        ),
        ("qualification_error_count", "READINESS_QUALIFICATION_ERROR_LIMIT_EXCEEDED"),
        ("invalid_input_count", "READINESS_INVALID_INPUT_LIMIT_EXCEEDED"),
        ("incomparable_count", "READINESS_INCOMPARABLE_LIMIT_EXCEEDED"),
        ("mismatch_count", "READINESS_MISMATCH_LIMIT_EXCEEDED"),
    ],
)
def test_safety_and_quality_limits_produce_not_ready(field: str, reason: str) -> None:
    assessment = assess(summary(**{field: 1, "summary_fingerprint": f"qvs-{field}"}))

    assert assessment.decision is ShadowReadinessDecision.NOT_READY
    assert reason in assessment.reason_codes


def test_match_ratio_minimum_and_mismatch_ratio_maximum_enforced() -> None:
    low_match = assess(
        summary(
            match_count=3,
            mismatch_count=1,
            status_counts=(("MATCH", 3), ("MISMATCH", 1)),
            match_ratio=ShadowValidationRatio(3, 4),
            mismatch_ratio=ShadowValidationRatio(1, 4),
            summary_fingerprint="qvs-ratio",
        )
    )

    assert low_match.decision is ShadowReadinessDecision.NOT_READY
    assert "READINESS_MATCH_RATIO_TOO_LOW" in low_match.reason_codes
    assert "READINESS_MISMATCH_RATIO_TOO_HIGH" in low_match.reason_codes


def test_allowed_mismatch_classification_can_pass_development_policy() -> None:
    policy = ShadowReadinessPolicy.development_observation_policy(
        allowed_mismatch_classifications=("ACTION_KIND_MISMATCH",),
    )
    validation_summary = summary(
        total_observations=1,
        unique_observations=1,
        duplicate_observations=0,
        match_count=0,
        mismatch_count=1,
        status_counts=(("MISMATCH", 1),),
        mismatch_classification_counts=(("ACTION_KIND_MISMATCH", 1),),
        repeatable_observation_groups=0,
        deterministic_replay_count=0,
        match_ratio=ShadowValidationRatio(0, 1),
        mismatch_ratio=ShadowValidationRatio(1, 1),
        summary_fingerprint="qvs-allowed-mismatch",
    )

    assessment = assess(validation_summary, policy)

    assert assessment.decision is ShadowReadinessDecision.READY_FOR_NEXT_PHASE


def test_prohibited_or_unallowed_mismatch_classification_is_not_ready() -> None:
    validation_summary = summary(
        mismatch_count=1,
        mismatch_classification_counts=(("ACTION_KIND_MISMATCH", 1),),
        mismatch_ratio=ShadowValidationRatio(1, 4),
        summary_fingerprint="qvs-prohibited",
    )
    policy = strict_policy(
        maximum_mismatch_count=4,
        maximum_mismatch_ratio=ShadowValidationRatio(1, 1),
        prohibited_mismatch_classifications=("ACTION_KIND_MISMATCH",),
    )

    assessment = assess(validation_summary, policy)

    assert assessment.decision is ShadowReadinessDecision.NOT_READY
    assert "READINESS_PROHIBITED_MISMATCH_PRESENT" in assessment.reason_codes
    assert "READINESS_UNALLOWED_MISMATCH_PRESENT" in assessment.reason_codes


def test_nonconsequential_difference_can_be_allowed_or_prohibited() -> None:
    validation_summary = summary(
        nonconsequential_difference_count=1,
        mismatch_count=1,
        mismatch_classification_counts=(("REPLAY_MISMATCH", 1),),
        mismatch_ratio=ShadowValidationRatio(1, 4),
        summary_fingerprint="qvs-nonconsequential",
    )
    allowed = strict_policy(
        maximum_mismatch_count=1,
        maximum_mismatch_ratio=ShadowValidationRatio(1, 4),
        allowed_mismatch_classifications=("REPLAY_MISMATCH",),
    )
    prohibited = strict_policy(
        maximum_mismatch_count=1,
        maximum_mismatch_ratio=ShadowValidationRatio(1, 4),
        prohibited_mismatch_classifications=("REPLAY_MISMATCH",),
    )

    assert assess(validation_summary, allowed).decision is (
        ShadowReadinessDecision.READY_FOR_NEXT_PHASE
    )
    assert assess(validation_summary, prohibited).decision is (
        ShadowReadinessDecision.NOT_READY
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"minimum_total_observations": -1},
        {"maximum_mismatch_count": -1},
        {"minimum_match_ratio": ShadowValidationRatio(2, 1)},
        {"minimum_match_ratio": ShadowValidationRatio(0, 0)},
        {
            "allowed_mismatch_classifications": ("A",),
            "prohibited_mismatch_classifications": ("A",),
        },
    ],
)
def test_invalid_policy_is_rejected_safely(updates: dict[str, object]) -> None:
    with pytest.raises(ShadowReadinessError):
        strict_policy(**updates)


def test_policy_and_assessment_fingerprints_are_deterministic_and_sensitive() -> None:
    policy_a = strict_policy()
    policy_b = strict_policy()
    policy_c = strict_policy(minimum_total_observations=5)
    summary_a = summary()
    summary_b = summary()
    summary_c = summary(summary_fingerprint="qvs-materially-different")

    assert policy_a.policy_digest == policy_b.policy_digest
    assert policy_a.policy_digest != policy_c.policy_digest
    assert assess(summary_a, policy_a).assessment_fingerprint == (
        assess(summary_b, policy_b).assessment_fingerprint
    )
    assert assess(summary_a, policy_a).assessment_fingerprint != (
        assess(summary_c, policy_a).assessment_fingerprint
    )


def test_canonical_ordering_for_criteria_reasons_and_risks() -> None:
    assessment = assess(
        summary(
            identity_continuity_failure_count=1,
            action_executed_count=1,
            summary_fingerprint="qvs-ordering",
        )
    )

    assert assessment.unsatisfied_criterion_ids == tuple(
        sorted(assessment.unsatisfied_criterion_ids)
    )
    assert assessment.reason_codes == tuple(sorted(assessment.reason_codes))
    assert assessment.risks == tuple(sorted(assessment.risks))


@pytest.mark.parametrize(
    "decision_summary",
    [
        summary(),
        summary(
            identity_continuity_failure_count=1, summary_fingerprint="qvs-not-ready"
        ),
        summary(
            total_observations=0,
            unique_observations=0,
            summary_fingerprint="qvs-insufficient",
        ),
    ],
)
def test_all_decisions_remain_advisory_only(
    decision_summary: ShadowValidationSummary,
) -> None:
    assessment = assess(decision_summary)

    assert assessment.advisory_only is True
    assert assessment.execution_authorized is False
    assert assessment.runtime_changed is False
    assert assessment.broker_accessed is False
    assert assessment.simulator_accessed is False
    assert assessment.live_authorized is False


def test_assessment_does_not_claim_external_readiness_or_profitability() -> None:
    rendered = repr(assess()).lower()

    assert "profit" not in rendered
    assert "regulatory" not in rendered
    assert "broker_ready" not in rendered
    assert "legacy_retirement" not in rendered


def test_invalid_summary_type_fails_safely() -> None:
    with pytest.raises(ShadowReadinessError) as error:
        ShadowReadinessAssessmentService().assess(object(), strict_policy())  # type: ignore[arg-type]

    assert error.value.reason_code == "INVALID_READINESS_SUMMARY"


def test_secret_absent_from_policy_assessment_criteria_risks_errors_and_fingerprints() -> (
    None
):
    policy = strict_policy(policy_label="SENTINEL_F4D_SECRET_DO_NOT_EXPOSE")
    assessment = assess(summary(identity_continuity_failure_count=1), policy)
    with pytest.raises(ShadowReadinessError) as error:
        ShadowReadinessAssessmentService().assess(summary(), object())  # type: ignore[arg-type]

    rendered = repr(
        (policy, assessment, assessment.criteria, assessment.risks, error.value)
    )
    assert "SENTINEL_F4D_SECRET_DO_NOT_EXPOSE" not in policy.policy_digest
    assert "SENTINEL_F4D_TOKEN_DO_NOT_EXPOSE" not in rendered
    assert "SENTINEL_F4D_PASSWORD_DO_NOT_EXPOSE" not in rendered


def test_no_external_effects_from_readiness_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("external effect attempted")

    monkeypatch.setattr(builtins, "open", fail)
    monkeypatch.setattr(Path, "read_text", fail)
    monkeypatch.setattr(Path, "write_text", fail)
    monkeypatch.setattr(Path, "write_bytes", fail)
    monkeypatch.setattr(socket, "socket", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(time, "time", fail)
    monkeypatch.setattr(uuid, "uuid4", fail)
    monkeypatch.setattr(random, "random", fail)
    monkeypatch.setattr(ShadowObservationValidationHarness, "record", fail)
    monkeypatch.setattr(ShadowObservationValidationHarness, "summarize", fail)
    monkeypatch.setattr(
        QualificationRuntimeIntegrationBoundary, "evaluate_shadow", fail
    )
    monkeypatch.setattr(PaperQualificationShadowRunner, "evaluate", fail)
    monkeypatch.setattr(PaperQualificationFacade, "handle", fail)
    monkeypatch.setattr(PaperQualificationService, "execute", fail)
    monkeypatch.setattr(
        "volcanoes.application.qualification.state_machine.apply_transition",
        fail,
    )

    assess()
    assess(summary(identity_continuity_failure_count=1))
    assess(summary(total_observations=0, unique_observations=0))
    with pytest.raises(ShadowReadinessError):
        strict_policy(minimum_total_observations=-1)


def test_conflict_summary_drives_not_ready() -> None:
    validation_summary = summary(
        conflicting_duplicates=1,
        nondeterministic_replay_count=1,
        nonrepeatable_observation_groups=1,
        validation_conflicts=(
            ShadowValidationConflict(
                ShadowValidationConflictType.DUPLICATE_IDENTITY_CONFLICT,
                "qiv-conflict",
            ),
        ),
        summary_fingerprint="qvs-conflict",
    )

    assessment = assess(validation_summary)

    assert assessment.decision is ShadowReadinessDecision.NOT_READY
    assert "READINESS_CONFLICTING_DUPLICATE_LIMIT_EXCEEDED" in assessment.reason_codes
