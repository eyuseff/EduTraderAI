from __future__ import annotations

import builtins
import socket
import subprocess
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from volcanoes.application.qualification import (
    ActorType,
    CommandId,
    CorrelationId,
    Guard,
    IdempotencyKey,
    QualificationRunId,
    QualificationScenarioId,
    RetryClassification,
    SideEffectIntent,
    SideEffectIntentType,
    StateRevision,
)
from volcanoes.application.qualification.integration import (
    IntegrationOrderType,
    IntegrationTimeInForce,
    NormalizedRuntimeObservation,
    PaperEnvironmentRequiredError,
    PaperIntegrationEnvironment,
    PaperRuntimeRequest,
    RuntimeActionKind,
    RuntimeActionRequest,
    RuntimeObservationType,
    RuntimeRequestKind,
    RuntimeRequestValidationError,
    SafeOrderIntent,
    UnsafeIntegrationMetadataError,
    UnsupportedExecutionPlanError,
    UnsupportedRuntimeObservationError,
    derive_integration_identity,
    execution_plan_to_runtime_action_request,
    observation_to_qualification_command,
    runtime_request_to_qualification_command,
)
from volcanoes.application.qualification.contracts import QualificationState
from volcanoes.application.qualification.service import (
    ExecutionPlanKind,
    PaperQualificationService,
    QualificationExecutionPlan,
)
from volcanoes.application.qualification import state_machine

RUN_ID = QualificationRunId("pq-run-f1-001")
SCENARIO_ID = QualificationScenarioId("PQ-SCN-005")
COMMAND_ID = CommandId("cmd-f1-001")
CORRELATION_ID = CorrelationId("corr-f1-001")
IDEMPOTENCY_KEY = IdempotencyKey("idem-f1-001")
OBSERVATION_ID = "obs-f1-001"
REQUEST_ID = "runtime-request-f1-001"
OCCURRED_AT = datetime(2026, 7, 29, 12, 30, tzinfo=timezone(timedelta(hours=-4)))


def order_intent(**overrides: object) -> SafeOrderIntent:
    values: dict[str, Any] = {
        "symbol": " aapl ",
        "quantity": 1,
        "order_type": IntegrationOrderType.LIMIT,
        "limit_price": Decimal("100.50"),
        "time_in_force": IntegrationTimeInForce.DAY,
    }
    values.update(overrides)
    return SafeOrderIntent(**values)


def runtime_request(**overrides: object) -> PaperRuntimeRequest:
    values: dict[str, Any] = {
        "environment": PaperIntegrationEnvironment.PAPER,
        "runtime_request_id": REQUEST_ID,
        "qualification_run_id": RUN_ID,
        "qualification_scenario_id": SCENARIO_ID,
        "request_kind": RuntimeRequestKind.OPERATOR_APPROVED,
        "command_id": COMMAND_ID,
        "correlation_id": CORRELATION_ID,
        "idempotency_key": IDEMPOTENCY_KEY,
        "expected_revision": StateRevision(3),
        "actor_type": ActorType.OPERATOR,
        "occurred_at": OCCURRED_AT,
        "order_intent": order_intent(),
        "satisfied_guards": frozenset(
            {
                Guard.PAPER_ENVIRONMENT,
                Guard.OPERATOR_APPROVAL_VALID,
                Guard.PLAN_CURRENT,
            }
        ),
        "object_reference": "approval-ref-001",
        "metadata": (("source", "paper-order"),),
    }
    values.update(overrides)
    return PaperRuntimeRequest(**values)


def execution_plan(
    *,
    side_effects: tuple[SideEffectIntent, ...] = (),
    kinds: tuple[ExecutionPlanKind, ...] = (
        ExecutionPlanKind.NO_EXTERNAL_ACTION_REQUIRED,
    ),
) -> QualificationExecutionPlan:
    return QualificationExecutionPlan(
        qualification_run_id=RUN_ID,
        transition_id="PQ-TRN-010",
        source_state=QualificationState.SUBMISSION_PENDING,
        destination_state=QualificationState.SUBMITTED,
        previous_revision=StateRevision(7),
        next_revision=StateRevision(8),
        side_effect_intents=side_effects,
        evidence_intents=(),
        retry_classification=RetryClassification.SAFE_LOCAL_RETRY,
        reconciliation_required=False,
        operator_message="Safe plan message.",
        correlation_id=CORRELATION_ID,
        command_id=COMMAND_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        plan_kinds=kinds,
    )


def observation(**overrides: object) -> NormalizedRuntimeObservation:
    values: dict[str, Any] = {
        "environment": PaperIntegrationEnvironment.PAPER,
        "observation_id": OBSERVATION_ID,
        "qualification_run_id": RUN_ID,
        "qualification_scenario_id": SCENARIO_ID,
        "observation_type": RuntimeObservationType.BROKER_REQUEST_ACKNOWLEDGED,
        "command_id": CommandId("obs-command-001"),
        "correlation_id": CORRELATION_ID,
        "idempotency_key": IdempotencyKey("obs-idem-001"),
        "expected_revision": StateRevision(8),
        "actor_type": ActorType.BROKER,
        "occurred_at": OCCURRED_AT,
        "broker_request_reference": "broker-ref-001",
        "order_reference": "order-ref-001",
        "quantity": 1,
        "satisfied_guards": frozenset({Guard.BROKER_RESPONSE_MATCHES}),
        "metadata": (("source", "broker-observation"),),
    }
    values.update(overrides)
    return NormalizedRuntimeObservation(**values)


def test_paper_environment_is_accepted() -> None:
    assert runtime_request().environment is PaperIntegrationEnvironment.PAPER


@pytest.mark.parametrize(
    "environment", [PaperIntegrationEnvironment.LIVE, "UNKNOWN", None]
)
def test_non_paper_environment_is_rejected(environment: object) -> None:
    with pytest.raises(PaperEnvironmentRequiredError):
        runtime_request(environment=environment)


@pytest.mark.parametrize(
    "field",
    [
        "runtime_request_id",
        "command_id",
        "correlation_id",
        "idempotency_key",
    ],
)
def test_runtime_request_identifiers_cannot_be_empty(field: str) -> None:
    with pytest.raises(RuntimeRequestValidationError):
        runtime_request(**{field: ""})


def test_observation_identifier_cannot_be_empty() -> None:
    with pytest.raises(RuntimeRequestValidationError):
        observation(observation_id="")


@pytest.mark.parametrize("revision", [-1, True])
def test_expected_revision_validation(revision: object) -> None:
    with pytest.raises(RuntimeRequestValidationError):
        runtime_request(expected_revision=revision)


@pytest.mark.parametrize("quantity", [0, -1, True])
def test_quantity_must_be_positive_integer(quantity: object) -> None:
    with pytest.raises(RuntimeRequestValidationError):
        order_intent(quantity=quantity)


def test_unsupported_order_type_rejected() -> None:
    with pytest.raises(RuntimeRequestValidationError):
        order_intent(order_type="STOP")


def test_limit_order_requires_limit_price() -> None:
    with pytest.raises(RuntimeRequestValidationError):
        order_intent(limit_price=None)


def test_market_order_cannot_carry_limit_price() -> None:
    with pytest.raises(RuntimeRequestValidationError):
        order_intent(
            order_type=IntegrationOrderType.MARKET,
            limit_price=Decimal("10"),
        )


def test_market_order_does_not_infer_limit_price() -> None:
    intent = order_intent(
        order_type=IntegrationOrderType.MARKET,
        limit_price=None,
    )

    assert intent.limit_price is None


def test_binary_float_decimal_rejected() -> None:
    with pytest.raises(RuntimeRequestValidationError):
        order_intent(limit_price=1.1)


def test_non_finite_decimal_rejected() -> None:
    with pytest.raises(RuntimeRequestValidationError):
        order_intent(limit_price=Decimal("NaN"))


def test_naive_timestamp_rejected() -> None:
    with pytest.raises(RuntimeRequestValidationError):
        runtime_request(occurred_at=datetime(2026, 7, 29, 12, 30))


def test_timestamp_normalized_to_utc() -> None:
    request = runtime_request()

    assert request.occurred_at.tzinfo is UTC
    assert request.occurred_at.hour == 16


def test_symbol_normalization_is_deterministic() -> None:
    assert order_intent().symbol == "AAPL"


def test_contracts_are_immutable() -> None:
    request = runtime_request()
    action = RuntimeActionRequest(
        environment=PaperIntegrationEnvironment.PAPER,
        action_request_id="qia-sample",
        action_kind=RuntimeActionKind.NO_RUNTIME_ACTION_REQUIRED,
        qualification_run_id=RUN_ID,
        command_id=COMMAND_ID,
        correlation_id=CORRELATION_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        source_transition_id="PQ-TRN-001",
        source_revision=StateRevision(0),
        safe_operator_message="No runtime action required.",
    )
    observed = observation()

    with pytest.raises(FrozenInstanceError):
        request.runtime_request_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        action.action_request_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        observed.observation_id = "changed"  # type: ignore[misc]


def test_equivalent_runtime_requests_compare_equally() -> None:
    assert runtime_request() == runtime_request()


def test_runtime_request_translates_to_existing_qualification_command() -> None:
    request = runtime_request()

    command = runtime_request_to_qualification_command(request)

    assert command.qualification_run_id == RUN_ID
    assert command.qualification_scenario_id == SCENARIO_ID
    assert command.command_id == COMMAND_ID
    assert command.correlation_id == CORRELATION_ID
    assert command.idempotency_key == IDEMPOTENCY_KEY
    assert command.expected_revision == 3
    assert command.actor_type is ActorType.OPERATOR
    assert command.event_type.value == request.request_kind.value
    assert command.environment == "PAPER"
    assert command.object_reference == "approval-ref-001"
    assert "runtime_request" in command.payload_fingerprint


def test_translation_preserves_timestamp_in_payload_fingerprint() -> None:
    command = runtime_request_to_qualification_command(runtime_request())

    assert "2026-07-29T16:30:00+00:00" in command.payload_fingerprint


def test_equivalent_translation_produces_equivalent_command() -> None:
    assert runtime_request_to_qualification_command(
        runtime_request()
    ) == runtime_request_to_qualification_command(runtime_request())


def test_missing_approval_fact_is_not_invented() -> None:
    command = runtime_request_to_qualification_command(
        runtime_request(satisfied_guards=frozenset({Guard.PAPER_ENVIRONMENT}))
    )

    assert Guard.OPERATOR_APPROVAL_VALID not in command.satisfied_guards


def test_missing_broker_acknowledgment_is_not_invented() -> None:
    command = runtime_request_to_qualification_command(runtime_request())

    assert command.event_type is not None
    assert command.object_reference != "broker-acknowledgment"


@pytest.mark.parametrize(
    ("intent", "expected_kind"),
    [
        (
            SideEffectIntent(
                SideEffectIntentType.PREPARE_BROKER_SUBMISSION,
                "Prepare broker submission.",
            ),
            RuntimeActionKind.PREPARE_BROKER_SUBMISSION,
        ),
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
                "Request cancellation.",
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
                SideEffectIntentType.FINALIZE_QUALIFICATION,
                "Finalize qualification.",
            ),
            RuntimeActionKind.FINALIZE_WITHOUT_EXTERNAL_EFFECT,
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
def test_execution_plan_translates_to_descriptive_action_request(
    intent: SideEffectIntent,
    expected_kind: RuntimeActionKind,
) -> None:
    action = execution_plan_to_runtime_action_request(
        execution_plan(side_effects=(intent,)),
        environment=PaperIntegrationEnvironment.PAPER,
    )

    assert action.action_kind is expected_kind
    assert action.qualification_run_id == RUN_ID
    assert action.command_id == COMMAND_ID
    assert action.correlation_id == CORRELATION_ID
    assert action.idempotency_key == IDEMPOTENCY_KEY
    assert action.source_transition_id == "PQ-TRN-010"
    assert action.source_revision == 7


def test_no_action_plan_produces_typed_non_executing_result() -> None:
    action = execution_plan_to_runtime_action_request(
        execution_plan(),
        environment=PaperIntegrationEnvironment.PAPER,
    )

    assert action.action_kind is RuntimeActionKind.NO_RUNTIME_ACTION_REQUIRED


def test_blocked_plan_cannot_produce_broker_submission_request() -> None:
    action = execution_plan_to_runtime_action_request(
        execution_plan(
            side_effects=(
                SideEffectIntent(
                    SideEffectIntentType.BLOCK_CONSEQUENTIAL_ACTION,
                    "Blocked.",
                ),
                SideEffectIntent(
                    SideEffectIntentType.SEND_BROKER_REQUEST,
                    "Would otherwise send.",
                ),
            )
        ),
        environment=PaperIntegrationEnvironment.PAPER,
    )

    assert action.action_kind is RuntimeActionKind.BLOCK_CONSEQUENTIAL_ACTION


def test_submission_action_does_not_claim_acknowledgment() -> None:
    action = execution_plan_to_runtime_action_request(
        execution_plan(
            side_effects=(
                SideEffectIntent(
                    SideEffectIntentType.SEND_BROKER_REQUEST,
                    "Request broker submission.",
                ),
            )
        ),
        environment=PaperIntegrationEnvironment.PAPER,
    )

    assert action.action_kind is RuntimeActionKind.REQUEST_BROKER_SUBMISSION
    assert "ACK" not in action.action_kind.value


def test_cancellation_action_does_not_claim_cancellation_success() -> None:
    action = execution_plan_to_runtime_action_request(
        execution_plan(
            side_effects=(
                SideEffectIntent(
                    SideEffectIntentType.REQUEST_BROKER_CANCELLATION,
                    "Request cancellation.",
                ),
            )
        ),
        environment=PaperIntegrationEnvironment.PAPER,
    )

    assert action.action_kind is RuntimeActionKind.REQUEST_BROKER_CANCELLATION
    assert "CONFIRMED" not in action.action_kind.value


def test_reconciliation_action_does_not_claim_resolution() -> None:
    action = execution_plan_to_runtime_action_request(
        execution_plan(
            side_effects=(
                SideEffectIntent(
                    SideEffectIntentType.START_RECONCILIATION,
                    "Start reconciliation.",
                ),
            )
        ),
        environment=PaperIntegrationEnvironment.PAPER,
    )

    assert action.action_kind is RuntimeActionKind.START_RECONCILIATION
    assert action.reconciliation_reason == "Safe plan message."


def test_unsupported_plan_kind_fails_deterministically() -> None:
    with pytest.raises(UnsupportedExecutionPlanError):
        execution_plan_to_runtime_action_request(
            execution_plan(
                side_effects=(
                    SideEffectIntent(
                        SideEffectIntentType.RESUME_OR_REQUIRE_RECONCILIATION,
                        "Unsupported in F1.",
                    ),
                )
            ),
            environment=PaperIntegrationEnvironment.PAPER,
        )


def test_live_plan_translation_rejected() -> None:
    with pytest.raises(PaperEnvironmentRequiredError):
        execution_plan_to_runtime_action_request(
            execution_plan(),
            environment=PaperIntegrationEnvironment.LIVE,
        )


def test_equivalent_plan_produces_equivalent_action_identity() -> None:
    left = execution_plan_to_runtime_action_request(
        execution_plan(),
        environment=PaperIntegrationEnvironment.PAPER,
    )
    right = execution_plan_to_runtime_action_request(
        execution_plan(),
        environment=PaperIntegrationEnvironment.PAPER,
    )

    assert left.action_request_id == right.action_request_id


def test_materially_different_plan_produces_different_action_identity() -> None:
    left = execution_plan_to_runtime_action_request(
        execution_plan(),
        environment=PaperIntegrationEnvironment.PAPER,
    )
    right = execution_plan_to_runtime_action_request(
        QualificationExecutionPlan(
            qualification_run_id=RUN_ID,
            transition_id="PQ-TRN-011",
            source_state=QualificationState.SUBMITTED,
            destination_state=QualificationState.ACKNOWLEDGED,
            previous_revision=StateRevision(8),
            next_revision=StateRevision(9),
            side_effect_intents=(),
            evidence_intents=(),
            retry_classification=RetryClassification.SAFE_LOCAL_RETRY,
            reconciliation_required=False,
            operator_message="Safe plan message.",
            correlation_id=CORRELATION_ID,
            command_id=COMMAND_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            plan_kinds=(ExecutionPlanKind.NO_EXTERNAL_ACTION_REQUIRED,),
        ),
        environment=PaperIntegrationEnvironment.PAPER,
    )

    assert left.action_request_id != right.action_request_id


@pytest.mark.parametrize(
    ("observation_type", "event_name"),
    [
        (
            RuntimeObservationType.BROKER_REQUEST_ACKNOWLEDGED,
            "BROKER_ACKNOWLEDGED",
        ),
        (RuntimeObservationType.BROKER_REQUEST_REJECTED, "BROKER_REJECTED"),
        (
            RuntimeObservationType.BROKER_REQUEST_OUTCOME_UNCERTAIN,
            "TIMEOUT_DETECTED",
        ),
        (
            RuntimeObservationType.CANCELLATION_CONFIRMED,
            "BROKER_CANCELLATION_CONFIRMED",
        ),
        (
            RuntimeObservationType.PARTIAL_FILL_OBSERVED,
            "BROKER_PARTIAL_FILL_REPORTED",
        ),
        (RuntimeObservationType.COMPLETE_FILL_OBSERVED, "BROKER_FILL_REPORTED"),
        (RuntimeObservationType.RECONCILIATION_RESOLVED, "RECONCILIATION_RESOLVED"),
    ],
)
def test_observation_translates_to_existing_qualification_command(
    observation_type: RuntimeObservationType,
    event_name: str,
) -> None:
    command = observation_to_qualification_command(
        observation(observation_type=observation_type)
    )

    assert command.event_type.value == event_name
    assert command.qualification_run_id == RUN_ID
    assert command.correlation_id == CORRELATION_ID
    assert command.expected_revision == 8


def test_acknowledgment_observation_does_not_imply_fill() -> None:
    command = observation_to_qualification_command(observation())

    assert command.event_type.value == "BROKER_ACKNOWLEDGED"


def test_cancellation_request_does_not_imply_confirmation() -> None:
    request_command = runtime_request_to_qualification_command(
        runtime_request(request_kind=RuntimeRequestKind.CANCELLATION_REQUESTED)
    )

    assert request_command.event_type.value == "CANCELLATION_REQUESTED"


def test_uncertain_observation_remains_uncertain() -> None:
    command = observation_to_qualification_command(
        observation(
            observation_type=RuntimeObservationType.BROKER_REQUEST_OUTCOME_UNCERTAIN,
            satisfied_guards=frozenset({Guard.BROKER_SEND_UNCERTAIN}),
        )
    )

    assert command.event_type.value == "TIMEOUT_DETECTED"
    assert Guard.BROKER_SEND_UNCERTAIN in command.satisfied_guards


def test_order_absence_alone_does_not_imply_no_position() -> None:
    with pytest.raises(UnsupportedRuntimeObservationError):
        observation_to_qualification_command(
            observation(observation_type=RuntimeObservationType.ORDER_ABSENT)
        )


def test_duplicate_observation_retains_idempotency_identity() -> None:
    command = observation_to_qualification_command(observation())

    assert command.idempotency_key == "obs-idem-001"


def test_stale_expected_revision_is_preserved_for_service_rejection() -> None:
    command = observation_to_qualification_command(
        observation(expected_revision=StateRevision(1))
    )

    assert command.expected_revision == 1


def test_live_observation_rejected() -> None:
    with pytest.raises(PaperEnvironmentRequiredError):
        observation(environment=PaperIntegrationEnvironment.LIVE)


@pytest.mark.parametrize(
    "metadata",
    [
        (("raw_payload", "x"),),
        (("api_key", "x"),),
        (("note", "SENTINEL_INTEGRATION_SECRET_DO_NOT_EXPOSE"),),
        (("note", {"nested": "mapping"}),),
        (("note", {"set-value"}),),
        (("note", RuntimeError("boom")),),
        (("note", lambda: None),),
        (("path", "/Users/example/secret"),),
    ],
)
def test_unsafe_metadata_rejected(metadata: object) -> None:
    with pytest.raises(UnsafeIntegrationMetadataError) as error_info:
        runtime_request(metadata=metadata)

    assert "SENTINEL" not in str(error_info.value)


def test_secret_absent_from_translated_command_action_observation_and_identity() -> (
    None
):
    safe_request = runtime_request(metadata=(("note", "safe"),))
    command = runtime_request_to_qualification_command(safe_request)
    action = execution_plan_to_runtime_action_request(
        execution_plan(),
        environment=PaperIntegrationEnvironment.PAPER,
        metadata=(("note", "safe"),),
    )
    observed = observation(metadata=(("note", "safe"),))
    identity = derive_integration_identity("qia", ("safe", "identity"))

    rendered = "\n".join(
        (
            repr(command),
            repr(action),
            repr(observed),
            identity,
        )
    )

    assert "SENTINEL_INTEGRATION_SECRET_DO_NOT_EXPOSE" not in rendered
    assert "SENTINEL_BROKER_TOKEN_DO_NOT_EXPOSE" not in rendered
    assert "SENTINEL_PASSWORD_DO_NOT_EXPOSE" not in rendered


def test_runtime_action_request_remains_distinct_from_actual_broker_result() -> None:
    action = execution_plan_to_runtime_action_request(
        execution_plan(
            side_effects=(
                SideEffectIntent(
                    SideEffectIntentType.SEND_BROKER_REQUEST,
                    "Request broker submission.",
                ),
            )
        ),
        environment=PaperIntegrationEnvironment.PAPER,
    )

    assert not hasattr(action, "broker_status")
    assert not hasattr(action, "broker_order_id")


def test_normalized_observation_remains_distinct_from_raw_broker_response() -> None:
    observed = observation()

    assert not hasattr(observed, "raw_payload")
    assert not hasattr(observed, "headers")


def test_public_translation_apis_are_pure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("external effect attempted")

    monkeypatch.setattr(builtins, "open", fail)
    monkeypatch.setattr(socket, "socket", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(PaperQualificationService, "execute", fail)
    monkeypatch.setattr(state_machine, "transition", fail)
    monkeypatch.setattr(state_machine, "apply_transition", fail)

    runtime_request_to_qualification_command(runtime_request())
    execution_plan_to_runtime_action_request(
        execution_plan(),
        environment=PaperIntegrationEnvironment.PAPER,
    )
    observation_to_qualification_command(observation())
