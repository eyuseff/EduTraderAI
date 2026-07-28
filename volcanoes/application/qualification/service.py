"""Presentation-neutral Paper qualification application service."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from volcanoes.application.qualification.contracts import (
    ActorType,
    CommandId,
    CorrelationId,
    EvidenceIntent,
    Guard,
    IdempotencyKey,
    PaperQualificationRun,
    PriorCommandRecord,
    QualificationEvent,
    QualificationEventType,
    QualificationResult,
    QualificationRunId,
    QualificationScenarioId,
    QualificationState,
    RetryClassification,
    SideEffectIntent,
    SideEffectIntentType,
    StateRevision,
    TransitionContext,
    TransitionDecision,
)
from volcanoes.application.qualification.errors import QualificationTransitionError
from volcanoes.application.qualification.ports import (
    EvidenceRecordReference,
    QualificationEvidenceRecorder,
    QualificationRunRepository,
    SaveResult,
)
from volcanoes.application.qualification.state_machine import (
    apply_transition,
    diagnostic_rejection,
    transition,
)


class ExecutionPlanKind(StrEnum):
    """High-level interpretation of a descriptive execution plan."""

    NO_EXTERNAL_ACTION_REQUIRED = "NO_EXTERNAL_ACTION_REQUIRED"
    OPERATOR_ACTION_REQUIRED = "OPERATOR_ACTION_REQUIRED"
    BROKER_ACTION_PROPOSED = "BROKER_ACTION_PROPOSED"
    BROKER_OBSERVATION_REQUIRED = "BROKER_OBSERVATION_REQUIRED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    QUALIFICATION_FINALIZATION_PROPOSED = "QUALIFICATION_FINALIZATION_PROPOSED"
    CONSEQUENTIAL_ACTION_BLOCKED = "CONSEQUENTIAL_ACTION_BLOCKED"


@dataclass(frozen=True, slots=True)
class QualificationApplicationCommand:
    """Typed command accepted by the Paper qualification application service."""

    qualification_run_id: QualificationRunId
    qualification_scenario_id: QualificationScenarioId
    correlation_id: CorrelationId
    event_type: QualificationEventType
    expected_revision: StateRevision
    command_id: CommandId
    idempotency_key: IdempotencyKey
    actor_type: ActorType
    satisfied_guards: frozenset[Guard] = frozenset()
    payload_fingerprint: tuple[str, ...] = ()
    object_reference: str | None = None
    environment: str = "PAPER"
    recovered_state: QualificationState | None = None

    def __post_init__(self) -> None:
        for name in (
            "qualification_run_id",
            "qualification_scenario_id",
            "correlation_id",
            "command_id",
            "idempotency_key",
            "environment",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ApplicationCommandValidationError(
                    reason_code="INVALID_COMMAND",
                    safe_message=f"{name} cannot be empty.",
                )
        if not isinstance(self.event_type, QualificationEventType):
            raise ApplicationCommandValidationError(
                reason_code="INVALID_COMMAND",
                safe_message="event_type must be a QualificationEventType.",
            )
        if not isinstance(self.expected_revision, int) or self.expected_revision < 0:
            raise ApplicationCommandValidationError(
                reason_code="INVALID_COMMAND",
                safe_message="expected_revision must be a non-negative integer.",
            )
        if not isinstance(self.actor_type, ActorType):
            raise ApplicationCommandValidationError(
                reason_code="INVALID_COMMAND",
                safe_message="actor_type must be an ActorType.",
            )
        object.__setattr__(self, "satisfied_guards", frozenset(self.satisfied_guards))
        object.__setattr__(
            self,
            "payload_fingerprint",
            tuple(str(item) for item in self.payload_fingerprint),
        )
        if self.object_reference is not None and not self.object_reference.strip():
            raise ApplicationCommandValidationError(
                reason_code="INVALID_COMMAND",
                safe_message="object_reference cannot be blank when supplied.",
            )

    @property
    def normalized_payload(self) -> tuple[str, ...]:
        """Return deterministic command identity for idempotency comparison."""

        return (
            self.event_type.value,
            self.environment,
            self.actor_type.value,
            *(self.payload_fingerprint),
            self.object_reference or "",
        )

    def to_event(self) -> QualificationEvent:
        """Convert the application command into a domain transition event."""

        return QualificationEvent(
            event_type=self.event_type,
            command_id=self.command_id,
            idempotency_key=self.idempotency_key,
            actor_type=self.actor_type,
            payload_fingerprint=self.normalized_payload,
            object_reference=self.object_reference,
        )

    def to_context(
        self,
        *,
        prior_command: PriorCommandRecord | None,
    ) -> TransitionContext:
        """Build deterministic transition context from command facts."""

        return TransitionContext(
            expected_revision=self.expected_revision,
            satisfied_guards=self.satisfied_guards,
            environment=self.environment,
            prior_command=prior_command,
            recovered_state=self.recovered_state,
        )


@dataclass(frozen=True, slots=True)
class QualificationExecutionPlan:
    """Descriptive future work plan; no effect is executed by this object."""

    qualification_run_id: QualificationRunId
    transition_id: str
    source_state: QualificationState
    destination_state: QualificationState
    previous_revision: StateRevision
    next_revision: StateRevision
    side_effect_intents: tuple[SideEffectIntent, ...]
    evidence_intents: tuple[EvidenceIntent, ...]
    retry_classification: RetryClassification
    reconciliation_required: bool
    operator_message: str
    correlation_id: CorrelationId
    command_id: CommandId
    idempotency_key: IdempotencyKey
    plan_kinds: tuple[ExecutionPlanKind, ...]

    @property
    def proposes_broker_action(self) -> bool:
        """Return whether the plan only describes a future broker action."""

        return ExecutionPlanKind.BROKER_ACTION_PROPOSED in self.plan_kinds


@dataclass(frozen=True, slots=True)
class QualificationApplicationResult:
    """Structured result returned by the qualification application service."""

    qualification_run_id: QualificationRunId
    accepted: bool
    code: str
    safe_message: str
    previous_run: PaperQualificationRun | None
    resulting_run: PaperQualificationRun | None
    transition_decision: TransitionDecision | None
    execution_plan: QualificationExecutionPlan | None
    evidence_records: tuple[EvidenceRecordReference, ...] = ()
    save_result: SaveResult | None = None
    replayed: bool = False
    reconciliation_required: bool = False


@dataclass(frozen=True, slots=True)
class QualificationApplicationError(Exception):
    """Base application-layer failure with safe structured metadata."""

    reason_code: str
    safe_message: str

    def __post_init__(self) -> None:
        if not self.reason_code.strip():
            raise ValueError("reason_code cannot be empty.")
        if not self.safe_message.strip():
            raise ValueError("safe_message cannot be empty.")
        Exception.__init__(self, self.safe_message)

    def __str__(self) -> str:
        return self.safe_message


class QualificationRunNotFoundError(QualificationApplicationError):
    """Raised when a command requires a run that does not exist."""


class QualificationRunAlreadyExistsError(QualificationApplicationError):
    """Raised when a new run command conflicts with an existing run."""


class QualificationRunSaveConflictError(QualificationApplicationError):
    """Raised when repository revision-aware save fails."""


class EvidenceRecordingError(QualificationApplicationError):
    """Raised when the abstract evidence recorder fails."""


class ApplicationCommandValidationError(QualificationApplicationError):
    """Raised when an application command is structurally invalid."""


class ApplicationPortError(QualificationApplicationError):
    """Raised when an abstract port fails unexpectedly."""


class PaperQualificationService:
    """Orchestrate qualification commands around the pure state machine."""

    def __init__(
        self,
        repository: QualificationRunRepository,
        evidence_recorder: QualificationEvidenceRecorder,
    ) -> None:
        self._repository = repository
        self._evidence_recorder = evidence_recorder

    def execute(
        self,
        command: QualificationApplicationCommand,
    ) -> QualificationApplicationResult:
        """Execute one application command without external broker side effects."""

        current_run = self._load_or_create_run(command)
        prior_command = self._prior_command(command)
        event = command.to_event()
        context = command.to_context(prior_command=prior_command)

        try:
            decision = transition(current_run, event, context)
        except QualificationTransitionError as error:
            rejection = diagnostic_rejection(
                current_run,
                event,
                context,
                reason_code=error.reason_code,
                safe_message=error.safe_message,
            )
            return QualificationApplicationResult(
                qualification_run_id=command.qualification_run_id,
                accepted=False,
                code=error.reason_code,
                safe_message=error.safe_message,
                previous_run=current_run,
                resulting_run=current_run,
                transition_decision=rejection,
                execution_plan=self._execution_plan(command, rejection),
                replayed=False,
                reconciliation_required=rejection.reconciliation_required,
            )

        execution_plan = self._execution_plan(command, decision)
        if decision.replayed:
            return QualificationApplicationResult(
                qualification_run_id=command.qualification_run_id,
                accepted=True,
                code="REPLAYED",
                safe_message=decision.safe_message,
                previous_run=current_run,
                resulting_run=current_run,
                transition_decision=decision,
                execution_plan=execution_plan,
                replayed=True,
                reconciliation_required=decision.reconciliation_required,
            )

        resulting_run = apply_transition(current_run, decision)
        evidence_records = self._record_evidence(decision.evidence_intents)
        save_result = self._save_run(
            resulting_run,
            expected_previous_revision=decision.previous_revision,
        )
        self._record_command(
            command.qualification_run_id,
            PriorCommandRecord(
                idempotency_key=command.idempotency_key,
                payload_fingerprint=event.payload_fingerprint,
                decision=decision,
            ),
        )
        return QualificationApplicationResult(
            qualification_run_id=command.qualification_run_id,
            accepted=True,
            code=decision.reason_code,
            safe_message=decision.safe_message,
            previous_run=current_run,
            resulting_run=resulting_run,
            transition_decision=decision,
            execution_plan=execution_plan,
            evidence_records=evidence_records,
            save_result=save_result,
            replayed=False,
            reconciliation_required=decision.reconciliation_required,
        )

    def _load_or_create_run(
        self,
        command: QualificationApplicationCommand,
    ) -> PaperQualificationRun:
        existing = self._get_run(command.qualification_run_id)
        if existing is not None:
            if (
                command.event_type is QualificationEventType.START_QUALIFICATION
                and command.expected_revision == 0
                and existing.state is QualificationState.NOT_STARTED
            ):
                raise QualificationRunAlreadyExistsError(
                    reason_code="RUN_ALREADY_EXISTS",
                    safe_message="Qualification run already exists.",
                )
            return existing

        if command.event_type is not QualificationEventType.START_QUALIFICATION:
            raise QualificationRunNotFoundError(
                reason_code="RUN_NOT_FOUND",
                safe_message="Qualification run was not found.",
            )

        return PaperQualificationRun(
            qualification_run_id=command.qualification_run_id,
            qualification_scenario_id=command.qualification_scenario_id,
            correlation_id=command.correlation_id,
            state=QualificationState.NOT_STARTED,
            result=QualificationResult.PENDING,
            state_revision=StateRevision(0),
        )

    def _get_run(
        self,
        run_id: QualificationRunId,
    ) -> PaperQualificationRun | None:
        try:
            return self._repository.get(run_id)
        except Exception as error:
            raise ApplicationPortError(
                reason_code="REPOSITORY_GET_FAILED",
                safe_message="Qualification run repository could not be read.",
            ) from error

    def _prior_command(
        self,
        command: QualificationApplicationCommand,
    ) -> PriorCommandRecord | None:
        try:
            return self._repository.prior_command(
                command.qualification_run_id,
                command.idempotency_key,
            )
        except Exception as error:
            raise ApplicationPortError(
                reason_code="REPOSITORY_IDEMPOTENCY_READ_FAILED",
                safe_message="Qualification command record could not be read.",
            ) from error

    def _record_evidence(
        self,
        evidence_intents: tuple[EvidenceIntent, ...],
    ) -> tuple[EvidenceRecordReference, ...]:
        try:
            return self._evidence_recorder.record(evidence_intents)
        except Exception as error:
            raise EvidenceRecordingError(
                reason_code="EVIDENCE_RECORDING_FAILED",
                safe_message="Qualification evidence could not be recorded.",
            ) from error

    def _save_run(
        self,
        run: PaperQualificationRun,
        *,
        expected_previous_revision: StateRevision,
    ) -> SaveResult:
        try:
            result = self._repository.save(
                run,
                expected_previous_revision=expected_previous_revision,
            )
        except Exception as error:
            raise QualificationRunSaveConflictError(
                reason_code="RUN_SAVE_FAILED",
                safe_message="Qualification run state could not be recorded.",
            ) from error
        if not result.saved:
            raise QualificationRunSaveConflictError(
                reason_code=result.reason_code,
                safe_message=result.safe_message,
            )
        return result

    def _record_command(
        self,
        run_id: QualificationRunId,
        record: PriorCommandRecord,
    ) -> None:
        try:
            self._repository.record_command(run_id, record)
        except Exception as error:
            raise ApplicationPortError(
                reason_code="REPOSITORY_IDEMPOTENCY_WRITE_FAILED",
                safe_message="Qualification command record could not be written.",
            ) from error

    @staticmethod
    def _execution_plan(
        command: QualificationApplicationCommand,
        decision: TransitionDecision,
    ) -> QualificationExecutionPlan:
        evidence_intents = () if decision.replayed else decision.evidence_intents
        side_effects = () if decision.replayed else decision.side_effects
        return QualificationExecutionPlan(
            qualification_run_id=command.qualification_run_id,
            transition_id=decision.transition_id,
            source_state=decision.previous_state,
            destination_state=decision.next_state,
            previous_revision=decision.previous_revision,
            next_revision=decision.next_revision,
            side_effect_intents=side_effects,
            evidence_intents=evidence_intents,
            retry_classification=decision.retry_classification,
            reconciliation_required=decision.reconciliation_required,
            operator_message=decision.safe_message,
            correlation_id=command.correlation_id,
            command_id=command.command_id,
            idempotency_key=command.idempotency_key,
            plan_kinds=_plan_kinds(decision, side_effects),
        )


def _plan_kinds(
    decision: TransitionDecision,
    side_effects: tuple[SideEffectIntent, ...],
) -> tuple[ExecutionPlanKind, ...]:
    if not decision.accepted:
        return (ExecutionPlanKind.CONSEQUENTIAL_ACTION_BLOCKED,)
    if decision.reconciliation_required:
        return (ExecutionPlanKind.RECONCILIATION_REQUIRED,)
    intent_types = {intent.intent_type for intent in side_effects}
    if not intent_types:
        return (ExecutionPlanKind.NO_EXTERNAL_ACTION_REQUIRED,)
    kinds: list[ExecutionPlanKind] = []
    if SideEffectIntentType.REQUEST_OPERATOR_APPROVAL in intent_types:
        kinds.append(ExecutionPlanKind.OPERATOR_ACTION_REQUIRED)
    if intent_types & {
        SideEffectIntentType.SEND_BROKER_REQUEST,
        SideEffectIntentType.REQUEST_BROKER_CANCELLATION,
    }:
        kinds.append(ExecutionPlanKind.BROKER_ACTION_PROPOSED)
    if intent_types & {
        SideEffectIntentType.RECORD_BROKER_REFERENCE,
        SideEffectIntentType.RECORD_BROKER_LIFECYCLE,
    }:
        kinds.append(ExecutionPlanKind.BROKER_OBSERVATION_REQUIRED)
    if SideEffectIntentType.START_RECONCILIATION in intent_types:
        kinds.append(ExecutionPlanKind.RECONCILIATION_REQUIRED)
    if SideEffectIntentType.FINALIZE_QUALIFICATION in intent_types:
        kinds.append(ExecutionPlanKind.QUALIFICATION_FINALIZATION_PROPOSED)
    if SideEffectIntentType.BLOCK_CONSEQUENTIAL_ACTION in intent_types:
        kinds.append(ExecutionPlanKind.CONSEQUENTIAL_ACTION_BLOCKED)
    return tuple(kinds) or (ExecutionPlanKind.NO_EXTERNAL_ACTION_REQUIRED,)
