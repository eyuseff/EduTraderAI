"""Approved immutable Paper qualification scenario catalog."""

from __future__ import annotations

from dataclasses import replace

from volcanoes.application.qualification.contracts import (
    ActorType,
    CommandId,
    Guard,
    IdempotencyKey,
    QualificationEventType,
    QualificationResult,
    QualificationScenarioId,
    QualificationState,
    SideEffectIntentType,
    StateRevision,
)
from volcanoes.application.qualification.scenario_models import (
    NormalizedBrokerObservation,
    QualificationScenarioExpectation,
    QualificationScenarioSpec,
    QualificationScenarioStep,
    QualificationScenarioVersion,
    ScenarioCategory,
    ScenarioStepId,
    ScenarioStepKind,
    ScenarioTerminalExpectation,
    ScenarioValidationError,
    ScenarioValidationReason,
)
from volcanoes.application.qualification.service import ExecutionPlanKind

DEFAULT_SCENARIO_ID = QualificationScenarioId("PQ-SCN-005")
DEFAULT_SCENARIO_VERSION = QualificationScenarioVersion("v1")


def approved_scenario_catalog() -> tuple[QualificationScenarioSpec, ...]:
    """Return approved scenarios in deterministic catalog order."""

    return build_scenario_catalog(
        (
            default_positive_scenario(),
            operator_rejection_scenario(),
            precheck_failure_scenario(),
            emergency_stop_scenario(),
            uncertain_submission_scenario(),
            duplicate_command_replay_scenario(),
            idempotency_conflict_scenario(),
            duplicate_broker_observation_scenario(),
        )
    )


def build_scenario_catalog(
    scenarios: tuple[QualificationScenarioSpec, ...],
) -> tuple[QualificationScenarioSpec, ...]:
    """Return a deterministic catalog and reject duplicate ID/version pairs."""

    seen: set[tuple[str, str]] = set()
    for scenario in scenarios:
        key = (scenario.scenario_id, scenario.scenario_version)
        if key in seen:
            raise ScenarioValidationError(
                reason_code=ScenarioValidationReason.DUPLICATE_SCENARIO_ID_VERSION,
                safe_message="Scenario ID and version pairs must be unique.",
            )
        seen.add(key)
    return tuple(sorted(scenarios, key=_scenario_sort_key))


def _scenario_sort_key(
    scenario: QualificationScenarioSpec,
) -> tuple[QualificationScenarioId, QualificationScenarioVersion]:
    return (scenario.scenario_id, scenario.scenario_version)


def scenario_by_id(
    scenario_id: QualificationScenarioId,
    scenario_version: QualificationScenarioVersion = DEFAULT_SCENARIO_VERSION,
) -> QualificationScenarioSpec:
    """Lookup one approved scenario by stable ID and version."""

    for scenario in approved_scenario_catalog():
        if (
            scenario.scenario_id == scenario_id
            and scenario.scenario_version == scenario_version
        ):
            return scenario
    raise ScenarioValidationError(
        reason_code=ScenarioValidationReason.UNSUPPORTED_VERSION,
        safe_message="Scenario ID and version were not found in the approved catalog.",
    )


def default_positive_scenario() -> QualificationScenarioSpec:
    """Return the Sentinel-approved one-share ack/cancel/no-position scenario."""

    steps = _default_positive_steps()
    return _scenario(
        scenario_id=DEFAULT_SCENARIO_ID,
        title="Paper acknowledgment, cancellation, no position",
        description=(
            "One-share Paper-only non-marketable order intent is approved, "
            "acknowledged, cancelled, confirmed clean, and finalized as qualified."
        ),
        order_intent_summary=(
            "BUY 1 TEST at a deliberately non-marketable Paper limit price."
        ),
        steps=steps,
        terminal_state=QualificationState.QUALIFIED,
        terminal_result=QualificationResult.PASSED,
        category=ScenarioCategory.POSITIVE,
        mandatory=True,
        required_side_effects=(
            SideEffectIntentType.REQUEST_OPERATOR_APPROVAL,
            SideEffectIntentType.RECORD_OPERATOR_APPROVAL,
            SideEffectIntentType.PREPARE_BROKER_SUBMISSION,
            SideEffectIntentType.SEND_BROKER_REQUEST,
            SideEffectIntentType.RECORD_BROKER_REFERENCE,
            SideEffectIntentType.REQUEST_BROKER_CANCELLATION,
            SideEffectIntentType.RECORD_BROKER_LIFECYCLE,
            SideEffectIntentType.FINALIZE_QUALIFICATION,
        ),
        tags=("default", "paper", "acknowledge", "cancel", "no-position"),
    )


def operator_rejection_scenario() -> QualificationScenarioSpec:
    """Return the approved operator rejection safety scenario."""

    base = _default_positive_steps()[:3]
    rejection = _step(
        sequence=4,
        event=QualificationEventType.OPERATOR_REJECTED,
        source=QualificationState.APPROVAL_PENDING,
        transition="PQ-TRN-007",
        destination=QualificationState.REJECTED,
        result=QualificationResult.FAILED,
        revision=4,
        actor=ActorType.OPERATOR,
        key="operator-reject",
        guards=(Guard.OPERATOR_REJECTION_CAPTURED,),
        plan=(ExecutionPlanKind.CONSEQUENTIAL_ACTION_BLOCKED,),
        side_effects=(SideEffectIntentType.BLOCK_CONSEQUENTIAL_ACTION,),
    )
    return _scenario(
        scenario_id=QualificationScenarioId("PQ-SCN-008"),
        title="Operator rejects before broker submission",
        description="Operator rejection blocks broker submission safely.",
        order_intent_summary="BUY 1 TEST; operator rejects before submission.",
        steps=(*base, rejection),
        terminal_state=QualificationState.REJECTED,
        terminal_result=QualificationResult.FAILED,
        category=ScenarioCategory.NEGATIVE,
        mandatory=True,
        required_side_effects=(
            SideEffectIntentType.REQUEST_OPERATOR_APPROVAL,
            SideEffectIntentType.BLOCK_CONSEQUENTIAL_ACTION,
        ),
        tags=("operator-rejection", "safety"),
    )


def precheck_failure_scenario() -> QualificationScenarioSpec:
    """Return the approved precheck failure safety scenario."""

    steps = (
        _default_positive_steps()[0],
        _step(
            sequence=2,
            event=QualificationEventType.PRECHECKS_FAILED,
            source=QualificationState.PRECHECK_PENDING,
            transition="PQ-TRN-003",
            destination=QualificationState.PRECHECK_FAILED,
            result=QualificationResult.INCONCLUSIVE,
            revision=2,
            actor=ActorType.APPLICATION,
            key="precheck-failed",
            guards=(Guard.EVIDENCE_AVAILABLE,),
            plan=(ExecutionPlanKind.CONSEQUENTIAL_ACTION_BLOCKED,),
            side_effects=(SideEffectIntentType.BLOCK_CONSEQUENTIAL_ACTION,),
        ),
    )
    return _scenario(
        scenario_id=QualificationScenarioId("PQ-SCN-002"),
        title="Precheck failure blocks approval and submission",
        description="One required deterministic precheck fails before approval.",
        order_intent_summary="BUY 1 TEST; precheck failure prevents submission.",
        steps=steps,
        terminal_state=QualificationState.PRECHECK_FAILED,
        terminal_result=QualificationResult.INCONCLUSIVE,
        category=ScenarioCategory.NEGATIVE,
        mandatory=True,
        required_side_effects=(SideEffectIntentType.BLOCK_CONSEQUENTIAL_ACTION,),
        tags=("precheck-failure", "safety"),
    )


def emergency_stop_scenario() -> QualificationScenarioSpec:
    """Return the approved emergency-stop boundary scenario."""

    steps = (
        *_default_positive_steps()[:4],
        _expected_rejection_step(
            sequence=5,
            event=QualificationEventType.SUBMISSION_STARTED,
            source=QualificationState.APPROVED,
            destination=QualificationState.APPROVED,
            result=QualificationResult.PENDING,
            revision=4,
            key="emergency-stop",
            reason_code="GUARD_EMERGENCY_STOP_INACTIVE",
            message="Emergency stop is active",
            guards=(Guard.APPROVAL_NOT_EXPIRED, Guard.NO_DUPLICATE_KEY),
        ),
    )
    return _scenario(
        scenario_id=QualificationScenarioId("PQ-SCN-009"),
        title="Emergency stop blocks consequential submission",
        description="Emergency stop prevents submission at the action boundary.",
        order_intent_summary="BUY 1 TEST; emergency stop active before submission.",
        steps=steps,
        terminal_state=QualificationState.APPROVED,
        terminal_result=QualificationResult.PENDING,
        category=ScenarioCategory.SAFETY,
        mandatory=True,
        required_side_effects=(
            SideEffectIntentType.REQUEST_OPERATOR_APPROVAL,
            SideEffectIntentType.RECORD_OPERATOR_APPROVAL,
        ),
        tags=("emergency-stop", "safety"),
    )


def uncertain_submission_scenario() -> QualificationScenarioSpec:
    """Return the accepted unresolved/reconciliation scenario."""

    steps = (
        *_default_positive_steps()[:5],
        _step(
            sequence=6,
            event=QualificationEventType.TIMEOUT_DETECTED,
            source=QualificationState.SUBMISSION_PENDING,
            transition="PQ-TRN-023",
            destination=QualificationState.UNRESOLVED,
            result=QualificationResult.INCONCLUSIVE,
            revision=6,
            actor=ActorType.SYSTEM,
            key="send-uncertain",
            guards=(Guard.BROKER_SEND_UNCERTAIN,),
            plan=(ExecutionPlanKind.CONSEQUENTIAL_ACTION_BLOCKED,),
            side_effects=(SideEffectIntentType.BLOCK_CONSEQUENTIAL_ACTION,),
        ),
        _step(
            sequence=7,
            event=QualificationEventType.RECONCILIATION_STARTED,
            source=QualificationState.UNRESOLVED,
            transition="PQ-TRN-024",
            destination=QualificationState.RECONCILIATION_REQUIRED,
            result=QualificationResult.INCONCLUSIVE,
            revision=7,
            actor=ActorType.RECONCILIATION,
            key="reconcile-required",
            guards=(Guard.READ_ONLY_RECONCILIATION_AVAILABLE,),
            plan=(ExecutionPlanKind.RECONCILIATION_REQUIRED,),
            side_effects=(SideEffectIntentType.START_RECONCILIATION,),
            reconciliation_required=True,
        ),
    )
    return _scenario(
        scenario_id=QualificationScenarioId("PQ-SCN-010"),
        title="Uncertain submission requires read-only reconciliation",
        description="Uncertain external effect reaches reconciliation-required state.",
        order_intent_summary="BUY 1 TEST; send outcome unknown after preparation.",
        steps=steps,
        terminal_state=QualificationState.RECONCILIATION_REQUIRED,
        terminal_result=QualificationResult.INCONCLUSIVE,
        category=ScenarioCategory.RECOVERY,
        mandatory=True,
        required_side_effects=(
            SideEffectIntentType.PREPARE_BROKER_SUBMISSION,
            SideEffectIntentType.BLOCK_CONSEQUENTIAL_ACTION,
            SideEffectIntentType.START_RECONCILIATION,
        ),
        tags=("uncertain-submission", "reconciliation"),
    )


def duplicate_command_replay_scenario() -> QualificationScenarioSpec:
    """Return the accepted replay scenario for a consequential command."""

    steps = (
        *_default_positive_steps()[:6],
        _step(
            sequence=7,
            event=QualificationEventType.BROKER_REQUEST_SENT,
            source=QualificationState.SUBMITTED,
            transition="PQ-TRN-010",
            destination=QualificationState.SUBMITTED,
            result=QualificationResult.PENDING,
            revision=6,
            actor=ActorType.APPLICATION,
            key="broker-request-sent",
            guards=(),
            plan=(ExecutionPlanKind.NO_EXTERNAL_ACTION_REQUIRED,),
            side_effects=(),
            evidence_recorded=False,
            replayed=True,
            replay_verification=True,
        ),
    )
    return _scenario(
        scenario_id=QualificationScenarioId("PQ-SCN-011"),
        title="Duplicate consequential command replays without repeated effect",
        description="Same send command identity replays without revision or broker plan.",
        order_intent_summary="BUY 1 TEST; replay send command after logical send.",
        steps=steps,
        terminal_state=QualificationState.SUBMITTED,
        terminal_result=QualificationResult.PENDING,
        category=ScenarioCategory.SAFETY,
        mandatory=True,
        required_side_effects=(SideEffectIntentType.SEND_BROKER_REQUEST,),
        tags=("idempotency", "replay"),
    )


def idempotency_conflict_scenario() -> QualificationScenarioSpec:
    """Return the accepted conflicting idempotency scenario."""

    first = _default_positive_steps()[0]
    conflict = _expected_rejection_step(
        sequence=2,
        event=QualificationEventType.START_QUALIFICATION,
        source=QualificationState.PRECHECK_PENDING,
        destination=QualificationState.PRECHECK_PENDING,
        result=QualificationResult.PENDING,
        revision=1,
        key="start-qualification",
        reason_code="IDEMPOTENCY_CONFLICT",
        message="idempotency key was already used",
        guards=(Guard.SCENARIO_AUTHORIZED, Guard.PAPER_ENVIRONMENT),
        fingerprint=("different-safe-payload",),
        replay_verification=True,
    )
    return _scenario(
        scenario_id=QualificationScenarioId("PQ-SCN-012"),
        title="Idempotency conflict preserves run state",
        description="Same idempotency key with different payload is rejected.",
        order_intent_summary="BUY 1 TEST; command identity conflict.",
        steps=(first, conflict),
        terminal_state=QualificationState.PRECHECK_PENDING,
        terminal_result=QualificationResult.PENDING,
        category=ScenarioCategory.SAFETY,
        mandatory=True,
        required_side_effects=(),
        tags=("idempotency", "conflict"),
    )


def duplicate_broker_observation_scenario() -> QualificationScenarioSpec:
    """Return the safe duplicate broker observation replay scenario."""

    steps = (
        *_default_positive_steps()[:7],
        _step(
            sequence=8,
            event=QualificationEventType.BROKER_ACKNOWLEDGED,
            source=QualificationState.ACKNOWLEDGED,
            transition="PQ-TRN-011",
            destination=QualificationState.ACKNOWLEDGED,
            result=QualificationResult.PENDING,
            revision=7,
            actor=ActorType.BROKER,
            key="broker-acknowledged",
            guards=(),
            plan=(ExecutionPlanKind.NO_EXTERNAL_ACTION_REQUIRED,),
            side_effects=(),
            evidence_recorded=False,
            replayed=True,
            replay_verification=True,
            observation=NormalizedBrokerObservation(
                observation_type="BROKER_ACKNOWLEDGED",
                object_reference="paper-order-reference-001",
                facts=("accepted-by-paper-broker", "zero-fill-observed"),
            ),
        ),
    )
    return _scenario(
        scenario_id=QualificationScenarioId("PQ-SCN-013"),
        title="Duplicate broker acknowledgment is replayed safely",
        description="Duplicate normalized acknowledgment does not mutate twice.",
        order_intent_summary="BUY 1 TEST; duplicate broker acknowledgment observation.",
        steps=steps,
        terminal_state=QualificationState.ACKNOWLEDGED,
        terminal_result=QualificationResult.PENDING,
        category=ScenarioCategory.SAFETY,
        mandatory=True,
        required_side_effects=(SideEffectIntentType.RECORD_BROKER_REFERENCE,),
        tags=("broker-observation", "replay"),
    )


def _default_positive_steps() -> tuple[QualificationScenarioStep, ...]:
    return (
        _step(
            sequence=1,
            event=QualificationEventType.START_QUALIFICATION,
            source=QualificationState.NOT_STARTED,
            transition="PQ-TRN-001",
            destination=QualificationState.PRECHECK_PENDING,
            result=QualificationResult.PENDING,
            revision=1,
            actor=ActorType.APPLICATION,
            key="start-qualification",
            guards=(Guard.SCENARIO_AUTHORIZED, Guard.PAPER_ENVIRONMENT),
        ),
        _step(
            sequence=2,
            event=QualificationEventType.PRECHECKS_PASSED,
            source=QualificationState.PRECHECK_PENDING,
            transition="PQ-TRN-002",
            destination=QualificationState.READY_FOR_APPROVAL,
            result=QualificationResult.PENDING,
            revision=2,
            actor=ActorType.APPLICATION,
            key="prechecks-passed",
            guards=(
                Guard.PAPER_ENVIRONMENT,
                Guard.BROKER_SUPPORTED,
                Guard.CONFIGURATION_VALID,
                Guard.CREDENTIALS_AVAILABLE,
                Guard.EVIDENCE_AVAILABLE,
            ),
        ),
        _step(
            sequence=3,
            event=QualificationEventType.APPROVAL_REQUESTED,
            source=QualificationState.READY_FOR_APPROVAL,
            transition="PQ-TRN-005",
            destination=QualificationState.APPROVAL_PENDING,
            result=QualificationResult.PENDING,
            revision=3,
            actor=ActorType.APPLICATION,
            key="approval-requested",
            guards=(Guard.APPROVAL_SURFACE_AVAILABLE, Guard.EMERGENCY_STOP_INACTIVE),
            plan=(ExecutionPlanKind.OPERATOR_ACTION_REQUIRED,),
            side_effects=(SideEffectIntentType.REQUEST_OPERATOR_APPROVAL,),
        ),
        _step(
            sequence=4,
            event=QualificationEventType.OPERATOR_APPROVED,
            source=QualificationState.APPROVAL_PENDING,
            transition="PQ-TRN-006",
            destination=QualificationState.APPROVED,
            result=QualificationResult.PENDING,
            revision=4,
            actor=ActorType.OPERATOR,
            key="operator-approved",
            guards=(
                Guard.OPERATOR_APPROVAL_VALID,
                Guard.PLAN_CURRENT,
                Guard.EVIDENCE_AVAILABLE,
            ),
            plan=(ExecutionPlanKind.NO_EXTERNAL_ACTION_REQUIRED,),
            side_effects=(SideEffectIntentType.RECORD_OPERATOR_APPROVAL,),
        ),
        _step(
            sequence=5,
            event=QualificationEventType.SUBMISSION_STARTED,
            source=QualificationState.APPROVED,
            transition="PQ-TRN-009",
            destination=QualificationState.SUBMISSION_PENDING,
            result=QualificationResult.PENDING,
            revision=5,
            actor=ActorType.APPLICATION,
            key="submission-started",
            guards=(
                Guard.APPROVAL_NOT_EXPIRED,
                Guard.NO_DUPLICATE_KEY,
                Guard.EMERGENCY_STOP_INACTIVE,
            ),
            plan=(ExecutionPlanKind.NO_EXTERNAL_ACTION_REQUIRED,),
            side_effects=(SideEffectIntentType.PREPARE_BROKER_SUBMISSION,),
        ),
        _step(
            sequence=6,
            event=QualificationEventType.BROKER_REQUEST_SENT,
            source=QualificationState.SUBMISSION_PENDING,
            transition="PQ-TRN-010",
            destination=QualificationState.SUBMITTED,
            result=QualificationResult.PENDING,
            revision=6,
            actor=ActorType.APPLICATION,
            key="broker-request-sent",
            guards=(
                Guard.BROKER_CAPABILITY_AVAILABLE,
                Guard.NO_DUPLICATE_KEY,
                Guard.PAPER_ENVIRONMENT,
            ),
            plan=(ExecutionPlanKind.BROKER_ACTION_PROPOSED,),
            side_effects=(SideEffectIntentType.SEND_BROKER_REQUEST,),
        ),
        _step(
            sequence=7,
            event=QualificationEventType.BROKER_ACKNOWLEDGED,
            source=QualificationState.SUBMITTED,
            transition="PQ-TRN-011",
            destination=QualificationState.ACKNOWLEDGED,
            result=QualificationResult.PENDING,
            revision=7,
            actor=ActorType.BROKER,
            key="broker-acknowledged",
            guards=(Guard.BROKER_RESPONSE_MATCHES,),
            plan=(ExecutionPlanKind.BROKER_OBSERVATION_REQUIRED,),
            side_effects=(SideEffectIntentType.RECORD_BROKER_REFERENCE,),
            observation=NormalizedBrokerObservation(
                observation_type="BROKER_ACKNOWLEDGED",
                object_reference="paper-order-reference-001",
                facts=("accepted-by-paper-broker", "zero-fill-observed"),
            ),
        ),
        _step(
            sequence=8,
            event=QualificationEventType.CANCELLATION_REQUESTED,
            source=QualificationState.ACKNOWLEDGED,
            transition="PQ-TRN-015",
            destination=QualificationState.CANCELLATION_REQUESTED,
            result=QualificationResult.PENDING,
            revision=8,
            actor=ActorType.APPLICATION,
            key="cancellation-requested",
            guards=(
                Guard.CANCELLATION_SUPPORTED,
                Guard.NO_TERMINAL_BROKER_STATE,
                Guard.EMERGENCY_STOP_INACTIVE,
            ),
            plan=(ExecutionPlanKind.BROKER_ACTION_PROPOSED,),
            side_effects=(SideEffectIntentType.REQUEST_BROKER_CANCELLATION,),
        ),
        _step(
            sequence=9,
            event=QualificationEventType.BROKER_CANCELLATION_CONFIRMED,
            source=QualificationState.CANCELLATION_REQUESTED,
            transition="PQ-TRN-017",
            destination=QualificationState.CANCELLED,
            result=QualificationResult.PENDING,
            revision=9,
            actor=ActorType.BROKER,
            key="broker-cancellation-confirmed",
            guards=(Guard.CANCELLATION_CONFIRMATION_MATCHES,),
            plan=(ExecutionPlanKind.BROKER_OBSERVATION_REQUIRED,),
            side_effects=(SideEffectIntentType.RECORD_BROKER_LIFECYCLE,),
            observation=NormalizedBrokerObservation(
                observation_type="BROKER_CANCELLATION_CONFIRMED",
                object_reference="paper-order-reference-001",
                facts=("no-open-order", "no-position"),
            ),
        ),
        _step(
            sequence=10,
            event=QualificationEventType.QUALIFICATION_CRITERIA_MET,
            source=QualificationState.CANCELLED,
            transition="PQ-TRN-030",
            destination=QualificationState.QUALIFIED,
            result=QualificationResult.PASSED,
            revision=10,
            actor=ActorType.APPLICATION,
            key="criteria-met",
            guards=(
                Guard.SCENARIO_REQUIRES_CANCELLATION_CLEANUP,
                Guard.CRITERIA_EVIDENCE_COMPLETE,
            ),
            plan=(ExecutionPlanKind.QUALIFICATION_FINALIZATION_PROPOSED,),
            side_effects=(SideEffectIntentType.FINALIZE_QUALIFICATION,),
        ),
    )


def _scenario(
    *,
    scenario_id: QualificationScenarioId,
    title: str,
    description: str,
    order_intent_summary: str,
    steps: tuple[QualificationScenarioStep, ...],
    terminal_state: QualificationState,
    terminal_result: QualificationResult,
    category: ScenarioCategory,
    mandatory: bool,
    required_side_effects: tuple[SideEffectIntentType, ...],
    tags: tuple[str, ...],
) -> QualificationScenarioSpec:
    return QualificationScenarioSpec(
        scenario_id=scenario_id,
        scenario_version=DEFAULT_SCENARIO_VERSION,
        title=title,
        description=description,
        environment="PAPER",
        order_intent_summary=order_intent_summary,
        preconditions=("Paper environment", "Safe normalized fixture"),
        steps=steps,
        terminal_expectation=ScenarioTerminalExpectation(
            workflow_state=terminal_state,
            qualification_result=terminal_result,
        ),
        required_evidence_expectations=("transition evidence recorded",),
        required_side_effect_expectations=required_side_effects,
        prohibited_behavior=(
            "broker connectivity",
            "simulator mutation",
            "credential access",
            "runtime file access",
            "network I/O",
        ),
        tags=tags,
        mandatory=mandatory,
        category=category,
    )


def _step(
    *,
    sequence: int,
    event: QualificationEventType,
    source: QualificationState,
    transition: str,
    destination: QualificationState,
    result: QualificationResult,
    revision: int,
    actor: ActorType,
    key: str,
    guards: tuple[Guard, ...],
    plan: tuple[ExecutionPlanKind, ...] = (
        ExecutionPlanKind.NO_EXTERNAL_ACTION_REQUIRED,
    ),
    side_effects: tuple[SideEffectIntentType, ...] = (),
    reconciliation_required: bool = False,
    evidence_recorded: bool = True,
    replayed: bool = False,
    replay_verification: bool = False,
    observation: NormalizedBrokerObservation | None = None,
) -> QualificationScenarioStep:
    return QualificationScenarioStep(
        step_id=ScenarioStepId(f"step-{sequence:02d}-{event.value.lower()}"),
        sequence=sequence,
        step_kind=_step_kind(event, actor, replayed),
        event_type=event,
        expected_source_state=source,
        expected_transition_id=transition,
        expected_revision=StateRevision(revision - (0 if replayed else 1)),
        actor_type=actor,
        command_id=CommandId(f"cmd-{key}"),
        idempotency_key=IdempotencyKey(key),
        guards=frozenset(guards),
        expectation=QualificationScenarioExpectation(
            accepted=True,
            transition_id=transition,
            destination_state=destination,
            qualification_result=result,
            revision=StateRevision(revision),
            execution_plan_kinds=plan,
            side_effect_intents=side_effects,
            reconciliation_required=reconciliation_required,
            evidence_recorded=evidence_recorded,
            replayed=replayed,
        ),
        payload_fingerprint=("one-share-paper-non-marketable", key),
        object_reference="paper-order-reference-001",
        observation=observation,
        replay_verification=replay_verification,
    )


def _expected_rejection_step(
    *,
    sequence: int,
    event: QualificationEventType,
    source: QualificationState,
    destination: QualificationState,
    result: QualificationResult,
    revision: int,
    key: str,
    reason_code: str,
    message: str,
    guards: tuple[Guard, ...],
    fingerprint: tuple[str, ...] = ("one-share-paper-non-marketable",),
    replay_verification: bool = False,
) -> QualificationScenarioStep:
    accepted_step = _step(
        sequence=sequence,
        event=event,
        source=source,
        transition="INVALID",
        destination=destination,
        result=result,
        revision=revision,
        actor=ActorType.APPLICATION,
        key=key,
        guards=guards,
        plan=(ExecutionPlanKind.CONSEQUENTIAL_ACTION_BLOCKED,),
        side_effects=(),
        evidence_recorded=False,
        replayed=False,
        replay_verification=replay_verification,
    )
    return replace(
        accepted_step,
        step_kind=ScenarioStepKind.EXPECTED_REJECTION,
        expected_revision=StateRevision(revision),
        expectation=replace(
            accepted_step.expectation,
            accepted=False,
            reason_code=reason_code,
            safe_message_contains=message,
        ),
        payload_fingerprint=fingerprint,
        expected_rejection=True,
    )


def _step_kind(
    event: QualificationEventType,
    actor: ActorType,
    replayed: bool,
) -> ScenarioStepKind:
    if replayed:
        return ScenarioStepKind.APPLICATION_COMMAND
    if actor is ActorType.BROKER:
        return ScenarioStepKind.BROKER_OBSERVATION
    if actor is ActorType.OPERATOR:
        return ScenarioStepKind.OPERATOR_COMMAND
    if event in {
        QualificationEventType.TIMEOUT_DETECTED,
        QualificationEventType.RECONCILIATION_STARTED,
    }:
        return ScenarioStepKind.SYSTEM_OBSERVATION
    return ScenarioStepKind.APPLICATION_COMMAND
