from __future__ import annotations

import builtins
import os
import random
import socket
import subprocess
import time
import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from volcanoes.application.qualification import (
    ActorType,
    CommandId,
    CorrelationId,
    IdempotencyKey,
    QualificationResult,
    QualificationRunId,
    QualificationScenarioId,
    QualificationState,
    StateRevision,
)
from volcanoes.application.qualification.integration import (
    IntegrationOrderType,
    IntegrationTimeInForce,
    LegacyPaperActionType,
    LegacyPaperDecision,
    LegacyPaperDecisionType,
    PaperIntegrationEnvironment,
    PaperQualificationFacade,
    PaperQualificationShadowRequest,
    PaperQualificationShadowResult,
    PaperQualificationShadowRunner,
    PaperRuntimeRequest,
    QualificationRuntimeBoundaryMode,
    QualificationRuntimeBoundaryResult,
    QualificationRuntimeBoundaryStatus,
    QualificationRuntimeIntegrationBoundary,
    RuntimeActionKind,
    RuntimeRequestKind,
    SafeOrderIntent,
    ShadowComparisonStatus,
    ShadowMismatch,
    ShadowMismatchClassification,
    ShadowObservationValidationHarness,
    ShadowValidationClassification,
    ShadowValidationConflictType,
    ShadowValidationError,
    ShadowValidationRatio,
)
from volcanoes.application.qualification.service import PaperQualificationService
from volcanoes.application.qualification.state_machine import apply_transition

OCCURRED_AT = datetime(2026, 7, 29, 21, 0, tzinfo=UTC)


def runtime_request(**overrides: Any) -> PaperRuntimeRequest:
    values: dict[str, Any] = {
        "environment": PaperIntegrationEnvironment.PAPER,
        "runtime_request_id": "qir-validation-001",
        "qualification_run_id": QualificationRunId("pqr-validation-001"),
        "qualification_scenario_id": QualificationScenarioId("PQ-SCN-005"),
        "request_kind": RuntimeRequestKind.START_QUALIFICATION,
        "command_id": CommandId("qic-validation-001"),
        "correlation_id": CorrelationId("corr-validation-001"),
        "idempotency_key": IdempotencyKey("qik-validation-001"),
        "expected_revision": StateRevision(0),
        "actor_type": ActorType.APPLICATION,
        "occurred_at": OCCURRED_AT,
        "order_intent": SafeOrderIntent(
            symbol="AAPL",
            quantity=1,
            order_type=IntegrationOrderType.LIMIT,
            limit_price=Decimal("1"),
            time_in_force=IntegrationTimeInForce.DAY,
        ),
        "satisfied_guards": frozenset(),
    }
    values.update(overrides)
    return PaperRuntimeRequest(**values)


def legacy_decision(
    request: PaperRuntimeRequest | None = None,
    **overrides: Any,
) -> LegacyPaperDecision:
    runtime = request or runtime_request()
    values: dict[str, Any] = {
        "environment": runtime.environment,
        "legacy_decision_id": "qld-validation-001",
        "runtime_request_id": runtime.runtime_request_id,
        "qualification_run_id": runtime.qualification_run_id,
        "command_id": runtime.command_id,
        "correlation_id": runtime.correlation_id,
        "idempotency_key": runtime.idempotency_key,
        "expected_revision": runtime.expected_revision,
        "decision_type": LegacyPaperDecisionType.PROCEED,
        "action_type": LegacyPaperActionType.SUBMIT_ORDER,
        "order_intent": runtime.order_intent,
        "approved": True,
        "reason_code": "PAPER_PREVIEW_APPROVED",
    }
    values.update(overrides)
    return LegacyPaperDecision(**values)


def shadow_request(
    *,
    request: PaperRuntimeRequest | None = None,
    legacy: LegacyPaperDecision | None = None,
    shadow_invocation_id: str = "qis-validation-001",
) -> PaperQualificationShadowRequest:
    runtime = request or runtime_request()
    return PaperQualificationShadowRequest(
        runtime_request=runtime,
        legacy_decision=legacy or legacy_decision(runtime),
        shadow_invocation_id=shadow_invocation_id,
    )


def shadow_result(
    *,
    request: PaperQualificationShadowRequest | None = None,
    status: ShadowComparisonStatus = ShadowComparisonStatus.MATCH,
    classifications: tuple[ShadowMismatchClassification, ...] = (),
    previous_revision: StateRevision = StateRevision(0),
    next_revision: StateRevision | None = StateRevision(1),
    transition_id: str | None = "PQ-TRN-001",
    action: RuntimeActionKind | None = RuntimeActionKind.NO_RUNTIME_ACTION_REQUIRED,
) -> PaperQualificationShadowResult:
    shadow = request or shadow_request()
    mismatches = tuple(
        ShadowMismatch(item, item.value.lower(), "safe-reason")
        for item in classifications
    )
    return PaperQualificationShadowResult(
        shadow_invocation_id=shadow.shadow_invocation_id,
        legacy_decision=shadow.legacy_decision,
        qualification_facade_result=None,
        comparison_status=status,
        classifications=classifications,
        matched_fields=("environment", "identity"),
        mismatches=mismatches,
        qualification_run_id=shadow.runtime_request.qualification_run_id,
        command_id=shadow.runtime_request.command_id,
        correlation_id=shadow.runtime_request.correlation_id,
        idempotency_key=shadow.runtime_request.idempotency_key,
        transition_id=transition_id,
        previous_revision=previous_revision,
        next_revision=next_revision,
        legacy_action_type=shadow.legacy_decision.action_type,
        qualification_action_type=action,
        qualification_state=(
            QualificationState.QUALIFIED
            if next_revision == 10
            else QualificationState.PRECHECK_PENDING
        ),
        qualification_result=(
            QualificationResult.PASSED
            if next_revision == 10
            else QualificationResult.PENDING
        ),
        replayed=False,
        safe_operator_summary="safe validation shadow summary",
        action_executed=False,
        legacy_behavior_changed=False,
    )


def boundary_result(
    *,
    shadow: PaperQualificationShadowResult | None = None,
    boundary_invocation_id: str = "qib-validation-001",
    boundary_status: QualificationRuntimeBoundaryStatus | None = None,
    comparison_status: ShadowComparisonStatus | None = None,
    classifications: tuple[ShadowMismatchClassification, ...] | None = None,
    expected_revision: StateRevision = StateRevision(0),
    previous_revision: StateRevision | None = None,
    next_revision: StateRevision | None = StateRevision(1),
    transition_id: str | None = "PQ-TRN-001",
) -> QualificationRuntimeBoundaryResult:
    output = shadow or shadow_result(
        status=comparison_status or ShadowComparisonStatus.MATCH,
        classifications=classifications or (),
        previous_revision=previous_revision or expected_revision,
        next_revision=next_revision,
        transition_id=transition_id,
    )
    status = comparison_status or output.comparison_status
    return QualificationRuntimeBoundaryResult(
        boundary_invocation_id=boundary_invocation_id,
        boundary_mode=QualificationRuntimeBoundaryMode.SHADOW_ONLY,
        boundary_status=boundary_status or _boundary_status_for(status),
        shadow_result=output,
        qualification_run_id=output.qualification_run_id,
        runtime_request_id=output.legacy_decision.runtime_request_id,
        command_id=output.command_id,
        correlation_id=output.correlation_id,
        idempotency_key=output.idempotency_key,
        comparison_status=status,
        mismatch_classifications=classifications or output.classifications,
        expected_revision=expected_revision,
        previous_revision=previous_revision or output.previous_revision,
        next_revision=next_revision,
        transition_id=transition_id,
        action_described=output.qualification_action_type,
        safe_summary="safe validation boundary summary",
        action_executed=False,
        legacy_behavior_authoritative=True,
        legacy_behavior_changed=False,
        runtime_connected=False,
    )


def unsafe_boundary_result(
    result: QualificationRuntimeBoundaryResult,
    **overrides: Any,
) -> QualificationRuntimeBoundaryResult:
    copied = object.__new__(QualificationRuntimeBoundaryResult)
    for field in (
        "boundary_invocation_id",
        "boundary_mode",
        "boundary_status",
        "shadow_result",
        "qualification_run_id",
        "runtime_request_id",
        "command_id",
        "correlation_id",
        "idempotency_key",
        "comparison_status",
        "mismatch_classifications",
        "expected_revision",
        "previous_revision",
        "next_revision",
        "transition_id",
        "action_described",
        "safe_summary",
        "action_executed",
        "legacy_behavior_authoritative",
        "legacy_behavior_changed",
        "runtime_connected",
    ):
        object.__setattr__(copied, field, overrides.get(field, getattr(result, field)))
    return copied


def _boundary_status_for(
    status: ShadowComparisonStatus,
) -> QualificationRuntimeBoundaryStatus:
    if status is ShadowComparisonStatus.MISMATCH:
        return QualificationRuntimeBoundaryStatus.SHADOW_MISMATCH
    if status is ShadowComparisonStatus.INCOMPARABLE:
        return QualificationRuntimeBoundaryStatus.SHADOW_INCOMPARABLE
    if status is ShadowComparisonStatus.QUALIFICATION_ERROR:
        return QualificationRuntimeBoundaryStatus.SHADOW_QUALIFICATION_ERROR
    return QualificationRuntimeBoundaryStatus.SHADOW_MATCH


def test_harness_accepts_valid_immutable_boundary_result() -> None:
    result = boundary_result()
    harness = ShadowObservationValidationHarness()

    observation = harness.record(result)
    summary = harness.summarize()

    assert observation.classification is ShadowValidationClassification.MATCH
    assert observation.observation_id.startswith("qiv-")
    assert observation.action_executed is False
    assert summary.total_observations == 1
    assert summary.unique_observations == 1


def test_validation_does_not_invoke_boundary_shadow_facade_service_or_state_machine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("validation invoked qualification runtime")

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

    harness = ShadowObservationValidationHarness()
    observation = harness.record(boundary_result())

    assert observation.classification is ShadowValidationClassification.MATCH
    assert apply_transition is not fail


def test_input_boundary_result_and_outputs_are_immutable() -> None:
    result = boundary_result()
    before = repr(result)
    observation = ShadowObservationValidationHarness().record(result)
    summary = ShadowObservationValidationHarness().summarize()

    with pytest.raises(FrozenInstanceError):
        observation.observation_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        summary.total_observations = 99  # type: ignore[misc]
    assert repr(result) == before


def test_empty_summary_is_deterministic_and_zero_denominators_are_safe() -> None:
    first = ShadowObservationValidationHarness().summarize()
    second = ShadowObservationValidationHarness().summarize()

    assert first == second
    assert first.total_observations == 0
    assert first.match_ratio == ShadowValidationRatio(0, 0)
    assert first.mismatch_ratio == ShadowValidationRatio(0, 0)
    assert first.summary_fingerprint == second.summary_fingerprint


@pytest.mark.parametrize(
    ("status", "classification", "field"),
    [
        (
            ShadowComparisonStatus.MATCH,
            ShadowValidationClassification.MATCH,
            "match_count",
        ),
        (
            ShadowComparisonStatus.MATCH_WITH_NONCONSEQUENTIAL_DIFFERENCE,
            ShadowValidationClassification.MATCH_WITH_NONCONSEQUENTIAL_DIFFERENCE,
            "nonconsequential_difference_count",
        ),
        (
            ShadowComparisonStatus.MISMATCH,
            ShadowValidationClassification.MISMATCH,
            "mismatch_count",
        ),
        (
            ShadowComparisonStatus.INCOMPARABLE,
            ShadowValidationClassification.INCOMPARABLE,
            "incomparable_count",
        ),
        (
            ShadowComparisonStatus.QUALIFICATION_ERROR,
            ShadowValidationClassification.QUALIFICATION_ERROR,
            "qualification_error_count",
        ),
        (
            ShadowComparisonStatus.INVALID_SHADOW_INPUT,
            ShadowValidationClassification.INVALID_SHADOW_INPUT,
            "invalid_input_count",
        ),
    ],
)
def test_single_statuses_are_classified_and_counted(
    status: ShadowComparisonStatus,
    classification: ShadowValidationClassification,
    field: str,
) -> None:
    observation = ShadowObservationValidationHarness().record(
        boundary_result(comparison_status=status)
    )
    harness = ShadowObservationValidationHarness()
    harness.record(boundary_result(comparison_status=status))
    summary = harness.summarize()

    assert observation.classification is classification
    assert getattr(summary, field) == 1


def test_exact_duplicate_is_replay_not_conflict() -> None:
    result = boundary_result()
    harness = ShadowObservationValidationHarness()

    first = harness.record(result)
    second = harness.record(result)
    summary = harness.summarize()

    assert first.observation_id == second.observation_id
    assert first.observation_fingerprint == second.observation_fingerprint
    assert second.conflicts == ()
    assert summary.total_observations == 2
    assert summary.unique_observations == 1
    assert summary.duplicate_observations == 1
    assert summary.deterministic_replay_count == 1
    assert summary.conflicting_duplicates == 0


def test_conflicting_duplicate_detects_drift_without_overwrite() -> None:
    first = boundary_result()
    second = boundary_result(
        comparison_status=ShadowComparisonStatus.MISMATCH,
        classifications=(ShadowMismatchClassification.ACTION_KIND_MISMATCH,),
    )
    harness = ShadowObservationValidationHarness()

    first_observation = harness.record(first)
    second_observation = harness.record(second)
    summary = harness.summarize()

    assert first_observation.observation_id == second_observation.observation_id
    assert (
        second_observation.observation_fingerprint
        != first_observation.observation_fingerprint
    )
    assert {conflict.conflict_type for conflict in second_observation.conflicts} >= {
        ShadowValidationConflictType.DUPLICATE_IDENTITY_CONFLICT,
        ShadowValidationConflictType.COMPARISON_STATUS_DRIFT,
        ShadowValidationConflictType.MISMATCH_CLASSIFICATION_DRIFT,
    }
    assert summary.conflicting_duplicates == 1
    assert summary.nondeterministic_replay_count == 1
    assert summary.nonrepeatable_observation_groups == 1


def test_independent_observations_and_repeatability_are_counted() -> None:
    first = boundary_result(boundary_invocation_id="qib-validation-001")
    second = boundary_result(boundary_invocation_id="qib-validation-002")
    harness = ShadowObservationValidationHarness()

    harness.record(first)
    harness.record(second)
    harness.record(second)
    summary = harness.summarize()

    assert summary.total_observations == 3
    assert summary.unique_observations == 2
    assert summary.repeatable_observation_groups == 1
    assert summary.nonrepeatable_observation_groups == 0


def test_revision_and_transition_drift_are_detected() -> None:
    harness = ShadowObservationValidationHarness()
    harness.record(boundary_result())
    drift = boundary_result(
        previous_revision=StateRevision(1), transition_id="PQ-TRN-002"
    )

    observation = harness.record(drift)
    summary = harness.summarize()

    assert {conflict.conflict_type for conflict in observation.conflicts} >= {
        ShadowValidationConflictType.REVISION_DRIFT,
        ShadowValidationConflictType.TRANSITION_DRIFT,
        ShadowValidationConflictType.REVISION_CONTINUITY_FAILURE,
    }
    assert summary.revision_continuity_failure_count == 1


@pytest.mark.parametrize(
    ("field", "value", "conflict_type"),
    [
        (
            "boundary_invocation_id",
            "",
            ShadowValidationConflictType.IDENTITY_CONTINUITY_FAILURE,
        ),
        (
            "runtime_request_id",
            "",
            ShadowValidationConflictType.IDENTITY_CONTINUITY_FAILURE,
        ),
        (
            "qualification_run_id",
            QualificationRunId(""),
            ShadowValidationConflictType.IDENTITY_CONTINUITY_FAILURE,
        ),
        (
            "command_id",
            CommandId(""),
            ShadowValidationConflictType.IDENTITY_CONTINUITY_FAILURE,
        ),
        (
            "correlation_id",
            CorrelationId(""),
            ShadowValidationConflictType.IDENTITY_CONTINUITY_FAILURE,
        ),
        (
            "idempotency_key",
            IdempotencyKey(""),
            ShadowValidationConflictType.IDENTITY_CONTINUITY_FAILURE,
        ),
        (
            "action_executed",
            True,
            ShadowValidationConflictType.ACTION_EXECUTION_VIOLATION,
        ),
        (
            "legacy_behavior_authoritative",
            False,
            ShadowValidationConflictType.LEGACY_AUTHORITY_VIOLATION,
        ),
        (
            "legacy_behavior_changed",
            True,
            ShadowValidationConflictType.LEGACY_AUTHORITY_VIOLATION,
        ),
        (
            "runtime_connected",
            True,
            ShadowValidationConflictType.RUNTIME_CONNECTION_VIOLATION,
        ),
    ],
)
def test_continuity_and_authority_violations_are_classified(
    field: str,
    value: object,
    conflict_type: ShadowValidationConflictType,
) -> None:
    observation = ShadowObservationValidationHarness().record(
        unsafe_boundary_result(boundary_result(), **{field: value})
    )

    assert (
        observation.classification
        is ShadowValidationClassification.INVALID_SHADOW_INPUT
    )
    assert conflict_type in {
        conflict.conflict_type for conflict in observation.conflicts
    }


def test_live_and_unknown_environments_are_classified_without_runtime_control() -> None:
    live_result = boundary_result()
    object.__setattr__(
        live_result.shadow_result.legacy_decision,
        "environment",
        PaperIntegrationEnvironment.LIVE,
    )
    observation = ShadowObservationValidationHarness().record(live_result)

    assert (
        observation.classification
        is ShadowValidationClassification.INVALID_SHADOW_INPUT
    )
    assert ShadowValidationConflictType.ENVIRONMENT_VIOLATION in {
        conflict.conflict_type for conflict in observation.conflicts
    }


def test_revision_and_transition_continuity_valid_case() -> None:
    harness = ShadowObservationValidationHarness()

    harness.record(
        boundary_result(
            expected_revision=StateRevision(0), next_revision=StateRevision(1)
        )
    )
    summary = harness.summarize()

    assert summary.revision_continuity_failure_count == 0
    assert summary.transition_continuity_failure_count == 0


def test_transition_continuity_failure_detected() -> None:
    result = boundary_result()
    object.__setattr__(result.shadow_result, "transition_id", "PQ-TRN-OTHER")

    summary = ShadowObservationValidationHarness().record(result)

    assert ShadowValidationConflictType.TRANSITION_CONTINUITY_FAILURE in {
        conflict.conflict_type for conflict in summary.conflicts
    }


def test_mismatch_classifications_preserved_and_canonically_counted() -> None:
    harness = ShadowObservationValidationHarness()
    result = boundary_result(
        comparison_status=ShadowComparisonStatus.MISMATCH,
        classifications=(
            ShadowMismatchClassification.REVISION_MISMATCH,
            ShadowMismatchClassification.ACTION_KIND_MISMATCH,
        ),
    )

    observation = harness.record(result)
    summary = harness.summarize()

    assert observation.mismatch_classifications == (
        ShadowMismatchClassification.ACTION_KIND_MISMATCH,
        ShadowMismatchClassification.REVISION_MISMATCH,
    )
    assert summary.mismatch_classification_counts == (
        ("ACTION_KIND_MISMATCH", 1),
        ("REVISION_MISMATCH", 1),
    )


def test_summary_ordering_and_fingerprints_are_deterministic() -> None:
    first = boundary_result(boundary_invocation_id="qib-validation-001")
    second = boundary_result(boundary_invocation_id="qib-validation-002")

    harness_a = ShadowObservationValidationHarness()
    harness_a.record(first)
    harness_a.record(second)
    harness_b = ShadowObservationValidationHarness()
    harness_b.record(second)
    harness_b.record(first)

    assert harness_a.summarize() == harness_b.summarize()
    assert (
        harness_a.summarize().summary_fingerprint
        == harness_b.summarize().summary_fingerprint
    )


def test_observation_id_and_fingerprint_are_deterministic_and_sensitive() -> None:
    first = ShadowObservationValidationHarness().record(boundary_result())
    second = ShadowObservationValidationHarness().record(boundary_result())
    changed = ShadowObservationValidationHarness().record(
        boundary_result(boundary_invocation_id="qib-validation-changed")
    )
    changed_facts = ShadowObservationValidationHarness().record(
        boundary_result(comparison_status=ShadowComparisonStatus.MISMATCH)
    )

    assert first.observation_id == second.observation_id
    assert first.observation_fingerprint == second.observation_fingerprint
    assert first.observation_id != changed.observation_id
    assert first.observation_fingerprint != changed_facts.observation_fingerprint


def test_ratios_are_exact_and_do_not_invent_success() -> None:
    harness = ShadowObservationValidationHarness()
    harness.record(boundary_result(comparison_status=ShadowComparisonStatus.MATCH))
    harness.record(
        boundary_result(
            boundary_invocation_id="qib-validation-mismatch",
            comparison_status=ShadowComparisonStatus.MISMATCH,
        )
    )
    harness.record(
        boundary_result(
            boundary_invocation_id="qib-validation-err",
            comparison_status=ShadowComparisonStatus.QUALIFICATION_ERROR,
        )
    )
    summary = harness.summarize()

    assert summary.match_ratio == ShadowValidationRatio(1, 3)
    assert summary.mismatch_ratio == ShadowValidationRatio(1, 3)
    assert summary.qualification_error_ratio == ShadowValidationRatio(1, 3)
    assert ShadowObservationValidationHarness().summarize().match_ratio == (
        ShadowValidationRatio(0, 0)
    )


def test_summary_makes_no_readiness_broker_profit_or_live_claims() -> None:
    summary = ShadowObservationValidationHarness().summarize()
    rendered = repr(summary).lower()

    assert "readiness" not in rendered
    assert "broker_correct" not in rendered
    assert "profit" not in rendered
    assert "live_read" not in rendered


def test_invalid_type_fails_with_typed_safe_error() -> None:
    with pytest.raises(ShadowValidationError) as error:
        ShadowObservationValidationHarness().record(object())  # type: ignore[arg-type]

    assert error.value.reason_code == "INVALID_SHADOW_VALIDATION_INPUT"
    assert "SENTINEL_F4C_SECRET_DO_NOT_EXPOSE" not in str(error.value)


def test_secret_absent_from_observation_summary_conflicts_errors_and_ids() -> None:
    result = boundary_result()
    object.__setattr__(
        result.shadow_result,
        "safe_operator_summary",
        "SENTINEL_F4C_SECRET_DO_NOT_EXPOSE",
    )
    harness = ShadowObservationValidationHarness()
    observation = harness.record(
        unsafe_boundary_result(result, legacy_behavior_changed=True)
    )
    summary = harness.summarize()

    rendered = repr((observation, summary, observation.conflicts))
    assert "SENTINEL_F4C_SECRET_DO_NOT_EXPOSE" not in observation.observation_id
    assert "SENTINEL_F4C_TOKEN_DO_NOT_EXPOSE" not in rendered
    assert "SENTINEL_F4C_PASSWORD_DO_NOT_EXPOSE" not in rendered


def test_no_external_effects_from_validation_harness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = (
        boundary_result(),
        boundary_result(comparison_status=ShadowComparisonStatus.MISMATCH),
        boundary_result(
            boundary_invocation_id="qib-validation-inc",
            comparison_status=ShadowComparisonStatus.INCOMPARABLE,
        ),
        boundary_result(
            boundary_invocation_id="qib-validation-err",
            comparison_status=ShadowComparisonStatus.QUALIFICATION_ERROR,
        ),
    )

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

    harness = ShadowObservationValidationHarness()
    harness.summarize()
    for result in results:
        harness.record(result)
    harness.record(results[0])
    harness.record(
        boundary_result(
            comparison_status=ShadowComparisonStatus.MISMATCH,
            classifications=(ShadowMismatchClassification.ACTION_KIND_MISMATCH,),
        )
    )
    harness.record(
        unsafe_boundary_result(results[0], previous_revision=StateRevision(2))
    )
    summary = harness.summarize()

    assert summary.total_observations == 7
    assert summary.conflicting_duplicates >= 1


def test_validation_does_not_access_broker_simulator_scanner_supervisor_ui_api_or_cli() -> (
    None
):
    harness = ShadowObservationValidationHarness()

    harness.record(boundary_result())
    summary = harness.summarize()

    assert summary.action_executed_count == 0
    assert summary.runtime_connected_count == 0


def test_default_successful_scenario_style_trace_records_step_by_step() -> None:
    harness = ShadowObservationValidationHarness()
    for revision in range(10):
        harness.record(
            boundary_result(
                boundary_invocation_id=f"qib-validation-trace-{revision}",
                expected_revision=StateRevision(revision),
                previous_revision=StateRevision(revision),
                next_revision=StateRevision(revision + 1),
                transition_id=f"PQ-TRN-{revision + 1:03d}",
                shadow=shadow_result(
                    previous_revision=StateRevision(revision),
                    next_revision=StateRevision(revision + 1),
                    transition_id=f"PQ-TRN-{revision + 1:03d}",
                ),
            )
        )
    summary = harness.summarize()

    assert summary.total_observations == 10
    assert summary.match_count == 10
    assert summary.action_executed_count == 0
    assert summary.legacy_authority_violation_count == 0
    assert summary.revision_continuity_failure_count == 0


def test_replaying_and_reordering_scenario_results_is_canonical() -> None:
    results = tuple(
        boundary_result(
            boundary_invocation_id=f"qib-validation-replay-{revision}",
            expected_revision=StateRevision(revision),
            previous_revision=StateRevision(revision),
            next_revision=StateRevision(revision + 1),
            transition_id=f"PQ-TRN-{revision + 1:03d}",
            shadow=shadow_result(
                previous_revision=StateRevision(revision),
                next_revision=StateRevision(revision + 1),
                transition_id=f"PQ-TRN-{revision + 1:03d}",
            ),
        )
        for revision in range(10)
    )
    first = ShadowObservationValidationHarness()
    second = ShadowObservationValidationHarness()
    for result in results:
        first.record(result)
    for result in reversed(results):
        second.record(result)

    assert first.summarize() == second.summarize()


def test_one_altered_scenario_result_creates_deterministic_conflict() -> None:
    harness = ShadowObservationValidationHarness()
    harness.record(boundary_result(boundary_invocation_id="qib-validation-scenario"))
    harness.record(
        boundary_result(
            boundary_invocation_id="qib-validation-scenario",
            comparison_status=ShadowComparisonStatus.MISMATCH,
            classifications=(ShadowMismatchClassification.REPLAY_MISMATCH,),
        )
    )
    summary = harness.summarize()

    assert summary.conflicting_duplicates == 1
    assert summary.validation_conflicts[0].observation_id.startswith("qiv-")
