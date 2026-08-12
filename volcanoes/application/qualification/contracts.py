"""Immutable contracts for Paper qualification state transitions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import NewType, Self

QualificationRunId = NewType("QualificationRunId", str)
QualificationScenarioId = NewType("QualificationScenarioId", str)
CorrelationId = NewType("CorrelationId", str)
CommandId = NewType("CommandId", str)
IdempotencyKey = NewType("IdempotencyKey", str)
StateRevision = NewType("StateRevision", int)


class QualificationState(StrEnum):
    """Accepted ADR-004 Paper qualification workflow states."""

    NOT_STARTED = "NOT_STARTED"
    PRECHECK_PENDING = "PRECHECK_PENDING"
    PRECHECK_FAILED = "PRECHECK_FAILED"
    READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    APPROVED = "APPROVED"
    SUBMISSION_PENDING = "SUBMISSION_PENDING"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNRESOLVED = "UNRESOLVED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    QUALIFIED = "QUALIFIED"
    DISQUALIFIED = "DISQUALIFIED"
    ABORTED = "ABORTED"


class StateCategory(StrEnum):
    """Deterministic state categories from ADR-004."""

    INITIAL = "INITIAL"
    ACTIVE = "ACTIVE"
    WAITING = "WAITING"
    RECOVERABLE_FAILURE = "RECOVERABLE_FAILURE"
    EXTERNALLY_UNCERTAIN = "EXTERNALLY_UNCERTAIN"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    TERMINAL_SUCCESS = "TERMINAL_SUCCESS"
    TERMINAL_FAILURE = "TERMINAL_FAILURE"
    ABORTED = "ABORTED"
    ORDER_LIFECYCLE_TERMINAL = "ORDER_LIFECYCLE_TERMINAL"


STATE_CATEGORIES: tuple[tuple[QualificationState, StateCategory], ...] = (
    (QualificationState.NOT_STARTED, StateCategory.INITIAL),
    (QualificationState.PRECHECK_PENDING, StateCategory.ACTIVE),
    (QualificationState.PRECHECK_FAILED, StateCategory.RECOVERABLE_FAILURE),
    (QualificationState.READY_FOR_APPROVAL, StateCategory.WAITING),
    (QualificationState.APPROVAL_PENDING, StateCategory.WAITING),
    (QualificationState.APPROVED, StateCategory.ACTIVE),
    (QualificationState.SUBMISSION_PENDING, StateCategory.ACTIVE),
    (QualificationState.SUBMITTED, StateCategory.EXTERNALLY_UNCERTAIN),
    (QualificationState.ACKNOWLEDGED, StateCategory.WAITING),
    (QualificationState.PARTIALLY_FILLED, StateCategory.WAITING),
    (QualificationState.FILLED, StateCategory.ORDER_LIFECYCLE_TERMINAL),
    (QualificationState.CANCELLATION_REQUESTED, StateCategory.WAITING),
    (QualificationState.CANCELLED, StateCategory.ORDER_LIFECYCLE_TERMINAL),
    (QualificationState.REJECTED, StateCategory.ORDER_LIFECYCLE_TERMINAL),
    (QualificationState.EXPIRED, StateCategory.ORDER_LIFECYCLE_TERMINAL),
    (QualificationState.UNRESOLVED, StateCategory.EXTERNALLY_UNCERTAIN),
    (
        QualificationState.RECONCILIATION_REQUIRED,
        StateCategory.RECONCILIATION_REQUIRED,
    ),
    (QualificationState.QUALIFIED, StateCategory.TERMINAL_SUCCESS),
    (QualificationState.DISQUALIFIED, StateCategory.TERMINAL_FAILURE),
    (QualificationState.ABORTED, StateCategory.ABORTED),
)

TERMINAL_WORKFLOW_STATES = frozenset(
    {
        QualificationState.QUALIFIED,
        QualificationState.DISQUALIFIED,
        QualificationState.ABORTED,
    }
)


class QualificationResult(StrEnum):
    """Qualification result values, separate from workflow state."""

    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class QualificationEventType(StrEnum):
    """Accepted transition events and commands."""

    START_QUALIFICATION = "START_QUALIFICATION"
    PRECHECKS_PASSED = "PRECHECKS_PASSED"
    PRECHECKS_FAILED = "PRECHECKS_FAILED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    OPERATOR_APPROVED = "OPERATOR_APPROVED"
    OPERATOR_REJECTED = "OPERATOR_REJECTED"
    SUBMISSION_STARTED = "SUBMISSION_STARTED"
    BROKER_REQUEST_SENT = "BROKER_REQUEST_SENT"
    BROKER_ACKNOWLEDGED = "BROKER_ACKNOWLEDGED"
    BROKER_PARTIAL_FILL_REPORTED = "BROKER_PARTIAL_FILL_REPORTED"
    BROKER_FILL_REPORTED = "BROKER_FILL_REPORTED"
    CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"
    BROKER_CANCELLATION_CONFIRMED = "BROKER_CANCELLATION_CONFIRMED"
    BROKER_REJECTED = "BROKER_REJECTED"
    BROKER_EXPIRED = "BROKER_EXPIRED"
    TIMEOUT_DETECTED = "TIMEOUT_DETECTED"
    RECONCILIATION_STARTED = "RECONCILIATION_STARTED"
    RECONCILIATION_RESOLVED = "RECONCILIATION_RESOLVED"
    QUALIFICATION_CRITERIA_MET = "QUALIFICATION_CRITERIA_MET"
    QUALIFICATION_CRITERIA_FAILED = "QUALIFICATION_CRITERIA_FAILED"
    ABORT_REQUESTED = "ABORT_REQUESTED"
    PROCESS_RESTARTED = "PROCESS_RESTARTED"


class Guard(StrEnum):
    """Deterministic guard facts supplied by callers."""

    SCENARIO_AUTHORIZED = "SCENARIO_AUTHORIZED"
    PAPER_ENVIRONMENT = "PAPER_ENVIRONMENT"
    BROKER_SUPPORTED = "BROKER_SUPPORTED"
    CONFIGURATION_VALID = "CONFIGURATION_VALID"
    CREDENTIALS_AVAILABLE = "CREDENTIALS_AVAILABLE"
    EVIDENCE_AVAILABLE = "EVIDENCE_AVAILABLE"
    APPROVAL_SURFACE_AVAILABLE = "APPROVAL_SURFACE_AVAILABLE"
    EMERGENCY_STOP_INACTIVE = "EMERGENCY_STOP_INACTIVE"
    OPERATOR_APPROVAL_VALID = "OPERATOR_APPROVAL_VALID"
    PLAN_CURRENT = "PLAN_CURRENT"
    OPERATOR_REJECTION_CAPTURED = "OPERATOR_REJECTION_CAPTURED"
    APPROVAL_NOT_EXPIRED = "APPROVAL_NOT_EXPIRED"
    NO_DUPLICATE_KEY = "NO_DUPLICATE_KEY"
    BROKER_CAPABILITY_AVAILABLE = "BROKER_CAPABILITY_AVAILABLE"
    BROKER_RESPONSE_MATCHES = "BROKER_RESPONSE_MATCHES"
    PARTIAL_FILL_VALID = "PARTIAL_FILL_VALID"
    FULL_FILL_EVIDENCE = "FULL_FILL_EVIDENCE"
    CANCELLATION_SUPPORTED = "CANCELLATION_SUPPORTED"
    NO_TERMINAL_BROKER_STATE = "NO_TERMINAL_BROKER_STATE"
    CANCELLATION_CONFIRMATION_MATCHES = "CANCELLATION_CONFIRMATION_MATCHES"
    BROKER_REJECTION_MATCHES = "BROKER_REJECTION_MATCHES"
    BROKER_EXPIRATION_MATCHES = "BROKER_EXPIRATION_MATCHES"
    BROKER_OUTCOME_UNKNOWN = "BROKER_OUTCOME_UNKNOWN"
    BROKER_SEND_UNCERTAIN = "BROKER_SEND_UNCERTAIN"
    READ_ONLY_RECONCILIATION_AVAILABLE = "READ_ONLY_RECONCILIATION_AVAILABLE"
    BROKER_TRUTH_FOUND = "BROKER_TRUTH_FOUND"
    BROKER_PROVES_CANCELLATION = "BROKER_PROVES_CANCELLATION"
    BROKER_PROVES_REJECTION_OR_NO_ORDER = "BROKER_PROVES_REJECTION_OR_NO_ORDER"
    RECONCILIATION_FAILED_OR_EVIDENCE_INCOMPLETE = (
        "RECONCILIATION_FAILED_OR_EVIDENCE_INCOMPLETE"
    )
    SCENARIO_REQUIRES_ACK_ONLY = "SCENARIO_REQUIRES_ACK_ONLY"
    SCENARIO_REQUIRES_CANCELLATION_CLEANUP = "SCENARIO_REQUIRES_CANCELLATION_CLEANUP"
    SCENARIO_REQUIRES_FILL = "SCENARIO_REQUIRES_FILL"
    SCENARIO_REQUIRES_REJECTION = "SCENARIO_REQUIRES_REJECTION"
    CRITERIA_EVIDENCE_COMPLETE = "CRITERIA_EVIDENCE_COMPLETE"
    CRITERIA_FAILED = "CRITERIA_FAILED"
    ACTOR_AUTHORIZED_TO_ABORT = "ACTOR_AUTHORIZED_TO_ABORT"
    NO_UNSAFE_BROKER_EFFECT_IN_PROGRESS = "NO_UNSAFE_BROKER_EFFECT_IN_PROGRESS"
    DURABLE_STATE_AND_EVIDENCE_VERIFIED = "DURABLE_STATE_AND_EVIDENCE_VERIFIED"


class RetryClassification(StrEnum):
    """Retry semantics for a transition decision."""

    SAFE_LOCAL_RETRY = "SAFE_LOCAL_RETRY"
    RETRY_AFTER_CORRECTION = "RETRY_AFTER_CORRECTION"
    NON_RETRYABLE_SAME_RUN = "NON_RETRYABLE_SAME_RUN"
    SAFE_READ_RETRY = "SAFE_READ_RETRY"
    SAFE_EVENT_REPLAY = "SAFE_EVENT_REPLAY"
    IDEMPOTENT_EXTERNAL_RETRY_ONLY = "IDEMPOTENT_EXTERNAL_RETRY_ONLY"
    UNSAFE_EXTERNAL_RETRY = "UNSAFE_EXTERNAL_RETRY"
    RECONCILE_BEFORE_RETRY = "RECONCILE_BEFORE_RETRY"
    SAFE_RECOVERY_READ_RETRY = "SAFE_RECOVERY_READ_RETRY"


class SideEffectIntentType(StrEnum):
    """Descriptions of side effects; the core engine never executes them."""

    NONE = "NONE"
    REQUEST_OPERATOR_APPROVAL = "REQUEST_OPERATOR_APPROVAL"
    RECORD_OPERATOR_APPROVAL = "RECORD_OPERATOR_APPROVAL"
    PREPARE_BROKER_SUBMISSION = "PREPARE_BROKER_SUBMISSION"
    SEND_BROKER_REQUEST = "SEND_BROKER_REQUEST"
    RECORD_BROKER_REFERENCE = "RECORD_BROKER_REFERENCE"
    RECORD_BROKER_LIFECYCLE = "RECORD_BROKER_LIFECYCLE"
    REQUEST_BROKER_CANCELLATION = "REQUEST_BROKER_CANCELLATION"
    START_RECONCILIATION = "START_RECONCILIATION"
    FINALIZE_QUALIFICATION = "FINALIZE_QUALIFICATION"
    BLOCK_CONSEQUENTIAL_ACTION = "BLOCK_CONSEQUENTIAL_ACTION"
    RESUME_OR_REQUIRE_RECONCILIATION = "RESUME_OR_REQUIRE_RECONCILIATION"


class ActorType(StrEnum):
    """Safe actor categories for evidence intent."""

    OPERATOR = "OPERATOR"
    APPLICATION = "APPLICATION"
    BROKER = "BROKER"
    SYSTEM = "SYSTEM"
    RECONCILIATION = "RECONCILIATION"


@dataclass(frozen=True, slots=True)
class PaperQualificationRun:
    """Immutable Paper qualification run snapshot."""

    qualification_run_id: QualificationRunId
    qualification_scenario_id: QualificationScenarioId
    correlation_id: CorrelationId
    state: QualificationState = QualificationState.NOT_STARTED
    result: QualificationResult = QualificationResult.PENDING
    state_revision: StateRevision = StateRevision(0)

    def __post_init__(self) -> None:
        for name in (
            "qualification_run_id",
            "qualification_scenario_id",
            "correlation_id",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} cannot be empty.")
        if not isinstance(self.state, QualificationState):
            raise TypeError("state must be a QualificationState.")
        if not isinstance(self.result, QualificationResult):
            raise TypeError("result must be a QualificationResult.")
        if not isinstance(self.state_revision, int) or self.state_revision < 0:
            raise ValueError("state_revision must be a non-negative integer.")

    def with_transition(
        self,
        *,
        state: QualificationState,
        result: QualificationResult,
        state_revision: StateRevision,
    ) -> Self:
        """Return a new snapshot with transition output applied."""

        return replace(
            self,
            state=state,
            result=result,
            state_revision=state_revision,
        )


@dataclass(frozen=True, slots=True)
class QualificationEvent:
    """Immutable transition input event or command."""

    event_type: QualificationEventType
    command_id: CommandId
    idempotency_key: IdempotencyKey
    actor_type: ActorType
    payload_fingerprint: tuple[str, ...] = ()
    object_reference: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, QualificationEventType):
            raise TypeError("event_type must be a QualificationEventType.")
        if not isinstance(self.actor_type, ActorType):
            raise TypeError("actor_type must be an ActorType.")
        for name in ("command_id", "idempotency_key"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} cannot be empty.")
        object.__setattr__(
            self,
            "payload_fingerprint",
            tuple(str(item) for item in self.payload_fingerprint),
        )
        if self.object_reference is not None and not self.object_reference.strip():
            raise ValueError("object_reference cannot be blank when supplied.")


@dataclass(frozen=True, slots=True)
class GuardFailure:
    """One deterministic guard failure."""

    guard: Guard
    reason_code: str
    safe_message: str

    def __post_init__(self) -> None:
        if not isinstance(self.guard, Guard):
            raise TypeError("guard must be a Guard.")
        if not self.reason_code.strip():
            raise ValueError("reason_code cannot be empty.")
        if not self.safe_message.strip():
            raise ValueError("safe_message cannot be empty.")


@dataclass(frozen=True, slots=True)
class SideEffectIntent:
    """Side-effect description emitted by the pure engine."""

    intent_type: SideEffectIntentType
    description: str

    def __post_init__(self) -> None:
        if not isinstance(self.intent_type, SideEffectIntentType):
            raise TypeError("intent_type must be a SideEffectIntentType.")
        if not self.description.strip():
            raise ValueError("description cannot be empty.")


@dataclass(frozen=True, slots=True)
class EvidenceIntent:
    """Serializable evidence description; not a durable publication."""

    transition_id: str
    event_type: QualificationEventType
    source_state: QualificationState
    destination_state: QualificationState
    qualification_run_id: QualificationRunId
    qualification_scenario_id: QualificationScenarioId
    correlation_id: CorrelationId
    command_id: CommandId
    idempotency_key: IdempotencyKey
    result: QualificationResult
    reason_code: str
    actor_type: ActorType
    environment: str
    safe_message: str
    schema_version: str = "paper-qualification-transition/v1"
    object_reference: str | None = None
    diagnostic: bool = False
    previous_revision: StateRevision | None = None
    next_revision: StateRevision | None = None
    replayed: bool = False
    reconciliation_required: bool = False

    def __post_init__(self) -> None:
        for name in (
            "transition_id",
            "qualification_run_id",
            "qualification_scenario_id",
            "correlation_id",
            "command_id",
            "idempotency_key",
            "reason_code",
            "environment",
            "safe_message",
            "schema_version",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} cannot be empty.")
        if self.object_reference is not None and not self.object_reference.strip():
            raise ValueError("object_reference cannot be blank when supplied.")
        if self.previous_revision is not None and self.previous_revision < 0:
            raise ValueError("previous_revision cannot be negative.")
        if self.next_revision is not None and self.next_revision < 0:
            raise ValueError("next_revision cannot be negative.")


@dataclass(frozen=True, slots=True)
class TransitionDecision:
    """Deterministic transition result."""

    accepted: bool
    transition_id: str
    previous_state: QualificationState
    next_state: QualificationState
    previous_revision: StateRevision
    next_revision: StateRevision
    result: QualificationResult
    reason_code: str
    safe_message: str
    retry_classification: RetryClassification
    side_effects: tuple[SideEffectIntent, ...] = ()
    evidence_intents: tuple[EvidenceIntent, ...] = ()
    guard_failures: tuple[GuardFailure, ...] = ()
    replayed: bool = False
    reconciliation_required: bool = False

    def __post_init__(self) -> None:
        if not self.transition_id.strip():
            raise ValueError("transition_id cannot be empty.")
        if not isinstance(self.previous_state, QualificationState):
            raise TypeError("previous_state must be a QualificationState.")
        if not isinstance(self.next_state, QualificationState):
            raise TypeError("next_state must be a QualificationState.")
        if self.previous_revision < 0 or self.next_revision < 0:
            raise ValueError("revisions must be non-negative.")
        if not isinstance(self.result, QualificationResult):
            raise TypeError("result must be a QualificationResult.")
        if not isinstance(self.retry_classification, RetryClassification):
            raise TypeError("retry_classification must be a RetryClassification.")
        object.__setattr__(self, "side_effects", tuple(self.side_effects))
        object.__setattr__(self, "evidence_intents", tuple(self.evidence_intents))
        object.__setattr__(self, "guard_failures", tuple(self.guard_failures))


@dataclass(frozen=True, slots=True)
class PriorCommandRecord:
    """Caller-supplied idempotency record for pure replay decisions."""

    idempotency_key: IdempotencyKey
    payload_fingerprint: tuple[str, ...]
    decision: TransitionDecision

    def __post_init__(self) -> None:
        if (
            not isinstance(self.idempotency_key, str)
            or not self.idempotency_key.strip()
        ):
            raise ValueError("idempotency_key cannot be empty.")
        object.__setattr__(
            self,
            "payload_fingerprint",
            tuple(str(item) for item in self.payload_fingerprint),
        )
        if not isinstance(self.decision, TransitionDecision):
            raise TypeError("decision must be a TransitionDecision.")


@dataclass(frozen=True, slots=True)
class TransitionContext:
    """Deterministic guard and replay facts supplied to transition evaluation."""

    expected_revision: StateRevision
    satisfied_guards: frozenset[Guard] = frozenset()
    environment: str = "PAPER"
    prior_command: PriorCommandRecord | None = None
    recovered_state: QualificationState | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.expected_revision, int) or self.expected_revision < 0:
            raise ValueError("expected_revision must be a non-negative integer.")
        object.__setattr__(
            self,
            "satisfied_guards",
            frozenset(self.satisfied_guards),
        )
        if not self.environment.strip():
            raise ValueError("environment cannot be empty.")
        if self.prior_command is not None and not isinstance(
            self.prior_command,
            PriorCommandRecord,
        ):
            raise TypeError("prior_command must be a PriorCommandRecord.")
        if self.recovered_state is not None and not isinstance(
            self.recovered_state,
            QualificationState,
        ):
            raise TypeError("recovered_state must be a QualificationState.")


@dataclass(frozen=True, slots=True)
class TransitionSpec:
    """One accepted transition registry row."""

    transition_id: str
    source_state: QualificationState | None
    event_type: QualificationEventType
    destination_state: QualificationState | None
    required_guards: frozenset[Guard]
    side_effects: tuple[SideEffectIntentType, ...]
    evidence_event: str
    retry_classification: RetryClassification
    result: QualificationResult
    safe_message: str
    reason_code: str
    allow_any_non_terminal: bool = False
    allow_any_active_recovery: bool = False

    def __post_init__(self) -> None:
        if not self.transition_id.strip():
            raise ValueError("transition_id cannot be empty.")
        object.__setattr__(self, "required_guards", frozenset(self.required_guards))
        object.__setattr__(self, "side_effects", tuple(self.side_effects))
        if not self.evidence_event.strip():
            raise ValueError("evidence_event cannot be empty.")
        if not self.reason_code.strip():
            raise ValueError("reason_code cannot be empty.")
        if not self.safe_message.strip():
            raise ValueError("safe_message cannot be empty.")
