"""Pure Paper qualification state-machine tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from volcanoes.application.qualification import (
    ActorType,
    Guard,
    GuardConditionError,
    IdempotencyConflictError,
    InvalidTransitionError,
    PaperQualificationRun,
    PriorCommandRecord,
    QualificationEvent,
    QualificationEventType,
    QualificationResult,
    CommandId,
    CorrelationId,
    IdempotencyKey,
    QualificationRunId,
    QualificationScenarioId,
    QualificationState,
    QualificationTerminalError,
    StateCategory,
    StateRevision,
    StaleRevisionError,
    TransitionContext,
    all_transition_specs,
    apply_transition,
    diagnostic_rejection,
    is_terminal_workflow_state,
    state_category,
    transition,
)

RUN_ID = QualificationRunId("pq-run-001")
SCENARIO_ID = QualificationScenarioId("PQ-SCN-005")
CORRELATION_ID = CorrelationId("correlation-001")
SECRET_SENTINEL = "SECRET-API_KEY-TOKEN-PASSWORD"
ALL_GUARDS = frozenset(Guard)


def run(
    state: QualificationState = QualificationState.NOT_STARTED,
    *,
    revision: int = 0,
    result: QualificationResult = QualificationResult.PENDING,
) -> PaperQualificationRun:
    return PaperQualificationRun(
        qualification_run_id=RUN_ID,
        qualification_scenario_id=SCENARIO_ID,
        correlation_id=CORRELATION_ID,
        state=state,
        result=result,
        state_revision=StateRevision(revision),
    )


def event(
    event_type: QualificationEventType,
    *,
    key: str = "idem-1",
    fingerprint: tuple[str, ...] = ("payload",),
) -> QualificationEvent:
    return QualificationEvent(
        event_type=event_type,
        command_id=CommandId("command-1"),
        idempotency_key=IdempotencyKey(key),
        actor_type=ActorType.APPLICATION,
        payload_fingerprint=fingerprint,
        object_reference="object-1",
    )


def context(
    revision: int = 0,
    *,
    guards: frozenset[Guard] = ALL_GUARDS,
    prior: PriorCommandRecord | None = None,
    recovered_state: QualificationState | None = None,
    environment: str = "PAPER",
) -> TransitionContext:
    return TransitionContext(
        expected_revision=StateRevision(revision),
        satisfied_guards=guards,
        prior_command=prior,
        recovered_state=recovered_state,
        environment=environment,
    )


def source_for_transition(transition_id: str) -> QualificationState:
    explicit = {
        "PQ-TRN-033": QualificationState.APPROVAL_PENDING,
        "PQ-TRN-034": QualificationState.APPROVAL_PENDING,
        "PQ-TRN-035": QualificationState.APPROVED,
    }
    if transition_id in explicit:
        return explicit[transition_id]
    spec = next(
        item for item in all_transition_specs() if item.transition_id == transition_id
    )
    assert spec.source_state is not None
    return spec.source_state


@pytest.mark.parametrize("state", tuple(QualificationState))
def test_state_classification_is_complete_and_terminal_states_are_explicit(
    state: QualificationState,
) -> None:
    category = state_category(state)

    assert isinstance(category, StateCategory)
    assert is_terminal_workflow_state(state) is (
        state
        in {
            QualificationState.QUALIFIED,
            QualificationState.DISQUALIFIED,
            QualificationState.ABORTED,
        }
    )


def test_domain_models_are_immutable_and_result_is_independent_of_state() -> None:
    sample = run(QualificationState.FILLED, result=QualificationResult.PENDING)

    assert sample.state is QualificationState.FILLED
    assert sample.result is QualificationResult.PENDING
    with pytest.raises(FrozenInstanceError):
        sample.state = QualificationState.QUALIFIED  # type: ignore[misc]


@pytest.mark.parametrize(
    "spec", all_transition_specs(), ids=lambda spec: spec.transition_id
)
def test_every_transition_id_has_positive_decision_with_expected_contract(spec) -> None:
    current = run(source_for_transition(spec.transition_id), revision=4)
    next_state = (
        QualificationState.RECONCILIATION_REQUIRED
        if spec.transition_id == "PQ-TRN-035"
        else spec.destination_state
    )
    decision = transition(
        current,
        event(spec.event_type),
        context(
            4,
            guards=spec.required_guards,
            recovered_state=next_state,
        ),
    )

    assert decision.accepted is True
    assert decision.transition_id == spec.transition_id
    assert decision.previous_state is current.state
    assert decision.next_state is next_state
    assert decision.previous_revision == 4
    assert decision.next_revision == 5
    assert decision.result is (
        current.result if spec.transition_id == "PQ-TRN-035" else spec.result
    )
    assert decision.reason_code == spec.transition_id.replace("-", "_")
    assert decision.safe_message == spec.safe_message
    assert decision.retry_classification is spec.retry_classification
    assert tuple(intent.intent_type for intent in decision.side_effects) == tuple(
        intent for intent in spec.side_effects if intent.value != "NONE"
    )
    assert len(decision.evidence_intents) == 1
    evidence = decision.evidence_intents[0]
    assert evidence.transition_id == spec.transition_id
    assert evidence.source_state is current.state
    assert evidence.destination_state is decision.next_state
    assert evidence.qualification_run_id == RUN_ID
    assert evidence.qualification_scenario_id == SCENARIO_ID
    assert evidence.correlation_id == CORRELATION_ID
    assert evidence.idempotency_key == "idem-1"
    assert evidence.result is decision.result
    assert evidence.safe_message == decision.safe_message


@pytest.mark.parametrize(
    "spec", all_transition_specs(), ids=lambda spec: spec.transition_id
)
def test_every_transition_rejects_invalid_source_without_side_effects(spec) -> None:
    current = run(
        QualificationState.QUALIFIED, revision=7, result=QualificationResult.PASSED
    )

    with pytest.raises(QualificationTerminalError):
        transition(
            current, event(spec.event_type), context(7, guards=spec.required_guards)
        )


@pytest.mark.parametrize(
    "spec",
    tuple(spec for spec in all_transition_specs() if spec.required_guards),
    ids=lambda spec: spec.transition_id,
)
def test_guard_failures_are_deterministic_and_have_no_side_effects(spec) -> None:
    current = run(source_for_transition(spec.transition_id), revision=2)
    missing_one_guard = frozenset(tuple(spec.required_guards)[1:])

    with pytest.raises(GuardConditionError) as error_info:
        transition(
            current, event(spec.event_type), context(2, guards=missing_one_guard)
        )

    assert (
        error_info.value.reason_code.startswith("GUARD_")
        or error_info.value.reason_code == "GUARD_DISAMBIGUATION_FAILED"
    )
    assert SECRET_SENTINEL not in str(error_info.value)
    assert current.state_revision == 2


def test_stale_revision_fails_before_side_effect_intent() -> None:
    with pytest.raises(StaleRevisionError) as error_info:
        transition(
            run(QualificationState.APPROVED, revision=3),
            event(QualificationEventType.SUBMISSION_STARTED),
            context(2, guards=ALL_GUARDS),
        )

    assert error_info.value.reason_code == "STALE_REVISION"
    assert "refresh" in str(error_info.value)


@pytest.mark.parametrize(
    ("state", "event_type"),
    [
        (
            QualificationState.NOT_STARTED,
            QualificationEventType.QUALIFICATION_CRITERIA_MET,
        ),
        (QualificationState.PRECHECK_FAILED, QualificationEventType.SUBMISSION_STARTED),
        (
            QualificationState.READY_FOR_APPROVAL,
            QualificationEventType.BROKER_REQUEST_SENT,
        ),
        (QualificationState.APPROVED, QualificationEventType.BROKER_ACKNOWLEDGED),
        (
            QualificationState.CANCELLATION_REQUESTED,
            QualificationEventType.QUALIFICATION_CRITERIA_MET,
        ),
        (
            QualificationState.UNRESOLVED,
            QualificationEventType.QUALIFICATION_CRITERIA_MET,
        ),
        (QualificationState.REJECTED, QualificationEventType.BROKER_FILL_REPORTED),
        (QualificationState.ABORTED, QualificationEventType.BROKER_REQUEST_SENT),
    ],
)
def test_invalid_broker_truth_shortcuts_are_rejected(
    state: QualificationState,
    event_type: QualificationEventType,
) -> None:
    error_type = (
        QualificationTerminalError
        if is_terminal_workflow_state(state)
        else InvalidTransitionError
    )

    with pytest.raises(error_type):
        transition(run(state), event(event_type), context(guards=ALL_GUARDS))


def test_live_environment_guard_blocks_start_without_reading_environment() -> None:
    with pytest.raises(GuardConditionError) as error_info:
        transition(
            run(),
            event(QualificationEventType.START_QUALIFICATION),
            context(guards=frozenset({Guard.SCENARIO_AUTHORIZED}), environment="LIVE"),
        )

    assert error_info.value.reason_code == "GUARD_PAPER_ENVIRONMENT"
    assert "Paper environment" in str(error_info.value)


def test_emergency_stop_guard_blocks_consequential_transition() -> None:
    guards = frozenset(
        {
            Guard.APPROVAL_NOT_EXPIRED,
            Guard.NO_DUPLICATE_KEY,
        }
    )

    with pytest.raises(GuardConditionError) as error_info:
        transition(
            run(QualificationState.APPROVED),
            event(QualificationEventType.SUBMISSION_STARTED),
            context(guards=guards),
        )

    assert "Emergency stop" in str(error_info.value)


def test_apply_transition_returns_new_run_without_mutating_original() -> None:
    original = run()
    decision = transition(
        original,
        event(QualificationEventType.START_QUALIFICATION),
        context(guards=frozenset({Guard.SCENARIO_AUTHORIZED, Guard.PAPER_ENVIRONMENT})),
    )

    updated = apply_transition(original, decision)

    assert original.state is QualificationState.NOT_STARTED
    assert original.state_revision == 0
    assert updated.state is QualificationState.PRECHECK_PENDING
    assert updated.state_revision == 1


def test_idempotent_replay_returns_recorded_result_without_side_effects() -> None:
    original = run(QualificationState.SUBMISSION_PENDING, revision=10)
    original_event = event(QualificationEventType.BROKER_REQUEST_SENT, key="send-1")
    first = transition(
        original,
        original_event,
        context(
            10,
            guards=frozenset(
                {
                    Guard.BROKER_CAPABILITY_AVAILABLE,
                    Guard.NO_DUPLICATE_KEY,
                    Guard.PAPER_ENVIRONMENT,
                }
            ),
        ),
    )
    applied = apply_transition(original, first)
    replay = transition(
        applied,
        original_event,
        context(
            11,
            prior=PriorCommandRecord(
                idempotency_key=original_event.idempotency_key,
                payload_fingerprint=original_event.payload_fingerprint,
                decision=first,
            ),
        ),
    )

    assert replay.replayed is True
    assert replay.previous_state is QualificationState.SUBMITTED
    assert replay.next_state is QualificationState.SUBMITTED
    assert replay.previous_revision == 11
    assert replay.next_revision == 11
    assert replay.side_effects == ()


def test_idempotency_conflict_is_deterministic_and_safe() -> None:
    current = run(QualificationState.SUBMITTED, revision=1)
    original_event = event(QualificationEventType.BROKER_ACKNOWLEDGED, key="ack-1")
    first = transition(
        current,
        original_event,
        context(1, guards=frozenset({Guard.BROKER_RESPONSE_MATCHES})),
    )

    with pytest.raises(IdempotencyConflictError) as error_info:
        transition(
            apply_transition(current, first),
            event(
                QualificationEventType.BROKER_ACKNOWLEDGED,
                key="ack-1",
                fingerprint=("different-quantity",),
            ),
            context(
                2,
                prior=PriorCommandRecord(
                    idempotency_key=original_event.idempotency_key,
                    payload_fingerprint=original_event.payload_fingerprint,
                    decision=first,
                ),
            ),
        )

    assert error_info.value.reason_code == "IDEMPOTENCY_CONFLICT"
    assert "different input" in str(error_info.value)


def test_duplicate_broker_fill_observation_does_not_duplicate_state_mutation() -> None:
    current = run(QualificationState.ACKNOWLEDGED, revision=4)
    fill_event = event(QualificationEventType.BROKER_FILL_REPORTED, key="fill-1")
    first = transition(
        current,
        fill_event,
        context(4, guards=frozenset({Guard.FULL_FILL_EVIDENCE})),
    )
    replay = transition(
        apply_transition(current, first),
        fill_event,
        context(
            5,
            prior=PriorCommandRecord(
                idempotency_key=fill_event.idempotency_key,
                payload_fingerprint=fill_event.payload_fingerprint,
                decision=first,
            ),
        ),
    )

    assert first.next_state is QualificationState.FILLED
    assert replay.next_state is QualificationState.FILLED
    assert replay.next_revision == 5
    assert replay.side_effects == ()


def test_diagnostic_rejection_preserves_state_revision_and_has_no_side_effects() -> (
    None
):
    current = run(QualificationState.READY_FOR_APPROVAL, revision=8)
    rejection = diagnostic_rejection(
        current,
        event(QualificationEventType.BROKER_REQUEST_SENT),
        context(8),
        reason_code="INVALID_TRANSITION",
        safe_message="This transition is not allowed from the current state.",
    )

    assert rejection.accepted is False
    assert rejection.previous_state is QualificationState.READY_FOR_APPROVAL
    assert rejection.next_state is QualificationState.READY_FOR_APPROVAL
    assert rejection.previous_revision == 8
    assert rejection.next_revision == 8
    assert rejection.side_effects == ()
    assert rejection.evidence_intents[0].diagnostic is True


def test_transition_is_deterministic_for_identical_inputs() -> None:
    current = run(QualificationState.CANCELLED, revision=6)
    qualification_event = event(QualificationEventType.QUALIFICATION_CRITERIA_MET)
    transition_context = context(
        6,
        guards=frozenset(
            {
                Guard.SCENARIO_REQUIRES_CANCELLATION_CLEANUP,
                Guard.CRITERIA_EVIDENCE_COMPLETE,
            }
        ),
    )

    first = transition(current, qualification_event, transition_context)
    second = transition(current, qualification_event, transition_context)

    assert first == second


def test_safe_messages_and_evidence_do_not_echo_secret_bearing_payload() -> None:
    decision = transition(
        run(),
        event(
            QualificationEventType.START_QUALIFICATION,
            fingerprint=(SECRET_SENTINEL,),
        ),
        context(guards=frozenset({Guard.SCENARIO_AUTHORIZED, Guard.PAPER_ENVIRONMENT})),
    )

    rendered = repr(decision.evidence_intents) + decision.safe_message
    assert SECRET_SENTINEL not in rendered
    assert "API_KEY" not in rendered
    assert "TOKEN" not in rendered
    assert "PASSWORD" not in rendered


def test_default_positive_scenario_path_reaches_qualified_only_after_cancellation_cleanup() -> (
    None
):
    current = run()
    path = [
        (
            QualificationEventType.START_QUALIFICATION,
            frozenset({Guard.SCENARIO_AUTHORIZED, Guard.PAPER_ENVIRONMENT}),
        ),
        (
            QualificationEventType.PRECHECKS_PASSED,
            frozenset(
                {
                    Guard.PAPER_ENVIRONMENT,
                    Guard.BROKER_SUPPORTED,
                    Guard.CONFIGURATION_VALID,
                    Guard.CREDENTIALS_AVAILABLE,
                    Guard.EVIDENCE_AVAILABLE,
                }
            ),
        ),
        (
            QualificationEventType.APPROVAL_REQUESTED,
            frozenset(
                {Guard.APPROVAL_SURFACE_AVAILABLE, Guard.EMERGENCY_STOP_INACTIVE}
            ),
        ),
        (
            QualificationEventType.OPERATOR_APPROVED,
            frozenset(
                {
                    Guard.OPERATOR_APPROVAL_VALID,
                    Guard.PLAN_CURRENT,
                    Guard.EVIDENCE_AVAILABLE,
                }
            ),
        ),
        (
            QualificationEventType.SUBMISSION_STARTED,
            frozenset(
                {
                    Guard.APPROVAL_NOT_EXPIRED,
                    Guard.NO_DUPLICATE_KEY,
                    Guard.EMERGENCY_STOP_INACTIVE,
                }
            ),
        ),
        (
            QualificationEventType.BROKER_REQUEST_SENT,
            frozenset(
                {
                    Guard.BROKER_CAPABILITY_AVAILABLE,
                    Guard.NO_DUPLICATE_KEY,
                    Guard.PAPER_ENVIRONMENT,
                }
            ),
        ),
        (
            QualificationEventType.BROKER_ACKNOWLEDGED,
            frozenset({Guard.BROKER_RESPONSE_MATCHES}),
        ),
        (
            QualificationEventType.CANCELLATION_REQUESTED,
            frozenset(
                {
                    Guard.CANCELLATION_SUPPORTED,
                    Guard.NO_TERMINAL_BROKER_STATE,
                    Guard.EMERGENCY_STOP_INACTIVE,
                }
            ),
        ),
        (
            QualificationEventType.BROKER_CANCELLATION_CONFIRMED,
            frozenset({Guard.CANCELLATION_CONFIRMATION_MATCHES}),
        ),
        (
            QualificationEventType.QUALIFICATION_CRITERIA_MET,
            frozenset(
                {
                    Guard.SCENARIO_REQUIRES_CANCELLATION_CLEANUP,
                    Guard.CRITERIA_EVIDENCE_COMPLETE,
                }
            ),
        ),
    ]

    for index, (event_type, guards) in enumerate(path):
        decision = transition(
            current,
            event(event_type, key=f"key-{index}"),
            context(index, guards=guards),
        )
        current = apply_transition(current, decision)

    assert current.state is QualificationState.QUALIFIED
    assert current.result is QualificationResult.PASSED
    assert current.state_revision == len(path)
