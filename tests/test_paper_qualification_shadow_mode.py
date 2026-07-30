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
    RetryClassification,
    SideEffectIntent,
    SideEffectIntentType,
    StateRevision,
    TransitionDecision,
    default_positive_scenario,
)
from volcanoes.application.qualification.contracts import PaperQualificationRun
from volcanoes.application.qualification.integration import (
    FacadeServiceInvocationError,
    IntegrationOrderType,
    IntegrationTimeInForce,
    LegacyPaperActionType,
    LegacyPaperDecision,
    LegacyPaperDecisionType,
    PaperEnvironmentRequiredError,
    PaperIntegrationEnvironment,
    PaperQualificationFacade,
    PaperQualificationFacadeResult,
    PaperQualificationShadowRequest,
    PaperQualificationShadowRunner,
    PaperRuntimeRequest,
    RuntimeActionKind,
    RuntimeActionRequest,
    RuntimeRequestKind,
    SafeOrderIntent,
    ShadowComparisonStatus,
    ShadowIdentityContinuityError,
    ShadowInputValidationError,
    ShadowMismatchClassification,
    derive_shadow_invocation_id,
)
from volcanoes.application.qualification.service import (
    ExecutionPlanKind,
    PaperQualificationService,
    QualificationApplicationResult,
    QualificationExecutionPlan,
)

RUN_ID = QualificationRunId("pq-run-f3-001")
SCENARIO_ID = QualificationScenarioId("PQ-SCN-005")
COMMAND_ID = CommandId("cmd-f3-001")
CORRELATION_ID = CorrelationId("corr-f3-001")
IDEMPOTENCY_KEY = IdempotencyKey("idem-f3-001")
RUNTIME_REQUEST_ID = "runtime-request-f3-001"
OCCURRED_AT = datetime(2026, 7, 29, 16, 0, tzinfo=UTC)


class ControlledFacade(PaperQualificationFacade):
    def __init__(
        self,
        result: PaperQualificationFacadeResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.requests: list[PaperRuntimeRequest] = []

    def handle(self, request: PaperRuntimeRequest) -> PaperQualificationFacadeResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("test facade result was not configured")
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
        "object_reference": "broker-request-f3-001",
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
    object.__setattr__(request, "object_reference", "broker-request-f3-001")
    object.__setattr__(request, "reason_code", None)
    object.__setattr__(request, "metadata", ())
    return request


def legacy_decision(**overrides: Any) -> LegacyPaperDecision:
    values: dict[str, Any] = {
        "environment": PaperIntegrationEnvironment.PAPER,
        "legacy_decision_id": "legacy-decision-f3-001",
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
    **overrides: Any,
) -> PaperQualificationShadowRequest:
    values: dict[str, Any] = {
        "runtime_request": request or runtime_request(),
        "legacy_decision": legacy or legacy_decision(),
    }
    values.update(overrides)
    return PaperQualificationShadowRequest(**values)


def transition_decision(
    *,
    previous_revision: StateRevision = StateRevision(4),
    next_revision: StateRevision = StateRevision(5),
    transition_id: str = "PQ-TRN-009",
) -> TransitionDecision:
    return TransitionDecision(
        accepted=True,
        transition_id=transition_id,
        previous_state=QualificationState.SUBMISSION_PENDING,
        next_state=QualificationState.SUBMITTED,
        previous_revision=previous_revision,
        next_revision=next_revision,
        result=QualificationResult.PENDING,
        reason_code="BROKER_REQUEST_SENT",
        safe_message="Broker request was sent.",
        retry_classification=RetryClassification.IDEMPOTENT_EXTERNAL_RETRY_ONLY,
    )


def execution_plan(
    *,
    side_effects: tuple[SideEffectIntent, ...] = (
        SideEffectIntent(
            SideEffectIntentType.SEND_BROKER_REQUEST,
            "request-broker-submission",
        ),
    ),
    previous_revision: StateRevision = StateRevision(4),
    next_revision: StateRevision = StateRevision(5),
    transition_id: str = "PQ-TRN-009",
) -> QualificationExecutionPlan:
    return QualificationExecutionPlan(
        qualification_run_id=RUN_ID,
        transition_id=transition_id,
        source_state=QualificationState.SUBMISSION_PENDING,
        destination_state=QualificationState.SUBMITTED,
        previous_revision=previous_revision,
        next_revision=next_revision,
        side_effect_intents=side_effects,
        evidence_intents=(),
        retry_classification=RetryClassification.IDEMPOTENT_EXTERNAL_RETRY_ONLY,
        reconciliation_required=False,
        operator_message="broker-request-sent",
        correlation_id=CORRELATION_ID,
        command_id=COMMAND_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        plan_kinds=(ExecutionPlanKind.BROKER_ACTION_PROPOSED,),
    )


def application_result(
    *,
    plan: QualificationExecutionPlan | None = None,
    decision: TransitionDecision | None = None,
    replayed: bool = False,
    state: QualificationState = QualificationState.SUBMITTED,
    result: QualificationResult = QualificationResult.PENDING,
) -> QualificationApplicationResult:
    return QualificationApplicationResult(
        qualification_run_id=RUN_ID,
        accepted=True,
        code="BROKER_REQUEST_SENT",
        safe_message="Broker request was sent.",
        previous_run=PaperQualificationRun(
            qualification_run_id=RUN_ID,
            qualification_scenario_id=SCENARIO_ID,
            correlation_id=CORRELATION_ID,
            state=QualificationState.SUBMISSION_PENDING,
            result=QualificationResult.PENDING,
            state_revision=StateRevision(4),
        ),
        resulting_run=PaperQualificationRun(
            qualification_run_id=RUN_ID,
            qualification_scenario_id=SCENARIO_ID,
            correlation_id=CORRELATION_ID,
            state=state,
            result=result,
            state_revision=StateRevision(5),
        ),
        transition_decision=decision or transition_decision(),
        execution_plan=plan or execution_plan(),
        replayed=replayed,
    )


def runtime_action(
    action_kind: RuntimeActionKind = RuntimeActionKind.REQUEST_BROKER_SUBMISSION,
    *,
    intent: SafeOrderIntent | None = None,
    source_revision: StateRevision = StateRevision(4),
) -> RuntimeActionRequest:
    return RuntimeActionRequest(
        environment=PaperIntegrationEnvironment.PAPER,
        action_request_id="action-request-f3-001",
        action_kind=action_kind,
        qualification_run_id=RUN_ID,
        command_id=COMMAND_ID,
        correlation_id=CORRELATION_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        source_transition_id="PQ-TRN-009",
        source_revision=source_revision,
        safe_operator_message="broker-request-sent",
        order_intent=intent if intent is not None else order(),
    )


def facade_result(
    action_kind: RuntimeActionKind = RuntimeActionKind.REQUEST_BROKER_SUBMISSION,
    *,
    intent: SafeOrderIntent | None = None,
    replayed: bool = False,
    state: QualificationState = QualificationState.SUBMITTED,
    result: QualificationResult = QualificationResult.PENDING,
) -> PaperQualificationFacadeResult:
    return PaperQualificationFacadeResult(
        qualification_run_id=RUN_ID,
        application_result=application_result(
            replayed=replayed, state=state, result=result
        ),
        runtime_action=runtime_action(action_kind, intent=intent),
        command_id=COMMAND_ID,
        correlation_id=CORRELATION_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        transition_id="PQ-TRN-009",
        previous_revision=StateRevision(4),
        next_revision=StateRevision(5),
        qualification_state=state,
        qualification_result=result,
        replayed=replayed,
        safe_operator_message="broker-request-sent",
        action_executed=False,
    )


def evaluate(
    facade_output: PaperQualificationFacadeResult | None = None,
    *,
    request: PaperQualificationShadowRequest | None = None,
    error: Exception | None = None,
) -> tuple[PaperQualificationShadowRunner, ControlledFacade, Any]:
    facade = ControlledFacade(facade_output or facade_result(), error=error)
    runner = PaperQualificationShadowRunner(facade)
    result = runner.evaluate(request or shadow_request())
    return runner, facade, result


def test_shadow_runner_constructed_with_injected_facade() -> None:
    facade = ControlledFacade(facade_result())

    runner = PaperQualificationShadowRunner(facade)

    assert runner is not None


def test_shadow_runner_rejects_non_facade_dependency() -> None:
    with pytest.raises(TypeError):
        PaperQualificationShadowRunner(object())  # type: ignore[arg-type]


def test_valid_paper_shadow_request_is_accepted_and_facade_called_once() -> None:
    _, facade, result = evaluate()

    assert len(facade.requests) == 1
    assert result.comparison_status is ShadowComparisonStatus.MATCH
    assert result.action_executed is False
    assert result.legacy_behavior_changed is False


@pytest.mark.parametrize(
    "environment", [PaperIntegrationEnvironment.LIVE, "UNKNOWN", None]
)
def test_non_paper_runtime_request_rejected_before_facade_call(
    environment: object,
) -> None:
    facade = ControlledFacade(facade_result())
    runner = PaperQualificationShadowRunner(facade)

    with pytest.raises(PaperEnvironmentRequiredError):
        runner.evaluate(shadow_request(request=unsafe_runtime_request(environment)))

    assert facade.requests == []


def test_live_legacy_decision_rejected_before_facade_call() -> None:
    facade = ControlledFacade(facade_result())
    runner = PaperQualificationShadowRunner(facade)

    with pytest.raises(PaperEnvironmentRequiredError):
        runner.evaluate(
            shadow_request(
                legacy=legacy_decision(environment=PaperIntegrationEnvironment.LIVE)
            )
        )

    assert facade.requests == []


def test_identity_mismatch_prevents_facade_invocation() -> None:
    facade = ControlledFacade(facade_result())
    runner = PaperQualificationShadowRunner(facade)

    with pytest.raises(ShadowIdentityContinuityError):
        runner.evaluate(
            shadow_request(
                legacy=legacy_decision(correlation_id=CorrelationId("other-corr"))
            )
        )

    assert facade.requests == []


def test_shadow_result_is_immutable_and_identity_continuity_is_preserved() -> None:
    _, _, result = evaluate()

    with pytest.raises(FrozenInstanceError):
        result.safe_operator_summary = "changed"  # type: ignore[misc]
    assert result.command_id == COMMAND_ID
    assert result.correlation_id == CORRELATION_ID
    assert result.idempotency_key == IDEMPOTENCY_KEY
    assert result.qualification_run_id == RUN_ID
    assert result.previous_revision == 4
    assert result.next_revision == 5


def test_shadow_identity_is_deterministic_and_sensitive_to_material_fields() -> None:
    request_one = shadow_request()
    request_two = shadow_request()
    changed = shadow_request(
        legacy=legacy_decision(legacy_decision_id="legacy-decision-f3-002")
    )

    assert request_one.shadow_invocation_id == request_two.shadow_invocation_id
    assert request_one.shadow_invocation_id.startswith("qis-")
    assert request_one.shadow_invocation_id != changed.shadow_invocation_id
    assert (
        derive_shadow_invocation_id(
            request_one.runtime_request,
            request_one.legacy_decision,
        )
        == request_one.shadow_invocation_id
    )


@pytest.mark.parametrize(
    ("legacy_type", "legacy_action", "qualification_action", "status"),
    [
        (
            LegacyPaperDecisionType.REQUEST_SUBMISSION,
            LegacyPaperActionType.SUBMIT_ORDER,
            RuntimeActionKind.REQUEST_BROKER_SUBMISSION,
            ShadowComparisonStatus.MATCH,
        ),
        (
            LegacyPaperDecisionType.PROCEED,
            LegacyPaperActionType.SUBMIT_ORDER,
            RuntimeActionKind.BLOCK_CONSEQUENTIAL_ACTION,
            ShadowComparisonStatus.MISMATCH,
        ),
        (
            LegacyPaperDecisionType.BLOCK,
            LegacyPaperActionType.BLOCK_CONSEQUENTIAL_ACTION,
            RuntimeActionKind.REQUEST_BROKER_SUBMISSION,
            ShadowComparisonStatus.MISMATCH,
        ),
        (
            LegacyPaperDecisionType.NO_ACTION,
            LegacyPaperActionType.NONE,
            RuntimeActionKind.FINALIZE_WITHOUT_EXTERNAL_EFFECT,
            ShadowComparisonStatus.MATCH,
        ),
        (
            LegacyPaperDecisionType.REQUEST_CANCELLATION,
            LegacyPaperActionType.CANCEL_ORDER,
            RuntimeActionKind.REQUEST_BROKER_CANCELLATION,
            ShadowComparisonStatus.MATCH,
        ),
        (
            LegacyPaperDecisionType.REQUEST_RECONCILIATION,
            LegacyPaperActionType.RECONCILE,
            RuntimeActionKind.START_RECONCILIATION,
            ShadowComparisonStatus.MATCH,
        ),
        (
            LegacyPaperDecisionType.EMERGENCY_STOP,
            LegacyPaperActionType.EMERGENCY_STOP,
            RuntimeActionKind.REQUEST_BROKER_SUBMISSION,
            ShadowComparisonStatus.MISMATCH,
        ),
    ],
)
def test_action_semantics_are_compared_deterministically(
    legacy_type: LegacyPaperDecisionType,
    legacy_action: LegacyPaperActionType,
    qualification_action: RuntimeActionKind,
    status: ShadowComparisonStatus,
) -> None:
    request = shadow_request(
        legacy=legacy_decision(
            decision_type=legacy_type,
            action_type=legacy_action,
            approved=legacy_type is not LegacyPaperDecisionType.BLOCK,
        )
    )

    _, _, result = evaluate(facade_result(qualification_action), request=request)

    assert result.comparison_status is status


@pytest.mark.parametrize(
    ("changed_order", "expected_field"),
    [
        (order(symbol="MSFT"), "symbol"),
        (order(quantity=2), "quantity"),
        (order(order_type=IntegrationOrderType.BRACKET_LIMIT), "order_type"),
        (order(limit_price=Decimal("101")), "limit_price"),
        (order(time_in_force=IntegrationTimeInForce.GTC), "time_in_force"),
    ],
)
def test_order_intent_mismatches_are_specific(
    changed_order: SafeOrderIntent,
    expected_field: str,
) -> None:
    _, _, result = evaluate(facade_result(intent=changed_order))

    assert result.comparison_status is ShadowComparisonStatus.MISMATCH
    assert ShadowMismatchClassification.ORDER_INTENT_MISMATCH in result.classifications
    assert result.mismatches[0].field == expected_field


def test_insufficient_order_facts_are_incomparable_not_match() -> None:
    request = shadow_request(
        request=runtime_request(order_intent=None),
        legacy=legacy_decision(order_intent=None),
    )

    _, _, result = evaluate(
        facade_result(RuntimeActionKind.REQUEST_BROKER_SUBMISSION, intent=None),
        request=request,
    )

    assert result.comparison_status is ShadowComparisonStatus.INCOMPARABLE
    assert (
        ShadowMismatchClassification.INSUFFICIENT_COMPARISON_FACTS
        in result.classifications
    )


def test_replay_difference_is_nonconsequential_when_other_facts_match() -> None:
    request = shadow_request(legacy=legacy_decision(metadata=(("replay", True),)))

    _, _, result = evaluate(facade_result(replayed=False), request=request)

    assert (
        result.comparison_status
        is ShadowComparisonStatus.MATCH_WITH_NONCONSEQUENTIAL_DIFFERENCE
    )
    assert ShadowMismatchClassification.REPLAY_MISMATCH in result.classifications


@pytest.mark.parametrize(
    ("error_code", "error_message"),
    [
        ("STALE_REVISION", "Stale revision."),
        ("IDEMPOTENCY_CONFLICT", "Idempotency conflict."),
        ("GUARD_FAILED", "Guard failed."),
        ("INVALID_TRANSITION", "Invalid transition."),
    ],
)
def test_facade_failures_are_safe_distinguishable_and_not_retried(
    error_code: str,
    error_message: str,
) -> None:
    _, facade, result = evaluate(
        error=FacadeServiceInvocationError(
            reason_code=error_code,
            safe_message=error_message,
        )
    )

    assert len(facade.requests) == 1
    assert result.comparison_status is ShadowComparisonStatus.QUALIFICATION_ERROR
    assert result.mismatches[0].safe_reason == error_code
    assert result.action_executed is False
    assert result.legacy_behavior_changed is False


def test_facade_result_identity_mismatch_raises_without_retry() -> None:
    bad_result = PaperQualificationFacadeResult(
        qualification_run_id=QualificationRunId("other-run"),
        application_result=application_result(),
        runtime_action=runtime_action(),
        command_id=COMMAND_ID,
        correlation_id=CORRELATION_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        transition_id="PQ-TRN-009",
        previous_revision=StateRevision(4),
        next_revision=StateRevision(5),
        qualification_state=QualificationState.SUBMITTED,
        qualification_result=QualificationResult.PENDING,
        replayed=False,
        safe_operator_message="broker-request-sent",
        action_executed=False,
    )
    facade = ControlledFacade(bad_result)
    runner = PaperQualificationShadowRunner(facade)

    with pytest.raises(ShadowIdentityContinuityError):
        runner.evaluate(shadow_request())

    assert len(facade.requests) == 1


def test_inconclusive_qualification_result_remains_incomparable() -> None:
    _, _, result = evaluate(
        facade_result(result=QualificationResult.INCONCLUSIVE),
    )

    assert result.comparison_status is ShadowComparisonStatus.INCOMPARABLE


def test_cancellation_request_is_not_equated_with_cancellation_confirmation() -> None:
    request = shadow_request(
        legacy=legacy_decision(
            decision_type=LegacyPaperDecisionType.REQUEST_CANCELLATION,
            action_type=LegacyPaperActionType.CANCEL_ORDER,
            approved=True,
        )
    )

    _, _, result = evaluate(
        facade_result(RuntimeActionKind.FINALIZE_WITHOUT_EXTERNAL_EFFECT),
        request=request,
    )

    assert result.comparison_status is ShadowComparisonStatus.MISMATCH
    assert ShadowMismatchClassification.CANCELLATION_MISMATCH in result.classifications


def test_broker_acknowledgment_is_not_equated_with_fill() -> None:
    request = shadow_request(
        request=runtime_request(request_kind=RuntimeRequestKind.BROKER_ACKNOWLEDGED),
        legacy=legacy_decision(
            decision_type=LegacyPaperDecisionType.NO_ACTION,
            action_type=LegacyPaperActionType.NONE,
        ),
    )

    _, _, result = evaluate(
        facade_result(
            RuntimeActionKind.FINALIZE_WITHOUT_EXTERNAL_EFFECT,
            state=QualificationState.ACKNOWLEDGED,
            result=QualificationResult.PENDING,
        ),
        request=request,
    )

    assert result.qualification_state is QualificationState.ACKNOWLEDGED
    assert result.qualification_result is QualificationResult.PENDING
    assert result.qualification_state is not QualificationState.FILLED


def test_secret_markers_are_absent_from_result_errors_and_identity() -> None:
    sentinel = "SENTINEL_SHADOW_SECRET_DO_NOT_EXPOSE"
    result = evaluate()[2]

    with pytest.raises(ShadowInputValidationError) as error_info:
        legacy_decision(reason_code=sentinel)

    rendered = "\n".join(
        (repr(result), str(error_info.value), result.shadow_invocation_id)
    )
    assert sentinel not in rendered
    assert "SENTINEL_SHADOW_TOKEN_DO_NOT_EXPOSE" not in rendered
    assert "SENTINEL_SHADOW_PASSWORD_DO_NOT_EXPOSE" not in rendered


def test_shadow_evaluation_does_not_mutate_inputs_or_facade_result() -> None:
    request = shadow_request()
    output = facade_result()
    before_request = repr(request)
    before_output = repr(output)

    evaluate(output, request=request)

    assert repr(request) == before_request
    assert repr(output) == before_output


def test_shadow_no_external_effects(
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

    matching = evaluate()[2]
    mismatch = evaluate(facade_result(RuntimeActionKind.BLOCK_CONSEQUENTIAL_ACTION))[2]
    incomparable = evaluate(
        facade_result(RuntimeActionKind.REQUEST_BROKER_SUBMISSION, intent=None),
        request=shadow_request(
            request=runtime_request(order_intent=None),
            legacy=legacy_decision(order_intent=None),
        ),
    )[2]
    failure = evaluate(
        error=FacadeServiceInvocationError(
            reason_code="STALE_REVISION",
            safe_message="Stale revision.",
        )
    )[2]
    replay = evaluate(
        facade_result(replayed=False),
        request=shadow_request(legacy=legacy_decision(metadata=(("replay", True),))),
    )[2]

    assert matching.action_executed is False
    assert mismatch.action_executed is False
    assert incomparable.action_executed is False
    assert failure.action_executed is False
    assert replay.action_executed is False


def test_default_qualification_scenario_can_be_evaluated_through_shadow_runner() -> (
    None
):
    repository = InMemoryQualificationRunRepository()
    recorder = RecordingQualificationEvidenceRecorder()
    service = PaperQualificationService(repository, recorder)
    runner = PaperQualificationShadowRunner(PaperQualificationFacade(service))
    scenario = default_positive_scenario()
    transitions: list[str] = []
    revisions: list[int] = []
    actions_executed: list[bool] = []
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
        result = runner.evaluate(
            PaperQualificationShadowRequest(
                runtime_request=runtime,
                legacy_decision=legacy,
            )
        )
        transitions.append(result.transition_id or "")
        revisions.append(result.next_revision or 0)
        actions_executed.append(result.action_executed)
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
    assert final_result is not None
    assert final_result.qualification_state is QualificationState.QUALIFIED
    assert final_result.qualification_result is QualificationResult.PASSED


def test_mismatch_classification_order_is_deterministic() -> None:
    result_one = evaluate(facade_result(intent=order(symbol="MSFT", quantity=2)))[2]
    result_two = evaluate(facade_result(intent=order(symbol="MSFT", quantity=2)))[2]

    assert result_one.classifications == result_two.classifications
    assert result_one.mismatches == result_two.mismatches
