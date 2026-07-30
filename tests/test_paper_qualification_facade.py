from __future__ import annotations

import builtins
import socket
import subprocess
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
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
    FacadeIdentityContinuityError,
    FacadeResultValidationError,
    FacadeServiceInvocationError,
    IntegrationOrderType,
    PaperEnvironmentRequiredError,
    PaperIntegrationEnvironment,
    PaperQualificationFacade,
    PaperRuntimeRequest,
    RuntimeActionKind,
    RuntimeRequestKind,
    SafeOrderIntent,
)
from volcanoes.application.qualification.integration import facade as facade_module
from volcanoes.application.qualification.service import (
    ApplicationCommandValidationError,
    ExecutionPlanKind,
    PaperQualificationService,
    QualificationApplicationCommand,
    QualificationApplicationResult,
    QualificationExecutionPlan,
)
from volcanoes.application.qualification import state_machine

RUN_ID = QualificationRunId("pq-run-f2-001")
SCENARIO_ID = QualificationScenarioId("PQ-SCN-005")
COMMAND_ID = CommandId("cmd-f2-001")
CORRELATION_ID = CorrelationId("corr-f2-001")
IDEMPOTENCY_KEY = IdempotencyKey("idem-f2-001")
OCCURRED_AT = datetime(2026, 7, 29, 14, 0, tzinfo=UTC)


class RecordingService(PaperQualificationService):
    def __init__(
        self,
        result: QualificationApplicationResult | None = None,
        error: Exception | None = None,
    ) -> None:
        super().__init__(
            InMemoryQualificationRunRepository(),
            RecordingQualificationEvidenceRecorder(),
        )
        self.result = result
        self.error = error
        self.commands: list[QualificationApplicationCommand] = []

    def execute(
        self,
        command: QualificationApplicationCommand,
    ) -> QualificationApplicationResult:
        self.commands.append(command)
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise AssertionError("test service result was not configured")
        return self.result


def runtime_request(**overrides: Any) -> PaperRuntimeRequest:
    values: dict[str, Any] = {
        "environment": PaperIntegrationEnvironment.PAPER,
        "runtime_request_id": "runtime-request-f2-001",
        "qualification_run_id": RUN_ID,
        "qualification_scenario_id": SCENARIO_ID,
        "request_kind": RuntimeRequestKind.OPERATOR_APPROVED,
        "command_id": COMMAND_ID,
        "correlation_id": CORRELATION_ID,
        "idempotency_key": IDEMPOTENCY_KEY,
        "expected_revision": StateRevision(3),
        "actor_type": ActorType.OPERATOR,
        "occurred_at": OCCURRED_AT,
        "order_intent": SafeOrderIntent(
            symbol="AAPL",
            quantity=1,
            order_type=IntegrationOrderType.LIMIT,
            limit_price=Decimal("100"),
        ),
        "satisfied_guards": frozenset(
            {
                Guard.PAPER_ENVIRONMENT,
                Guard.OPERATOR_APPROVAL_VALID,
                Guard.PLAN_CURRENT,
            }
        ),
        "object_reference": "approval-ref-f2-001",
    }
    values.update(overrides)
    return PaperRuntimeRequest(**values)


def transition_decision(
    *,
    previous_revision: StateRevision = StateRevision(3),
    next_revision: StateRevision = StateRevision(4),
    transition_id: str = "PQ-TRN-006",
) -> TransitionDecision:
    return TransitionDecision(
        accepted=True,
        transition_id=transition_id,
        previous_state=QualificationState.APPROVAL_PENDING,
        next_state=QualificationState.APPROVED,
        previous_revision=previous_revision,
        next_revision=next_revision,
        result=QualificationResult.PENDING,
        reason_code="APPROVED",
        safe_message="Operator approved qualification.",
        retry_classification=RetryClassification.SAFE_LOCAL_RETRY,
    )


def execution_plan(
    *,
    command_id: CommandId = COMMAND_ID,
    correlation_id: CorrelationId = CORRELATION_ID,
    idempotency_key: IdempotencyKey = IDEMPOTENCY_KEY,
    qualification_run_id: QualificationRunId = RUN_ID,
    previous_revision: StateRevision = StateRevision(3),
    next_revision: StateRevision = StateRevision(4),
    transition_id: str = "PQ-TRN-006",
    side_effects: tuple[SideEffectIntent, ...] = (),
) -> QualificationExecutionPlan:
    return QualificationExecutionPlan(
        qualification_run_id=qualification_run_id,
        transition_id=transition_id,
        source_state=QualificationState.APPROVAL_PENDING,
        destination_state=QualificationState.APPROVED,
        previous_revision=previous_revision,
        next_revision=next_revision,
        side_effect_intents=side_effects,
        evidence_intents=(),
        retry_classification=RetryClassification.SAFE_LOCAL_RETRY,
        reconciliation_required=False,
        operator_message="Operator approved qualification.",
        correlation_id=correlation_id,
        command_id=command_id,
        idempotency_key=idempotency_key,
        plan_kinds=(ExecutionPlanKind.NO_EXTERNAL_ACTION_REQUIRED,),
    )


def application_result(
    *,
    plan: QualificationExecutionPlan | None = None,
    decision: TransitionDecision | None = None,
    run_id: QualificationRunId = RUN_ID,
    replayed: bool = False,
    resulting_state: QualificationState = QualificationState.APPROVED,
    result_value: QualificationResult = QualificationResult.PENDING,
) -> QualificationApplicationResult:
    return QualificationApplicationResult(
        qualification_run_id=run_id,
        accepted=True,
        code="APPROVED",
        safe_message="Operator approved qualification.",
        previous_run=PaperQualificationRun(
            qualification_run_id=run_id,
            qualification_scenario_id=SCENARIO_ID,
            correlation_id=CORRELATION_ID,
            state=QualificationState.APPROVAL_PENDING,
            result=QualificationResult.PENDING,
            state_revision=StateRevision(3),
        ),
        resulting_run=PaperQualificationRun(
            qualification_run_id=run_id,
            qualification_scenario_id=SCENARIO_ID,
            correlation_id=CORRELATION_ID,
            state=resulting_state,
            result=result_value,
            state_revision=StateRevision(4),
        ),
        transition_decision=decision or transition_decision(),
        execution_plan=plan if plan is not None else execution_plan(),
        replayed=replayed,
    )


def invalid_environment_request(value: object) -> PaperRuntimeRequest:
    request = object.__new__(PaperRuntimeRequest)
    object.__setattr__(request, "environment", value)
    return request


def test_facade_is_constructed_with_injected_service() -> None:
    service = RecordingService(application_result())

    facade = PaperQualificationFacade(service)

    assert facade is not None


def test_facade_rejects_non_service_dependency() -> None:
    with pytest.raises(TypeError):
        PaperQualificationFacade(object())  # type: ignore[arg-type]


def test_valid_paper_request_is_accepted_and_service_called_once() -> None:
    service = RecordingService(application_result())
    facade = PaperQualificationFacade(service)

    result = facade.handle(runtime_request())

    assert len(service.commands) == 1
    assert result.qualification_run_id == RUN_ID
    assert result.command_id == COMMAND_ID
    assert result.correlation_id == CORRELATION_ID
    assert result.idempotency_key == IDEMPOTENCY_KEY
    assert result.transition_id == "PQ-TRN-006"
    assert result.previous_revision == 3
    assert result.next_revision == 4
    assert result.qualification_state is QualificationState.APPROVED
    assert result.qualification_result is QualificationResult.PENDING
    assert result.action_executed is False


@pytest.mark.parametrize(
    "environment", [PaperIntegrationEnvironment.LIVE, "UNKNOWN", None]
)
def test_non_paper_request_rejected_before_service_call(environment: object) -> None:
    service = RecordingService(application_result())
    facade = PaperQualificationFacade(service)

    with pytest.raises(PaperEnvironmentRequiredError):
        facade.handle(invalid_environment_request(environment))

    assert service.commands == []


def test_operation_order_request_translation_service_then_action_translation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    service = RecordingService(application_result())
    facade = PaperQualificationFacade(service)
    original_request_translator = facade_module.runtime_request_to_qualification_command
    original_action_translator = facade_module.execution_plan_to_runtime_action_request

    def request_translator(
        request: PaperRuntimeRequest,
    ) -> QualificationApplicationCommand:
        calls.append("request_translator")
        return original_request_translator(request)

    def service_execute(
        command: QualificationApplicationCommand,
    ) -> QualificationApplicationResult:
        calls.append("service")
        return service.result  # type: ignore[return-value]

    def action_translator(
        plan: QualificationExecutionPlan,
        *,
        environment: PaperIntegrationEnvironment,
    ):
        calls.append("action_translator")
        return original_action_translator(plan, environment=environment)

    monkeypatch.setattr(
        facade_module,
        "runtime_request_to_qualification_command",
        request_translator,
    )
    monkeypatch.setattr(service, "execute", service_execute)
    monkeypatch.setattr(
        facade_module,
        "execution_plan_to_runtime_action_request",
        action_translator,
    )

    facade.handle(runtime_request())

    assert calls == ["request_translator", "service", "action_translator"]


def test_facade_result_is_immutable() -> None:
    result = PaperQualificationFacade(RecordingService(application_result())).handle(
        runtime_request()
    )

    with pytest.raises(FrozenInstanceError):
        result.safe_operator_message = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("intent", "expected_kind"),
    [
        (
            SideEffectIntent(
                SideEffectIntentType.SEND_BROKER_REQUEST,
                "Request broker submission.",
            ),
            RuntimeActionKind.REQUEST_BROKER_SUBMISSION,
        ),
        (
            SideEffectIntent(
                SideEffectIntentType.REQUEST_BROKER_CANCELLATION,
                "Request broker cancellation.",
            ),
            RuntimeActionKind.REQUEST_BROKER_CANCELLATION,
        ),
        (
            SideEffectIntent(
                SideEffectIntentType.START_RECONCILIATION,
                "Start reconciliation.",
            ),
            RuntimeActionKind.START_RECONCILIATION,
        ),
        (
            SideEffectIntent(
                SideEffectIntentType.BLOCK_CONSEQUENTIAL_ACTION,
                "Block action.",
            ),
            RuntimeActionKind.BLOCK_CONSEQUENTIAL_ACTION,
        ),
    ],
)
def test_runtime_action_remains_descriptive(
    intent: SideEffectIntent,
    expected_kind: RuntimeActionKind,
) -> None:
    plan = execution_plan(side_effects=(intent,))
    result = PaperQualificationFacade(
        RecordingService(application_result(plan=plan))
    ).handle(runtime_request())

    assert result.runtime_action.action_kind is expected_kind
    assert result.action_executed is False
    assert not hasattr(result.runtime_action, "broker_status")


def test_no_action_plan_returns_typed_non_executing_outcome() -> None:
    result = PaperQualificationFacade(RecordingService(application_result())).handle(
        runtime_request()
    )

    assert (
        result.runtime_action.action_kind
        is RuntimeActionKind.NO_RUNTIME_ACTION_REQUIRED
    )
    assert result.action_executed is False


def test_replay_does_not_reintroduce_consequential_action_or_increment_revision() -> (
    None
):
    replay_decision = transition_decision(
        previous_revision=StateRevision(3),
        next_revision=StateRevision(3),
    )
    replay_plan = execution_plan(
        previous_revision=StateRevision(3),
        next_revision=StateRevision(3),
        side_effects=(),
    )
    result = PaperQualificationFacade(
        RecordingService(
            application_result(
                plan=replay_plan,
                decision=replay_decision,
                replayed=True,
            )
        )
    ).handle(runtime_request())

    assert result.replayed is True
    assert result.previous_revision == result.next_revision == 3
    assert (
        result.runtime_action.action_kind
        is RuntimeActionKind.NO_RUNTIME_ACTION_REQUIRED
    )


def test_translation_failure_prevents_service_call() -> None:
    service = RecordingService(application_result())
    facade = PaperQualificationFacade(service)

    with pytest.raises(PaperEnvironmentRequiredError):
        facade.handle(invalid_environment_request(PaperIntegrationEnvironment.LIVE))

    assert service.commands == []


def test_service_failure_prevents_action_translation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RecordingService(
        error=ApplicationCommandValidationError(
            reason_code="STALE_REVISION",
            safe_message="Stale revision.",
        )
    )
    facade = PaperQualificationFacade(service)

    def fail_action_translation(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("action translation should not run")

    monkeypatch.setattr(
        facade_module,
        "execution_plan_to_runtime_action_request",
        fail_action_translation,
    )

    with pytest.raises(FacadeServiceInvocationError) as error_info:
        facade.handle(runtime_request())

    assert error_info.value.reason_code == "STALE_REVISION"
    assert len(service.commands) == 1


def test_action_translation_failure_does_not_retry_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = RecordingService(application_result())
    facade = PaperQualificationFacade(service)

    def fail_action_translation(*_args: object, **_kwargs: object) -> None:
        raise FacadeResultValidationError(
            reason_code="ACTION_TRANSLATION_FAILED",
            safe_message="Action translation failed safely.",
        )

    monkeypatch.setattr(
        facade_module,
        "execution_plan_to_runtime_action_request",
        fail_action_translation,
    )

    with pytest.raises(FacadeResultValidationError):
        facade.handle(runtime_request())

    assert len(service.commands) == 1


@pytest.mark.parametrize(
    "plan",
    [
        execution_plan(command_id=CommandId("other-command")),
        execution_plan(correlation_id=CorrelationId("other-correlation")),
        execution_plan(idempotency_key=IdempotencyKey("other-idem")),
        execution_plan(qualification_run_id=QualificationRunId("other-run")),
        execution_plan(previous_revision=StateRevision(2)),
    ],
)
def test_identity_mismatch_raises_typed_error(plan: QualificationExecutionPlan) -> None:
    facade = PaperQualificationFacade(RecordingService(application_result(plan=plan)))

    with pytest.raises(FacadeIdentityContinuityError):
        facade.handle(runtime_request())


def test_mismatched_result_run_id_raises_typed_error() -> None:
    facade = PaperQualificationFacade(
        RecordingService(application_result(run_id=QualificationRunId("other-run")))
    )

    with pytest.raises(FacadeIdentityContinuityError):
        facade.handle(runtime_request())


def test_missing_execution_plan_raises_typed_error() -> None:
    result = application_result()
    result_without_plan = QualificationApplicationResult(
        qualification_run_id=result.qualification_run_id,
        accepted=result.accepted,
        code=result.code,
        safe_message=result.safe_message,
        previous_run=result.previous_run,
        resulting_run=result.resulting_run,
        transition_decision=result.transition_decision,
        execution_plan=None,
        evidence_records=result.evidence_records,
        save_result=result.save_result,
        replayed=result.replayed,
        reconciliation_required=result.reconciliation_required,
    )
    facade = PaperQualificationFacade(RecordingService(result_without_plan))

    with pytest.raises(FacadeResultValidationError):
        facade.handle(runtime_request())


def test_secret_absent_from_result_error_and_identity() -> None:
    secret = "SENTINEL_PASSWORD_DO_NOT_EXPOSE"
    result = PaperQualificationFacade(RecordingService(application_result())).handle(
        runtime_request(metadata=(("safe_note", "safe"),))
    )
    with pytest.raises(FacadeServiceInvocationError) as error_info:
        PaperQualificationFacade(
            RecordingService(
                error=ApplicationCommandValidationError(
                    reason_code="SAFE_ERROR",
                    safe_message="Safe message.",
                )
            )
        ).handle(runtime_request())

    rendered = "\n".join(
        (
            repr(result),
            str(error_info.value),
            result.runtime_action.action_request_id,
        )
    )

    assert secret not in rendered
    assert "SENTINEL_INTEGRATION_SECRET_DO_NOT_EXPOSE" not in rendered
    assert "SENTINEL_BROKER_TOKEN_DO_NOT_EXPOSE" not in rendered


def test_facade_does_not_mutate_request_or_application_result() -> None:
    request = runtime_request()
    app_result = application_result()
    before_request = repr(request)
    before_result = repr(app_result)

    PaperQualificationFacade(RecordingService(app_result)).handle(request)

    assert repr(request) == before_request
    assert repr(app_result) == before_result


def test_public_facade_api_has_no_external_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("external effect attempted")

    monkeypatch.setattr(builtins, "open", fail)
    monkeypatch.setattr(socket, "socket", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(state_machine, "transition", fail)
    monkeypatch.setattr(state_machine, "apply_transition", fail)

    result = PaperQualificationFacade(RecordingService(application_result())).handle(
        runtime_request()
    )

    assert result.action_executed is False


def test_default_scenario_can_be_invoked_through_facade_step_by_step() -> None:
    repository = InMemoryQualificationRunRepository()
    recorder = RecordingQualificationEvidenceRecorder()
    service = PaperQualificationService(repository, recorder)
    facade = PaperQualificationFacade(service)
    scenario = default_positive_scenario()
    transition_trace: list[str] = []
    revision_trace: list[int] = []
    actions_executed: list[bool] = []
    final_result = None

    for step in scenario.steps:
        result = facade.handle(
            runtime_request(
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
        )
        transition_trace.append(result.transition_id)
        revision_trace.append(result.next_revision)
        actions_executed.append(result.action_executed)
        final_result = result

    assert transition_trace == [
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
    assert revision_trace == list(range(1, 11))
    assert actions_executed == [False] * 10
    assert final_result is not None
    assert final_result.qualification_state is QualificationState.QUALIFIED
    assert final_result.qualification_result is QualificationResult.PASSED
