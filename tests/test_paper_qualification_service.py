"""Application-service tests for Paper qualification orchestration."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from volcanoes.application.qualification import (
    ActorType,
    ApplicationPortError,
    CommandId,
    CorrelationId,
    EvidenceIntent,
    EvidenceRecordReference,
    EvidenceRecordingError,
    ExecutionPlanKind,
    Guard,
    IdempotencyKey,
    PaperQualificationRun,
    PaperQualificationService,
    PriorCommandRecord,
    QualificationApplicationCommand,
    QualificationEventType,
    QualificationResult,
    QualificationRunId,
    QualificationRunNotFoundError,
    QualificationRunSaveConflictError,
    QualificationScenarioId,
    QualificationState,
    SaveResult,
    SideEffectIntentType,
    StateRevision,
)

RUN_ID = QualificationRunId("pq-run-service-001")
SCENARIO_ID = QualificationScenarioId("PQ-SCN-005")
CORRELATION_ID = CorrelationId("service-correlation-001")
SECRET_SENTINEL = "SECRET-API_KEY-TOKEN-PASSWORD"


class InMemoryQualificationRunRepository:
    """Deterministic fake repository used only by tests."""

    def __init__(self) -> None:
        self.runs: dict[QualificationRunId, PaperQualificationRun] = {}
        self.records: dict[
            tuple[QualificationRunId, IdempotencyKey], PriorCommandRecord
        ] = {}
        self.operations: list[str] = []
        self.fail_get = False
        self.fail_save = False
        self.conflict_save = False
        self.fail_record_command = False

    def get(self, run_id: QualificationRunId) -> PaperQualificationRun | None:
        self.operations.append("get")
        if self.fail_get:
            raise RuntimeError("repository unavailable")
        return self.runs.get(run_id)

    def save(
        self,
        run: PaperQualificationRun,
        *,
        expected_previous_revision: StateRevision | None,
    ) -> SaveResult:
        self.operations.append("save")
        if self.fail_save:
            raise RuntimeError("save unavailable")
        existing = self.runs.get(run.qualification_run_id)
        if self.conflict_save or (
            existing is not None
            and expected_previous_revision is not None
            and existing.state_revision != expected_previous_revision
        ):
            return SaveResult(
                saved=False,
                previous_revision=existing.state_revision if existing else None,
                current_revision=run.state_revision,
                reason_code="SAVE_CONFLICT",
                safe_message="Qualification run state could not be recorded.",
            )
        self.runs[run.qualification_run_id] = run
        return SaveResult(
            saved=True,
            previous_revision=expected_previous_revision,
            current_revision=run.state_revision,
        )

    def prior_command(
        self,
        run_id: QualificationRunId,
        idempotency_key: IdempotencyKey,
    ) -> PriorCommandRecord | None:
        self.operations.append("prior_command")
        return self.records.get((run_id, idempotency_key))

    def record_command(
        self,
        run_id: QualificationRunId,
        record: PriorCommandRecord,
    ) -> None:
        self.operations.append("record_command")
        if self.fail_record_command:
            raise RuntimeError("record unavailable")
        self.records[(run_id, record.idempotency_key)] = record


class RecordingEvidenceRecorder:
    """Deterministic fake evidence recorder used only by tests."""

    def __init__(self) -> None:
        self.intents: list[EvidenceIntent] = []
        self.operations: list[str] = []
        self.fail = False

    def record(
        self,
        evidence_intents: tuple[EvidenceIntent, ...],
    ) -> tuple[EvidenceRecordReference, ...]:
        self.operations.append("record_evidence")
        if self.fail:
            raise RuntimeError("evidence unavailable")
        self.intents.extend(evidence_intents)
        return tuple(
            EvidenceRecordReference(
                evidence_id=f"evidence-{len(self.intents) - len(evidence_intents) + index + 1}",
                transition_id=intent.transition_id,
                correlation_id=intent.correlation_id,
            )
            for index, intent in enumerate(evidence_intents)
        )


def service_stack() -> tuple[
    PaperQualificationService,
    InMemoryQualificationRunRepository,
    RecordingEvidenceRecorder,
]:
    repository = InMemoryQualificationRunRepository()
    recorder = RecordingEvidenceRecorder()
    return PaperQualificationService(repository, recorder), repository, recorder


def command(
    event_type: QualificationEventType,
    *,
    revision: int = 0,
    key: str = "idem-1",
    guards: frozenset[Guard] = frozenset(),
    fingerprint: tuple[str, ...] = ("payload",),
    environment: str = "PAPER",
    actor: ActorType = ActorType.APPLICATION,
) -> QualificationApplicationCommand:
    return QualificationApplicationCommand(
        qualification_run_id=RUN_ID,
        qualification_scenario_id=SCENARIO_ID,
        correlation_id=CORRELATION_ID,
        event_type=event_type,
        expected_revision=StateRevision(revision),
        command_id=CommandId(f"command-{key}"),
        idempotency_key=IdempotencyKey(key),
        actor_type=actor,
        satisfied_guards=guards,
        payload_fingerprint=fingerprint,
        object_reference="object-1",
        environment=environment,
    )


def seed_run(
    repository: InMemoryQualificationRunRepository,
    state: QualificationState,
    *,
    revision: int = 0,
    result: QualificationResult = QualificationResult.PENDING,
) -> PaperQualificationRun:
    seeded = PaperQualificationRun(
        qualification_run_id=RUN_ID,
        qualification_scenario_id=SCENARIO_ID,
        correlation_id=CORRELATION_ID,
        state=state,
        result=result,
        state_revision=StateRevision(revision),
    )
    repository.runs[RUN_ID] = seeded
    return seeded


def test_start_new_qualification_run_records_evidence_and_state() -> None:
    service, repository, recorder = service_stack()

    result = service.execute(
        command(
            QualificationEventType.START_QUALIFICATION,
            guards=frozenset({Guard.SCENARIO_AUTHORIZED, Guard.PAPER_ENVIRONMENT}),
        )
    )

    assert result.accepted is True
    assert result.resulting_run is not None
    assert result.resulting_run.state is QualificationState.PRECHECK_PENDING
    assert result.resulting_run.state_revision == 1
    assert result.execution_plan is not None
    assert result.execution_plan.plan_kinds == (
        ExecutionPlanKind.NO_EXTERNAL_ACTION_REQUIRED,
    )
    assert len(result.evidence_records) == 1
    assert recorder.intents[0].transition_id == "PQ-TRN-001"
    assert repository.operations == ["get", "prior_command", "save", "record_command"]


def test_valid_transition_returns_descriptive_plan_without_executing_effect() -> None:
    service, repository, _recorder = service_stack()
    seed_run(repository, QualificationState.SUBMISSION_PENDING, revision=4)

    result = service.execute(
        command(
            QualificationEventType.BROKER_REQUEST_SENT,
            revision=4,
            key="send",
            guards=frozenset(
                {
                    Guard.BROKER_CAPABILITY_AVAILABLE,
                    Guard.NO_DUPLICATE_KEY,
                    Guard.PAPER_ENVIRONMENT,
                }
            ),
        )
    )

    assert result.accepted is True
    assert result.transition_decision is not None
    assert result.transition_decision.transition_id == "PQ-TRN-010"
    assert result.resulting_run is not None
    assert result.resulting_run.state is QualificationState.SUBMITTED
    assert result.execution_plan is not None
    assert result.execution_plan.proposes_broker_action is True
    assert tuple(
        intent.intent_type for intent in result.execution_plan.side_effect_intents
    ) == (SideEffectIntentType.SEND_BROKER_REQUEST,)


def test_save_revision_increments_once() -> None:
    service, repository, _recorder = service_stack()
    seed_run(repository, QualificationState.READY_FOR_APPROVAL, revision=9)

    result = service.execute(
        command(
            QualificationEventType.APPROVAL_REQUESTED,
            revision=9,
            guards=frozenset(
                {
                    Guard.APPROVAL_SURFACE_AVAILABLE,
                    Guard.EMERGENCY_STOP_INACTIVE,
                }
            ),
        )
    )

    assert result.previous_run is not None
    assert result.resulting_run is not None
    assert result.previous_run.state_revision == 9
    assert result.resulting_run.state_revision == 10
    assert repository.runs[RUN_ID].state_revision == 10


def test_stale_revision_is_domain_rejection_and_preserves_state() -> None:
    service, repository, recorder = service_stack()
    seeded = seed_run(repository, QualificationState.APPROVED, revision=3)

    result = service.execute(
        command(
            QualificationEventType.SUBMISSION_STARTED,
            revision=2,
            guards=frozenset(
                {
                    Guard.APPROVAL_NOT_EXPIRED,
                    Guard.NO_DUPLICATE_KEY,
                    Guard.EMERGENCY_STOP_INACTIVE,
                }
            ),
        )
    )

    assert result.accepted is False
    assert result.code == "STALE_REVISION"
    assert result.resulting_run == seeded
    assert result.execution_plan is not None
    assert result.execution_plan.side_effect_intents == ()
    assert recorder.intents == []
    assert repository.runs[RUN_ID] == seeded


def test_unknown_run_is_application_failure() -> None:
    service, _repository, _recorder = service_stack()

    with pytest.raises(QualificationRunNotFoundError):
        service.execute(
            command(
                QualificationEventType.PRECHECKS_PASSED,
                guards=frozenset({Guard.PAPER_ENVIRONMENT}),
            )
        )


def test_duplicate_run_creation_is_rejected() -> None:
    service, repository, _recorder = service_stack()
    seed_run(repository, QualificationState.NOT_STARTED)

    with pytest.raises(Exception) as error_info:
        service.execute(
            command(
                QualificationEventType.START_QUALIFICATION,
                guards=frozenset({Guard.SCENARIO_AUTHORIZED, Guard.PAPER_ENVIRONMENT}),
            )
        )

    assert error_info.value.__class__.__name__ == "QualificationRunAlreadyExistsError"


def test_replay_same_idempotency_key_returns_recorded_result_without_save_or_evidence() -> (
    None
):
    service, repository, recorder = service_stack()
    initial = seed_run(repository, QualificationState.READY_FOR_APPROVAL, revision=1)
    first_command = command(
        QualificationEventType.APPROVAL_REQUESTED,
        revision=1,
        key="approval",
        guards=frozenset(
            {Guard.APPROVAL_SURFACE_AVAILABLE, Guard.EMERGENCY_STOP_INACTIVE}
        ),
    )
    first = service.execute(first_command)
    assert first.resulting_run is not None
    repository.operations.clear()
    recorder.intents.clear()

    replay = service.execute(
        command(
            QualificationEventType.APPROVAL_REQUESTED,
            revision=initial.state_revision,
            key="approval",
            guards=frozenset(),
        )
    )

    assert replay.accepted is True
    assert replay.replayed is True
    assert replay.resulting_run == repository.runs[RUN_ID]
    assert replay.execution_plan is not None
    assert replay.execution_plan.side_effect_intents == ()
    assert replay.execution_plan.evidence_intents == ()
    assert recorder.intents == []
    assert repository.operations == ["get", "prior_command"]


def test_same_key_with_different_payload_fails_deterministically() -> None:
    service, repository, _recorder = service_stack()
    seed_run(repository, QualificationState.READY_FOR_APPROVAL, revision=1)
    first = service.execute(
        command(
            QualificationEventType.APPROVAL_REQUESTED,
            revision=1,
            key="approval",
            guards=frozenset(
                {Guard.APPROVAL_SURFACE_AVAILABLE, Guard.EMERGENCY_STOP_INACTIVE}
            ),
            fingerprint=("first",),
        )
    )
    assert first.accepted is True

    conflict = service.execute(
        command(
            QualificationEventType.APPROVAL_REQUESTED,
            revision=2,
            key="approval",
            guards=frozenset(
                {Guard.APPROVAL_SURFACE_AVAILABLE, Guard.EMERGENCY_STOP_INACTIVE}
            ),
            fingerprint=("changed",),
        )
    )

    assert conflict.accepted is False
    assert conflict.code == "IDEMPOTENCY_CONFLICT"
    assert conflict.execution_plan is not None
    assert conflict.execution_plan.side_effect_intents == ()


def test_guard_failure_preserves_state_and_does_not_record_evidence() -> None:
    service, repository, recorder = service_stack()
    seeded = seed_run(repository, QualificationState.READY_FOR_APPROVAL)

    result = service.execute(
        command(QualificationEventType.APPROVAL_REQUESTED, guards=frozenset())
    )

    assert result.accepted is False
    assert result.resulting_run == seeded
    assert result.execution_plan is not None
    assert result.execution_plan.plan_kinds == (
        ExecutionPlanKind.CONSEQUENTIAL_ACTION_BLOCKED,
    )
    assert recorder.intents == []


def test_invalid_transition_preserves_state() -> None:
    service, repository, _recorder = service_stack()
    seeded = seed_run(repository, QualificationState.APPROVED)

    result = service.execute(
        command(
            QualificationEventType.BROKER_ACKNOWLEDGED,
            guards=frozenset({Guard.BROKER_RESPONSE_MATCHES}),
        )
    )

    assert result.accepted is False
    assert result.code == "INVALID_TRANSITION"
    assert result.resulting_run == seeded


def test_terminal_state_rejects_mutation() -> None:
    service, repository, _recorder = service_stack()
    seed_run(
        repository, QualificationState.QUALIFIED, result=QualificationResult.PASSED
    )

    result = service.execute(
        command(
            QualificationEventType.SUBMISSION_STARTED,
            guards=frozenset(
                {
                    Guard.APPROVAL_NOT_EXPIRED,
                    Guard.NO_DUPLICATE_KEY,
                    Guard.EMERGENCY_STOP_INACTIVE,
                }
            ),
        )
    )

    assert result.accepted is False
    assert result.code == "TERMINAL_STATE"


def test_evidence_failure_is_distinct_from_transition_failure() -> None:
    service, repository, recorder = service_stack()
    recorder.fail = True
    seeded = seed_run(repository, QualificationState.READY_FOR_APPROVAL)

    with pytest.raises(EvidenceRecordingError):
        service.execute(
            command(
                QualificationEventType.APPROVAL_REQUESTED,
                guards=frozenset(
                    {
                        Guard.APPROVAL_SURFACE_AVAILABLE,
                        Guard.EMERGENCY_STOP_INACTIVE,
                    }
                ),
            )
        )

    assert repository.runs[RUN_ID] == seeded
    assert "save" not in repository.operations


def test_repository_save_conflict_after_evidence_is_distinct() -> None:
    service, repository, recorder = service_stack()
    repository.conflict_save = True
    seed_run(repository, QualificationState.READY_FOR_APPROVAL)

    with pytest.raises(QualificationRunSaveConflictError):
        service.execute(
            command(
                QualificationEventType.APPROVAL_REQUESTED,
                guards=frozenset(
                    {
                        Guard.APPROVAL_SURFACE_AVAILABLE,
                        Guard.EMERGENCY_STOP_INACTIVE,
                    }
                ),
            )
        )

    assert len(recorder.intents) == 1
    assert repository.operations[-1] == "save"


def test_port_failure_does_not_become_domain_rejection() -> None:
    service, repository, _recorder = service_stack()
    repository.fail_get = True

    with pytest.raises(ApplicationPortError):
        service.execute(
            command(
                QualificationEventType.START_QUALIFICATION,
                guards=frozenset({Guard.SCENARIO_AUTHORIZED, Guard.PAPER_ENVIRONMENT}),
            )
        )


def test_request_cancellation_plan_is_descriptive_only() -> None:
    service, repository, _recorder = service_stack()
    seed_run(repository, QualificationState.ACKNOWLEDGED)

    result = service.execute(
        command(
            QualificationEventType.CANCELLATION_REQUESTED,
            key="cancel",
            guards=frozenset(
                {
                    Guard.CANCELLATION_SUPPORTED,
                    Guard.NO_TERMINAL_BROKER_STATE,
                    Guard.EMERGENCY_STOP_INACTIVE,
                }
            ),
        )
    )

    assert result.execution_plan is not None
    assert result.execution_plan.plan_kinds == (
        ExecutionPlanKind.BROKER_ACTION_PROPOSED,
    )
    assert tuple(
        intent.intent_type for intent in result.execution_plan.side_effect_intents
    ) == (SideEffectIntentType.REQUEST_BROKER_CANCELLATION,)


def test_reconciliation_plan_does_not_execute_reconciliation() -> None:
    service, repository, _recorder = service_stack()
    seed_run(repository, QualificationState.UNRESOLVED)

    result = service.execute(
        command(
            QualificationEventType.RECONCILIATION_STARTED,
            key="reconcile",
            guards=frozenset({Guard.READ_ONLY_RECONCILIATION_AVAILABLE}),
        )
    )

    assert result.reconciliation_required is True
    assert result.execution_plan is not None
    assert result.execution_plan.plan_kinds == (
        ExecutionPlanKind.RECONCILIATION_REQUIRED,
    )


def test_paper_only_guard_rejects_non_paper_context() -> None:
    service, _repository, _recorder = service_stack()

    result = service.execute(
        command(
            QualificationEventType.START_QUALIFICATION,
            guards=frozenset({Guard.SCENARIO_AUTHORIZED}),
            environment="LIVE",
        )
    )

    assert result.accepted is False
    assert result.code == "GUARD_PAPER_ENVIRONMENT"
    assert result.execution_plan is not None
    assert result.execution_plan.side_effect_intents == ()


def test_safe_messages_do_not_echo_secret_payloads() -> None:
    service, _repository, _recorder = service_stack()

    result = service.execute(
        command(
            QualificationEventType.START_QUALIFICATION,
            guards=frozenset({Guard.SCENARIO_AUTHORIZED}),
            fingerprint=(SECRET_SENTINEL,),
        )
    )

    rendered = repr(result)
    assert SECRET_SENTINEL not in rendered
    assert "API_KEY" not in rendered
    assert "TOKEN" not in rendered
    assert "PASSWORD" not in rendered


def test_application_result_preserves_transition_correlation_and_command_identity() -> (
    None
):
    service, _repository, _recorder = service_stack()

    result = service.execute(
        command(
            QualificationEventType.START_QUALIFICATION,
            key="identity",
            guards=frozenset({Guard.SCENARIO_AUTHORIZED, Guard.PAPER_ENVIRONMENT}),
        )
    )

    assert result.transition_decision is not None
    assert result.transition_decision.transition_id == "PQ-TRN-001"
    assert result.execution_plan is not None
    assert result.execution_plan.correlation_id == CORRELATION_ID
    assert result.execution_plan.command_id == CommandId("command-identity")
    assert result.execution_plan.idempotency_key == IdempotencyKey("identity")


def test_operation_ordering_is_deterministic() -> None:
    service, repository, recorder = service_stack()

    service.execute(
        command(
            QualificationEventType.START_QUALIFICATION,
            guards=frozenset({Guard.SCENARIO_AUTHORIZED, Guard.PAPER_ENVIRONMENT}),
        )
    )

    assert repository.operations == ["get", "prior_command", "save", "record_command"]
    assert recorder.operations == ["record_evidence"]


def test_same_command_against_same_state_produces_equivalent_logical_result() -> None:
    first_service, _first_repo, _first_recorder = service_stack()
    second_service, _second_repo, _second_recorder = service_stack()
    start = command(
        QualificationEventType.START_QUALIFICATION,
        guards=frozenset({Guard.SCENARIO_AUTHORIZED, Guard.PAPER_ENVIRONMENT}),
    )

    first = first_service.execute(start)
    second = second_service.execute(start)

    assert first.transition_decision == second.transition_decision
    assert first.execution_plan == second.execution_plan


def test_command_model_is_immutable() -> None:
    sample = command(QualificationEventType.START_QUALIFICATION)

    with pytest.raises(FrozenInstanceError):
        sample.environment = "LIVE"  # type: ignore[misc]


def test_default_positive_scenario_orchestration_uses_fake_ports_only() -> None:
    service, repository, recorder = service_stack()
    sequence = [
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

    result = None
    for index, (event_type, guards) in enumerate(sequence):
        result = service.execute(
            command(event_type, revision=index, key=f"default-{index}", guards=guards)
        )

    assert result is not None
    assert result.accepted is True
    assert result.resulting_run is not None
    assert result.resulting_run.state is QualificationState.QUALIFIED
    assert result.resulting_run.result is QualificationResult.PASSED
    assert repository.runs[RUN_ID].state_revision == len(sequence)
    assert len(recorder.intents) == len(sequence)
    assert recorder.intents[-1].transition_id == "PQ-TRN-030"
