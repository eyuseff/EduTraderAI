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
    Guard,
    IdempotencyKey,
    InMemoryQualificationRunRepository,
    QualificationResult,
    QualificationRunId,
    QualificationScenarioId,
    QualificationState,
    RecordingQualificationEvidenceRecorder,
    StateRevision,
    default_positive_scenario,
)
from volcanoes.application.qualification.integration import (
    BoundaryIdentityContinuityError,
    BoundaryInputValidationError,
    BoundaryModeError,
    BoundaryResultValidationError,
    BoundaryShadowInvocationError,
    IntegrationOrderType,
    IntegrationTimeInForce,
    LegacyPaperActionType,
    LegacyPaperDecision,
    LegacyPaperDecisionType,
    PaperEnvironmentRequiredError,
    PaperIntegrationEnvironment,
    PaperQualificationFacade,
    PaperQualificationShadowRequest,
    PaperQualificationShadowResult,
    PaperQualificationShadowRunner,
    PaperRuntimeRequest,
    QualificationRuntimeBoundaryMode,
    QualificationRuntimeBoundaryRequest,
    QualificationRuntimeBoundaryStatus,
    QualificationRuntimeIntegrationBoundary,
    RuntimeActionKind,
    RuntimeRequestKind,
    SafeOrderIntent,
    ShadowComparisonStatus,
    ShadowInputValidationError,
    ShadowMismatch,
    ShadowMismatchClassification,
    boundary_status_from_shadow,
    derive_boundary_invocation_id,
)
from volcanoes.application.qualification.service import PaperQualificationService

RUN_ID = QualificationRunId("pq-run-f4a-001")
SCENARIO_ID = QualificationScenarioId("PQ-SCN-005")
COMMAND_ID = CommandId("cmd-f4a-001")
CORRELATION_ID = CorrelationId("corr-f4a-001")
IDEMPOTENCY_KEY = IdempotencyKey("idem-f4a-001")
RUNTIME_REQUEST_ID = "runtime-request-f4a-001"
OCCURRED_AT = datetime(2026, 7, 29, 18, 0, tzinfo=UTC)


class ControlledRunner(PaperQualificationShadowRunner):
    def __init__(
        self,
        result: PaperQualificationShadowResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.requests: list[PaperQualificationShadowRequest] = []

    def evaluate(
        self,
        request: PaperQualificationShadowRequest,
    ) -> PaperQualificationShadowResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("test runner result was not configured")
        return self.result


def order(**overrides: Any) -> SafeOrderIntent:
    values: dict[str, Any] = {
        "symbol": "AAPL",
        "quantity": 1,
        "order_type": IntegrationOrderType.LIMIT,
        "limit_price": Decimal("100"),
        "time_in_force": IntegrationTimeInForce.DAY,
    }
    values.update(overrides)
    return SafeOrderIntent(**values)


def runtime_request(**overrides: Any) -> PaperRuntimeRequest:
    values: dict[str, Any] = {
        "environment": PaperIntegrationEnvironment.PAPER,
        "runtime_request_id": RUNTIME_REQUEST_ID,
        "qualification_run_id": RUN_ID,
        "qualification_scenario_id": SCENARIO_ID,
        "request_kind": RuntimeRequestKind.BROKER_REQUEST_SENT,
        "command_id": COMMAND_ID,
        "correlation_id": CORRELATION_ID,
        "idempotency_key": IDEMPOTENCY_KEY,
        "expected_revision": StateRevision(4),
        "actor_type": ActorType.APPLICATION,
        "occurred_at": OCCURRED_AT,
        "order_intent": order(),
        "satisfied_guards": frozenset(
            {
                Guard.PAPER_ENVIRONMENT,
                Guard.BROKER_CAPABILITY_AVAILABLE,
                Guard.NO_DUPLICATE_KEY,
            }
        ),
        "object_reference": "broker-request-f4a-001",
    }
    values.update(overrides)
    return PaperRuntimeRequest(**values)


def unsafe_runtime_request(environment: object) -> PaperRuntimeRequest:
    request = object.__new__(PaperRuntimeRequest)
    object.__setattr__(request, "environment", environment)
    object.__setattr__(request, "runtime_request_id", RUNTIME_REQUEST_ID)
    object.__setattr__(request, "qualification_run_id", RUN_ID)
    object.__setattr__(request, "qualification_scenario_id", SCENARIO_ID)
    object.__setattr__(request, "request_kind", RuntimeRequestKind.BROKER_REQUEST_SENT)
    object.__setattr__(request, "command_id", COMMAND_ID)
    object.__setattr__(request, "correlation_id", CORRELATION_ID)
    object.__setattr__(request, "idempotency_key", IDEMPOTENCY_KEY)
    object.__setattr__(request, "expected_revision", StateRevision(4))
    object.__setattr__(request, "actor_type", ActorType.APPLICATION)
    object.__setattr__(request, "occurred_at", OCCURRED_AT)
    object.__setattr__(request, "order_intent", order())
    object.__setattr__(request, "satisfied_guards", frozenset())
    object.__setattr__(request, "object_reference", "broker-request-f4a-001")
    object.__setattr__(request, "reason_code", None)
    object.__setattr__(request, "metadata", ())
    return request


def legacy_decision(**overrides: Any) -> LegacyPaperDecision:
    values: dict[str, Any] = {
        "environment": PaperIntegrationEnvironment.PAPER,
        "legacy_decision_id": "legacy-decision-f4a-001",
        "runtime_request_id": RUNTIME_REQUEST_ID,
        "qualification_run_id": RUN_ID,
        "command_id": COMMAND_ID,
        "correlation_id": CORRELATION_ID,
        "idempotency_key": IDEMPOTENCY_KEY,
        "expected_revision": StateRevision(4),
        "decision_type": LegacyPaperDecisionType.REQUEST_SUBMISSION,
        "action_type": LegacyPaperActionType.SUBMIT_ORDER,
        "order_intent": order(),
        "approved": True,
    }
    values.update(overrides)
    return LegacyPaperDecision(**values)


def shadow_request(
    *,
    request: PaperRuntimeRequest | None = None,
    legacy: LegacyPaperDecision | None = None,
) -> PaperQualificationShadowRequest:
    return PaperQualificationShadowRequest(
        runtime_request=request or runtime_request(),
        legacy_decision=legacy or legacy_decision(),
    )


def shadow_result(
    *,
    status: ShadowComparisonStatus = ShadowComparisonStatus.MATCH,
    classifications: tuple[ShadowMismatchClassification, ...] = (),
    action: RuntimeActionKind | None = RuntimeActionKind.REQUEST_BROKER_SUBMISSION,
    next_revision: StateRevision | None = StateRevision(5),
    transition_id: str | None = "PQ-TRN-009",
    request: PaperQualificationShadowRequest | None = None,
) -> PaperQualificationShadowResult:
    shadow = request or shadow_request()
    mismatches = tuple(
        ShadowMismatch(classification, classification.value.lower(), "safe-reason")
        for classification in classifications
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
        previous_revision=shadow.runtime_request.expected_revision,
        next_revision=next_revision,
        legacy_action_type=shadow.legacy_decision.action_type,
        qualification_action_type=action,
        qualification_state=QualificationState.SUBMITTED,
        qualification_result=QualificationResult.PENDING,
        replayed=False,
        safe_operator_summary="safe shadow summary",
        action_executed=False,
        legacy_behavior_changed=False,
    )


def boundary_request(
    *,
    shadow: PaperQualificationShadowRequest | None = None,
    **overrides: Any,
) -> QualificationRuntimeBoundaryRequest:
    values: dict[str, Any] = {"shadow_request": shadow or shadow_request()}
    values.update(overrides)
    return QualificationRuntimeBoundaryRequest(**values)


def unsafe_boundary_request(
    *,
    shadow: PaperQualificationShadowRequest,
    mode: object = QualificationRuntimeBoundaryMode.SHADOW_ONLY,
    legacy_authoritative: bool = True,
    execution_authorized: bool = False,
) -> QualificationRuntimeBoundaryRequest:
    request = object.__new__(QualificationRuntimeBoundaryRequest)
    object.__setattr__(request, "shadow_request", shadow)
    object.__setattr__(request, "mode", mode)
    object.__setattr__(request, "boundary_invocation_id", "boundary-f4a-unsafe")
    object.__setattr__(request, "source_identifier", "paper-runtime-shadow-boundary")
    object.__setattr__(
        request,
        "legacy_behavior_authoritative",
        legacy_authoritative,
    )
    object.__setattr__(request, "execution_authorized", execution_authorized)
    object.__setattr__(request, "metadata", ())
    return request


def evaluate(
    output: PaperQualificationShadowResult | None = None,
    *,
    request: QualificationRuntimeBoundaryRequest | None = None,
    error: Exception | None = None,
) -> tuple[QualificationRuntimeIntegrationBoundary, ControlledRunner, Any]:
    runner = ControlledRunner(output or shadow_result(), error=error)
    boundary = QualificationRuntimeIntegrationBoundary(runner)
    result = boundary.evaluate_shadow(request or boundary_request())
    return boundary, runner, result


def test_boundary_constructed_with_injected_shadow_runner() -> None:
    runner = ControlledRunner(shadow_result())

    boundary = QualificationRuntimeIntegrationBoundary(runner)

    assert boundary is not None


def test_boundary_rejects_non_runner_dependency() -> None:
    with pytest.raises(TypeError):
        QualificationRuntimeIntegrationBoundary(object())  # type: ignore[arg-type]


def test_valid_paper_shadow_request_is_accepted() -> None:
    _, runner, result = evaluate()

    assert len(runner.requests) == 1
    assert result.boundary_status is QualificationRuntimeBoundaryStatus.SHADOW_MATCH
    assert result.action_executed is False
    assert result.legacy_behavior_authoritative is True
    assert result.legacy_behavior_changed is False
    assert result.runtime_connected is False


def test_boundary_request_and_result_are_immutable() -> None:
    request = boundary_request()
    result = evaluate(request=request)[2]

    with pytest.raises(FrozenInstanceError):
        request.source_identifier = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.safe_summary = "changed"  # type: ignore[misc]


def test_boundary_request_constructor_rejects_invalid_shadow_request() -> None:
    with pytest.raises(BoundaryInputValidationError):
        QualificationRuntimeBoundaryRequest(
            shadow_request=object(),  # type: ignore[arg-type]
        )


def test_boundary_request_constructor_rejects_execution_authority_inputs() -> None:
    with pytest.raises(BoundaryInputValidationError):
        QualificationRuntimeBoundaryRequest(
            shadow_request=shadow_request(),
            legacy_behavior_authoritative=False,
        )
    with pytest.raises(BoundaryInputValidationError):
        QualificationRuntimeBoundaryRequest(
            shadow_request=shadow_request(),
            execution_authorized=True,
        )


def test_boundary_request_constructor_rejects_unsafe_identifiers_and_metadata() -> None:
    with pytest.raises(BoundaryInputValidationError):
        QualificationRuntimeBoundaryRequest(
            shadow_request=shadow_request(),
            source_identifier=" ",
        )
    with pytest.raises(BoundaryInputValidationError):
        QualificationRuntimeBoundaryRequest(
            shadow_request=shadow_request(),
            metadata=(("safe", ("SENTINEL_BOUNDARY_TOKEN_DO_NOT_EXPOSE",)),),
        )


@pytest.mark.parametrize(
    "environment",
    [PaperIntegrationEnvironment.LIVE, "UNKNOWN", None],
)
def test_non_paper_environment_rejected_before_runner_call(environment: object) -> None:
    shadow = shadow_request(request=unsafe_runtime_request(environment))
    runner = ControlledRunner(shadow_result(request=shadow))
    boundary = QualificationRuntimeIntegrationBoundary(runner)

    with pytest.raises(PaperEnvironmentRequiredError):
        boundary.evaluate_shadow(unsafe_boundary_request(shadow=shadow))

    assert runner.requests == []


def test_environment_mismatch_rejected_before_runner_call() -> None:
    shadow = shadow_request(
        legacy=legacy_decision(environment=PaperIntegrationEnvironment.LIVE)
    )
    runner = ControlledRunner(shadow_result(request=shadow))
    boundary = QualificationRuntimeIntegrationBoundary(runner)

    with pytest.raises(PaperEnvironmentRequiredError):
        boundary.evaluate_shadow(unsafe_boundary_request(shadow=shadow))

    assert runner.requests == []


@pytest.mark.parametrize("mode", ["EXECUTE", None])
def test_non_shadow_mode_rejected_before_runner_call(mode: object) -> None:
    runner = ControlledRunner(shadow_result())
    boundary = QualificationRuntimeIntegrationBoundary(runner)

    with pytest.raises(BoundaryModeError):
        boundary.evaluate_shadow(
            unsafe_boundary_request(shadow=shadow_request(), mode=mode)
        )

    assert runner.requests == []


def test_execution_authorization_and_legacy_deauthority_rejected() -> None:
    runner = ControlledRunner(shadow_result())
    boundary = QualificationRuntimeIntegrationBoundary(runner)

    with pytest.raises(BoundaryInputValidationError):
        boundary.evaluate_shadow(
            unsafe_boundary_request(
                shadow=shadow_request(),
                legacy_authoritative=False,
            )
        )
    with pytest.raises(BoundaryInputValidationError):
        boundary.evaluate_shadow(
            unsafe_boundary_request(
                shadow=shadow_request(),
                execution_authorized=True,
            )
        )
    assert runner.requests == []


def test_identity_fields_are_preserved() -> None:
    request = boundary_request()
    _, _, result = evaluate(request=request)

    assert result.boundary_invocation_id == request.boundary_invocation_id
    assert (
        result.shadow_result.shadow_invocation_id
        == request.shadow_request.shadow_invocation_id
    )
    assert result.runtime_request_id == RUNTIME_REQUEST_ID
    assert result.qualification_run_id == RUN_ID
    assert result.command_id == COMMAND_ID
    assert result.correlation_id == CORRELATION_ID
    assert result.idempotency_key == IDEMPOTENCY_KEY
    assert result.expected_revision == 4
    assert result.previous_revision == 4
    assert result.next_revision == 5
    assert result.transition_id == "PQ-TRN-009"


def test_boundary_identity_is_deterministic_and_sensitive_to_material_fields() -> None:
    first = boundary_request()
    second = boundary_request()
    changed = boundary_request(source_identifier="different-source")

    assert first.boundary_invocation_id == second.boundary_invocation_id
    assert first.boundary_invocation_id.startswith("qib-")
    assert first.boundary_invocation_id != changed.boundary_invocation_id
    assert (
        derive_boundary_invocation_id(
            first.shadow_request,
            first.source_identifier,
        )
        == first.boundary_invocation_id
    )


def test_input_identity_mismatch_prevents_runner_invocation() -> None:
    shadow = shadow_request(
        legacy=legacy_decision(correlation_id=CorrelationId("other-corr"))
    )
    runner = ControlledRunner(shadow_result(request=shadow))
    boundary = QualificationRuntimeIntegrationBoundary(runner)

    with pytest.raises(BoundaryIdentityContinuityError):
        boundary.evaluate_shadow(boundary_request(shadow=shadow))

    assert runner.requests == []


@pytest.mark.parametrize(
    "legacy_overrides",
    [
        {"runtime_request_id": "other-runtime"},
        {"qualification_run_id": QualificationRunId("other-run")},
        {"command_id": CommandId("other-command")},
        {"idempotency_key": IdempotencyKey("other-idem")},
        {"expected_revision": StateRevision(3)},
    ],
)
def test_input_identity_mismatch_fields_prevent_runner_invocation(
    legacy_overrides: dict[str, object],
) -> None:
    shadow = shadow_request(legacy=legacy_decision(**legacy_overrides))
    runner = ControlledRunner(shadow_result(request=shadow))
    boundary = QualificationRuntimeIntegrationBoundary(runner)

    with pytest.raises(BoundaryIdentityContinuityError):
        boundary.evaluate_shadow(boundary_request(shadow=shadow))

    assert runner.requests == []


def test_result_identity_mismatch_fails_safely_without_retry() -> None:
    good_shadow = shadow_request()
    bad_legacy = legacy_decision(runtime_request_id="other-runtime")
    bad_result = shadow_result(request=good_shadow)
    object.__setattr__(bad_result, "legacy_decision", bad_legacy)
    runner = ControlledRunner(bad_result)
    boundary = QualificationRuntimeIntegrationBoundary(runner)

    with pytest.raises(BoundaryResultValidationError):
        boundary.evaluate_shadow(boundary_request(shadow=good_shadow))

    assert len(runner.requests) == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("shadow_invocation_id", "other-shadow"),
        ("qualification_run_id", QualificationRunId("other-run")),
        ("command_id", CommandId("other-command")),
        ("correlation_id", CorrelationId("other-corr")),
        ("idempotency_key", IdempotencyKey("other-idem")),
        ("previous_revision", StateRevision(3)),
        ("action_executed", True),
        ("legacy_behavior_changed", True),
    ],
)
def test_result_continuity_mismatch_fields_fail_safely(
    field: str,
    value: object,
) -> None:
    output = shadow_result()
    object.__setattr__(output, field, value)
    runner = ControlledRunner(output)
    boundary = QualificationRuntimeIntegrationBoundary(runner)

    with pytest.raises(BoundaryResultValidationError):
        boundary.evaluate_shadow(boundary_request())

    assert len(runner.requests) == 1


@pytest.mark.parametrize(
    ("shadow_status", "boundary_status"),
    [
        (ShadowComparisonStatus.MATCH, QualificationRuntimeBoundaryStatus.SHADOW_MATCH),
        (
            ShadowComparisonStatus.MATCH_WITH_NONCONSEQUENTIAL_DIFFERENCE,
            QualificationRuntimeBoundaryStatus.SHADOW_MATCH,
        ),
        (
            ShadowComparisonStatus.MISMATCH,
            QualificationRuntimeBoundaryStatus.SHADOW_MISMATCH,
        ),
        (
            ShadowComparisonStatus.INCOMPARABLE,
            QualificationRuntimeBoundaryStatus.SHADOW_INCOMPARABLE,
        ),
        (
            ShadowComparisonStatus.QUALIFICATION_ERROR,
            QualificationRuntimeBoundaryStatus.SHADOW_QUALIFICATION_ERROR,
        ),
        (
            ShadowComparisonStatus.INVALID_SHADOW_INPUT,
            QualificationRuntimeBoundaryStatus.REJECTED_INVALID_INPUT,
        ),
    ],
)
def test_shadow_status_maps_deterministically(
    shadow_status: ShadowComparisonStatus,
    boundary_status: QualificationRuntimeBoundaryStatus,
) -> None:
    output = shadow_result(status=shadow_status)

    assert boundary_status_from_shadow(shadow_status) is boundary_status
    assert evaluate(output)[2].boundary_status is boundary_status


def test_mismatch_classifications_are_preserved_exactly() -> None:
    classifications = (
        ShadowMismatchClassification.ACTION_KIND_MISMATCH,
        ShadowMismatchClassification.ORDER_INTENT_MISMATCH,
    )
    result = evaluate(
        shadow_result(
            status=ShadowComparisonStatus.MISMATCH,
            classifications=classifications,
        )
    )[2]

    assert result.mismatch_classifications == classifications
    assert result.shadow_result.classifications == classifications


@pytest.mark.parametrize(
    "action",
    [
        RuntimeActionKind.REQUEST_BROKER_SUBMISSION,
        RuntimeActionKind.REQUEST_BROKER_CANCELLATION,
        RuntimeActionKind.START_RECONCILIATION,
        RuntimeActionKind.BLOCK_CONSEQUENTIAL_ACTION,
        RuntimeActionKind.NO_RUNTIME_ACTION_REQUIRED,
    ],
)
def test_described_actions_remain_non_executed(action: RuntimeActionKind) -> None:
    result = evaluate(shadow_result(action=action))[2]

    assert result.action_described is action
    assert result.action_executed is False
    assert result.legacy_behavior_authoritative is True


@pytest.mark.parametrize(
    "reason_code",
    ["STALE_REVISION", "IDEMPOTENCY_CONFLICT", "GUARD_FAILED", "INVALID_TRANSITION"],
)
def test_shadow_runner_failure_is_distinguishable_and_not_retried(
    reason_code: str,
) -> None:
    with pytest.raises(BoundaryShadowInvocationError) as error_info:
        evaluate(
            error=ShadowInputValidationError(
                reason_code=reason_code,
                safe_message="Safe shadow failure.",
            )
        )

    assert error_info.value.reason_code == reason_code
    runner = error_info.value.__cause__  # type: ignore[assignment]
    assert runner is not None


def test_shadow_runner_failure_invokes_runner_once() -> None:
    runner = ControlledRunner(
        error=ShadowInputValidationError(
            reason_code="STALE_REVISION",
            safe_message="Safe shadow failure.",
        )
    )
    boundary = QualificationRuntimeIntegrationBoundary(runner)

    with pytest.raises(BoundaryShadowInvocationError):
        boundary.evaluate_shadow(boundary_request())

    assert len(runner.requests) == 1


def test_shadow_error_status_does_not_alter_legacy_authority() -> None:
    result = evaluate(shadow_result(status=ShadowComparisonStatus.QUALIFICATION_ERROR))[
        2
    ]

    assert (
        result.boundary_status
        is QualificationRuntimeBoundaryStatus.SHADOW_QUALIFICATION_ERROR
    )
    assert result.legacy_behavior_authoritative is True
    assert result.legacy_behavior_changed is False


def test_runner_shadow_error_is_wrapped_without_retry() -> None:
    runner = ControlledRunner(
        error=ShadowInputValidationError(
            reason_code="STALE_REVISION",
            safe_message="Stale revision.",
        )
    )
    boundary = QualificationRuntimeIntegrationBoundary(runner)

    with pytest.raises(BoundaryShadowInvocationError) as error_info:
        boundary.evaluate_shadow(boundary_request())

    assert error_info.value.reason_code == "STALE_REVISION"
    assert len(runner.requests) == 1


def test_secret_markers_absent_from_result_error_and_identity() -> None:
    sentinel = "SENTINEL_BOUNDARY_SECRET_DO_NOT_EXPOSE"
    result = evaluate()[2]

    with pytest.raises(BoundaryInputValidationError) as error_info:
        boundary_request(source_identifier=sentinel)

    rendered = "\n".join(
        (repr(result), str(error_info.value), result.boundary_invocation_id)
    )
    assert sentinel not in rendered
    assert "SENTINEL_BOUNDARY_TOKEN_DO_NOT_EXPOSE" not in rendered
    assert "SENTINEL_BOUNDARY_PASSWORD_DO_NOT_EXPOSE" not in rendered


def test_inputs_and_shadow_result_are_not_mutated() -> None:
    request = boundary_request()
    output = shadow_result(request=request.shadow_request)
    before_request = repr(request)
    before_output = repr(output)

    evaluate(output, request=request)

    assert repr(request) == before_request
    assert repr(output) == before_output


def test_boundary_no_external_effects(monkeypatch: pytest.MonkeyPatch) -> None:
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

    matching = evaluate()[2]
    mismatch = evaluate(shadow_result(status=ShadowComparisonStatus.MISMATCH))[2]
    incomparable = evaluate(shadow_result(status=ShadowComparisonStatus.INCOMPARABLE))[
        2
    ]
    qualification_error = evaluate(
        shadow_result(status=ShadowComparisonStatus.QUALIFICATION_ERROR)
    )[2]
    replay = evaluate(
        shadow_result(
            status=ShadowComparisonStatus.MATCH_WITH_NONCONSEQUENTIAL_DIFFERENCE
        )
    )[2]

    assert matching.action_executed is False
    assert mismatch.action_executed is False
    assert incomparable.action_executed is False
    assert qualification_error.action_executed is False
    assert replay.action_executed is False


def test_default_qualification_scenario_can_pass_through_boundary() -> None:
    repository = InMemoryQualificationRunRepository()
    recorder = RecordingQualificationEvidenceRecorder()
    service = PaperQualificationService(repository, recorder)
    runner = PaperQualificationShadowRunner(PaperQualificationFacade(service))
    boundary = QualificationRuntimeIntegrationBoundary(runner)
    scenario = default_positive_scenario()
    transitions: list[str] = []
    revisions: list[int] = []
    actions_executed: list[bool] = []
    legacy_authority: list[bool] = []
    final_result = None

    for step in scenario.steps:
        runtime = runtime_request(
            runtime_request_id=f"runtime-{step.step_id}",
            qualification_run_id=RUN_ID,
            qualification_scenario_id=scenario.scenario_id,
            request_kind=RuntimeRequestKind(step.event_type.value),
            command_id=step.command_id,
            idempotency_key=step.idempotency_key,
            expected_revision=step.expected_revision,
            actor_type=step.actor_type,
            satisfied_guards=step.guards,
            object_reference=step.object_reference,
        )
        legacy = legacy_decision(
            legacy_decision_id=f"legacy-{step.step_id}",
            runtime_request_id=runtime.runtime_request_id,
            command_id=runtime.command_id,
            idempotency_key=runtime.idempotency_key,
            expected_revision=runtime.expected_revision,
            decision_type=LegacyPaperDecisionType.NO_ACTION,
            action_type=LegacyPaperActionType.NONE,
            approved=None,
            order_intent=None,
        )
        result = boundary.evaluate_shadow(
            QualificationRuntimeBoundaryRequest(
                shadow_request=PaperQualificationShadowRequest(
                    runtime_request=runtime,
                    legacy_decision=legacy,
                )
            )
        )
        transitions.append(result.transition_id or "")
        revisions.append(result.next_revision or 0)
        actions_executed.append(result.action_executed)
        legacy_authority.append(result.legacy_behavior_authoritative)
        final_result = result

    assert transitions == [
        "PQ-TRN-001",
        "PQ-TRN-002",
        "PQ-TRN-005",
        "PQ-TRN-006",
        "PQ-TRN-009",
        "PQ-TRN-010",
        "PQ-TRN-011",
        "PQ-TRN-015",
        "PQ-TRN-017",
        "PQ-TRN-030",
    ]
    assert revisions == list(range(1, 11))
    assert actions_executed == [False] * 10
    assert legacy_authority == [True] * 10
    assert final_result is not None
    assert (
        final_result.shadow_result.qualification_state is QualificationState.QUALIFIED
    )
    assert final_result.shadow_result.qualification_result is QualificationResult.PASSED


def test_repeated_deterministic_evaluation_produces_equivalent_results() -> None:
    output = shadow_result()

    first = evaluate(output)[2]
    second = evaluate(output)[2]

    assert first.boundary_invocation_id == second.boundary_invocation_id
    assert first.boundary_status == second.boundary_status
    assert first.mismatch_classifications == second.mismatch_classifications
