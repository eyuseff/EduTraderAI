"""Pure translators for Paper qualification integration contracts."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from volcanoes.application.qualification.contracts import (
    QualificationEventType,
    SideEffectIntentType,
)
from volcanoes.application.qualification.integration.contracts import (
    NormalizedRuntimeObservation,
    PaperIntegrationEnvironment,
    PaperRuntimeRequest,
    RuntimeActionKind,
    RuntimeActionRequest,
    RuntimeObservationType,
    RuntimeRequestKind,
    SafeMetadata,
    require_paper_environment,
)
from volcanoes.application.qualification.integration.errors import (
    IntegrationIdentityError,
    IntegrationTranslationError,
    UnsupportedExecutionPlanError,
    UnsupportedRuntimeObservationError,
    UnsupportedRuntimeRequestError,
)
from volcanoes.application.qualification.service import (
    QualificationApplicationCommand,
    QualificationExecutionPlan,
)

_REQUEST_EVENT_MAP = {
    RuntimeRequestKind.START_QUALIFICATION: QualificationEventType.START_QUALIFICATION,
    RuntimeRequestKind.PRECHECKS_PASSED: QualificationEventType.PRECHECKS_PASSED,
    RuntimeRequestKind.PRECHECKS_FAILED: QualificationEventType.PRECHECKS_FAILED,
    RuntimeRequestKind.APPROVAL_REQUESTED: QualificationEventType.APPROVAL_REQUESTED,
    RuntimeRequestKind.OPERATOR_APPROVED: QualificationEventType.OPERATOR_APPROVED,
    RuntimeRequestKind.OPERATOR_REJECTED: QualificationEventType.OPERATOR_REJECTED,
    RuntimeRequestKind.CANCELLATION_REQUESTED: QualificationEventType.CANCELLATION_REQUESTED,
    RuntimeRequestKind.ABORT_REQUESTED: QualificationEventType.ABORT_REQUESTED,
}

_OBSERVATION_EVENT_MAP = {
    RuntimeObservationType.BROKER_REQUEST_ACKNOWLEDGED: (
        QualificationEventType.BROKER_ACKNOWLEDGED
    ),
    RuntimeObservationType.BROKER_REQUEST_REJECTED: QualificationEventType.BROKER_REJECTED,
    RuntimeObservationType.BROKER_REQUEST_OUTCOME_UNCERTAIN: (
        QualificationEventType.TIMEOUT_DETECTED
    ),
    RuntimeObservationType.CANCELLATION_CONFIRMED: (
        QualificationEventType.BROKER_CANCELLATION_CONFIRMED
    ),
    RuntimeObservationType.CANCELLATION_REJECTED: QualificationEventType.TIMEOUT_DETECTED,
    RuntimeObservationType.PARTIAL_FILL_OBSERVED: (
        QualificationEventType.BROKER_PARTIAL_FILL_REPORTED
    ),
    RuntimeObservationType.COMPLETE_FILL_OBSERVED: (
        QualificationEventType.BROKER_FILL_REPORTED
    ),
    RuntimeObservationType.RECONCILIATION_RESOLVED: (
        QualificationEventType.RECONCILIATION_RESOLVED
    ),
    RuntimeObservationType.RECONCILIATION_INCONCLUSIVE: (
        QualificationEventType.QUALIFICATION_CRITERIA_FAILED
    ),
}


def runtime_request_to_qualification_command(
    request: PaperRuntimeRequest,
) -> QualificationApplicationCommand:
    """Translate one safe Paper runtime request into the existing command type."""

    if not isinstance(request, PaperRuntimeRequest):
        raise UnsupportedRuntimeRequestError(
            reason_code="UNSUPPORTED_RUNTIME_REQUEST",
            safe_message="Runtime request is unsupported.",
        )
    require_paper_environment(request.environment)
    try:
        event_type = _REQUEST_EVENT_MAP[request.request_kind]
    except KeyError as error:
        raise UnsupportedRuntimeRequestError(
            reason_code="UNSUPPORTED_RUNTIME_REQUEST",
            safe_message="Runtime request kind is unsupported.",
        ) from error
    return QualificationApplicationCommand(
        qualification_run_id=request.qualification_run_id,
        qualification_scenario_id=request.qualification_scenario_id,
        correlation_id=request.correlation_id,
        event_type=event_type,
        expected_revision=request.expected_revision,
        command_id=request.command_id,
        idempotency_key=request.idempotency_key,
        actor_type=request.actor_type,
        satisfied_guards=request.satisfied_guards,
        payload_fingerprint=_request_fingerprint(request),
        object_reference=request.object_reference,
        environment=request.environment.value,
    )


def execution_plan_to_runtime_action_request(
    plan: QualificationExecutionPlan,
    *,
    environment: PaperIntegrationEnvironment,
    metadata: SafeMetadata = (),
) -> RuntimeActionRequest:
    """Translate a descriptive execution plan into a descriptive runtime action."""

    if not isinstance(plan, QualificationExecutionPlan):
        raise UnsupportedExecutionPlanError(
            reason_code="UNSUPPORTED_EXECUTION_PLAN",
            safe_message="Execution plan is unsupported.",
        )
    require_paper_environment(environment)
    action_kind = _action_kind_for_plan(plan)
    action_id = derive_integration_identity(
        "qia",
        (
            "action",
            environment.value,
            plan.qualification_run_id,
            plan.transition_id,
            plan.command_id,
            plan.correlation_id,
            plan.idempotency_key,
            str(plan.previous_revision),
            action_kind.value,
        ),
    )
    return RuntimeActionRequest(
        environment=environment,
        action_request_id=action_id,
        action_kind=action_kind,
        qualification_run_id=plan.qualification_run_id,
        command_id=plan.command_id,
        correlation_id=plan.correlation_id,
        idempotency_key=plan.idempotency_key,
        source_transition_id=plan.transition_id,
        source_revision=plan.previous_revision,
        safe_operator_message=plan.operator_message,
        reconciliation_reason=(
            plan.operator_message
            if action_kind is RuntimeActionKind.START_RECONCILIATION
            else None
        ),
        metadata=metadata,
    )


def observation_to_qualification_command(
    observation: object,
) -> QualificationApplicationCommand:
    """Translate one normalized observation into an application command."""

    from volcanoes.application.qualification.integration.contracts import (
        NormalizedRuntimeObservation,
    )

    if not isinstance(observation, NormalizedRuntimeObservation):
        raise UnsupportedRuntimeObservationError(
            reason_code="UNSUPPORTED_RUNTIME_OBSERVATION",
            safe_message="Runtime observation is unsupported.",
        )
    require_paper_environment(observation.environment)
    try:
        event_type = _OBSERVATION_EVENT_MAP[observation.observation_type]
    except KeyError as error:
        raise UnsupportedRuntimeObservationError(
            reason_code="UNSUPPORTED_RUNTIME_OBSERVATION",
            safe_message="Runtime observation type requires more explicit facts.",
        ) from error
    return QualificationApplicationCommand(
        qualification_run_id=observation.qualification_run_id,
        qualification_scenario_id=observation.qualification_scenario_id,
        correlation_id=observation.correlation_id,
        event_type=event_type,
        expected_revision=observation.expected_revision,
        command_id=observation.command_id,
        idempotency_key=observation.idempotency_key,
        actor_type=observation.actor_type,
        satisfied_guards=observation.satisfied_guards,
        payload_fingerprint=_observation_fingerprint(observation),
        object_reference=(
            observation.order_reference or observation.broker_request_reference
        ),
        environment=observation.environment.value,
    )


def derive_integration_identity(prefix: str, fields: tuple[object, ...]) -> str:
    """Derive a deterministic safe integration identity from stable fields."""

    if not prefix.strip():
        raise IntegrationIdentityError(
            reason_code="INVALID_IDENTITY_PREFIX",
            safe_message="Integration identity prefix cannot be empty.",
        )
    payload = [_canonical_identity_value(field) for field in fields]
    digest = hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
    return f"{prefix}-{digest}"


def _action_kind_for_plan(plan: QualificationExecutionPlan) -> RuntimeActionKind:
    intent_types = tuple(intent.intent_type for intent in plan.side_effect_intents)
    if SideEffectIntentType.BLOCK_CONSEQUENTIAL_ACTION in intent_types:
        return RuntimeActionKind.BLOCK_CONSEQUENTIAL_ACTION
    if SideEffectIntentType.SEND_BROKER_REQUEST in intent_types:
        return RuntimeActionKind.REQUEST_BROKER_SUBMISSION
    if SideEffectIntentType.PREPARE_BROKER_SUBMISSION in intent_types:
        return RuntimeActionKind.PREPARE_BROKER_SUBMISSION
    if SideEffectIntentType.REQUEST_BROKER_CANCELLATION in intent_types:
        return RuntimeActionKind.REQUEST_BROKER_CANCELLATION
    if SideEffectIntentType.START_RECONCILIATION in intent_types:
        return RuntimeActionKind.START_RECONCILIATION
    if SideEffectIntentType.FINALIZE_QUALIFICATION in intent_types:
        return RuntimeActionKind.FINALIZE_WITHOUT_EXTERNAL_EFFECT
    if not intent_types:
        return RuntimeActionKind.NO_RUNTIME_ACTION_REQUIRED
    if set(intent_types) <= {
        SideEffectIntentType.REQUEST_OPERATOR_APPROVAL,
        SideEffectIntentType.RECORD_OPERATOR_APPROVAL,
        SideEffectIntentType.RECORD_BROKER_REFERENCE,
        SideEffectIntentType.RECORD_BROKER_LIFECYCLE,
    }:
        return RuntimeActionKind.NO_RUNTIME_ACTION_REQUIRED
    raise UnsupportedExecutionPlanError(
        reason_code="UNSUPPORTED_EXECUTION_PLAN",
        safe_message="Execution plan contains unsupported side-effect intents.",
    )


def _request_fingerprint(request: PaperRuntimeRequest) -> tuple[str, ...]:
    order = request.order_intent
    return (
        "runtime_request",
        request.runtime_request_id,
        request.request_kind.value,
        request.occurred_at.isoformat(),
        request.reason_code or "",
        order.symbol if order is not None else "",
        str(order.quantity) if order is not None else "",
        order.order_type.value if order is not None else "",
        (
            format(order.limit_price, "f")
            if order is not None and order.limit_price is not None
            else ""
        ),
        (
            order.time_in_force.value
            if order is not None and order.time_in_force is not None
            else ""
        ),
        *_metadata_fingerprint(request.metadata),
    )


def _observation_fingerprint(
    observation: NormalizedRuntimeObservation,
) -> tuple[str, ...]:
    return (
        "runtime_observation",
        observation.observation_id,
        observation.observation_type.value,
        observation.occurred_at.isoformat(),
        observation.broker_request_reference or "",
        observation.order_reference or "",
        str(observation.quantity) if observation.quantity is not None else "",
        observation.safe_reason_code or "",
        *(guard.value for guard in sorted(observation.satisfied_guards, key=str)),
        *_metadata_fingerprint(observation.metadata),
    )


def _metadata_fingerprint(metadata: SafeMetadata) -> tuple[str, ...]:
    return tuple(f"{key}={_canonical_identity_value(value)}" for key, value in metadata)


def _canonical_identity_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int)):
        return str(value)
    if isinstance(value, tuple):
        return json.dumps(
            [_canonical_identity_value(item) for item in value],
            separators=(",", ":"),
            sort_keys=True,
        )
    raise IntegrationTranslationError(
        reason_code="UNSUPPORTED_IDENTITY_FIELD",
        safe_message="Integration identity field is unsupported.",
    )
