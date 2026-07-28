"""Pure Paper qualification state-transition engine."""

from __future__ import annotations

from dataclasses import replace

from volcanoes.application.qualification.contracts import (
    EvidenceIntent,
    Guard,
    GuardFailure,
    PaperQualificationRun,
    QualificationEvent,
    QualificationEventType,
    QualificationResult,
    QualificationState,
    RetryClassification,
    SideEffectIntent,
    SideEffectIntentType,
    StateCategory,
    StateRevision,
    STATE_CATEGORIES,
    TERMINAL_WORKFLOW_STATES,
    TransitionContext,
    TransitionDecision,
    TransitionSpec,
)
from volcanoes.application.qualification.errors import (
    GuardConditionError,
    IdempotencyConflictError,
    InvalidTransitionError,
    QualificationTerminalError,
    StaleRevisionError,
)

_DEFAULT_ENVIRONMENT = "PAPER"


def state_category(state: QualificationState) -> StateCategory:
    """Return the accepted category for one qualification state."""

    for candidate, category in STATE_CATEGORIES:
        if candidate is state:
            return category
    raise ValueError(f"Unknown qualification state {state!r}.")


def is_terminal_workflow_state(state: QualificationState) -> bool:
    """Return whether state is a terminal qualification workflow state."""

    return state in TERMINAL_WORKFLOW_STATES


def all_transition_specs() -> tuple[TransitionSpec, ...]:
    """Return the immutable accepted transition registry."""

    return _TRANSITION_SPECS


def transition(
    current_run: PaperQualificationRun,
    event: QualificationEvent,
    context: TransitionContext,
) -> TransitionDecision:
    """Evaluate exactly one accepted ADR-004 transition without side effects."""

    if current_run.state_revision != context.expected_revision:
        raise StaleRevisionError(
            reason_code="STALE_REVISION",
            safe_message="State changed before this command; refresh required.",
        )

    replay = _idempotent_replay(current_run, event, context)
    if replay is not None:
        return replay

    if is_terminal_workflow_state(current_run.state):
        raise QualificationTerminalError(
            reason_code="TERMINAL_STATE",
            safe_message="This qualification run is terminal; start a new run.",
        )

    spec = _find_transition(current_run.state, event, context)
    if spec is None:
        raise InvalidTransitionError(
            reason_code="INVALID_TRANSITION",
            safe_message="This transition is not allowed from the current state.",
        )

    missing_guards = tuple(
        guard for guard in spec.required_guards if guard not in context.satisfied_guards
    )
    if missing_guards:
        failures = tuple(_guard_failure(guard) for guard in missing_guards)
        raise GuardConditionError(
            reason_code=failures[0].reason_code,
            safe_message=failures[0].safe_message,
            transition_id=spec.transition_id,
        )

    destination = _destination_state(spec, current_run, context)
    result = _result(spec, current_run)
    next_revision = StateRevision(current_run.state_revision + 1)
    side_effects = tuple(
        SideEffectIntent(
            intent_type=intent,
            description=_side_effect_description(intent),
        )
        for intent in spec.side_effects
        if intent is not SideEffectIntentType.NONE
    )
    evidence = _evidence_intent(
        spec=spec,
        current_run=current_run,
        event=event,
        destination=destination,
        result=result,
        environment=context.environment,
        diagnostic=False,
    )
    return TransitionDecision(
        accepted=True,
        transition_id=spec.transition_id,
        previous_state=current_run.state,
        next_state=destination,
        previous_revision=current_run.state_revision,
        next_revision=next_revision,
        result=result,
        reason_code=spec.reason_code,
        safe_message=spec.safe_message,
        retry_classification=spec.retry_classification,
        side_effects=side_effects,
        evidence_intents=(evidence,),
        replayed=False,
        reconciliation_required=destination
        is QualificationState.RECONCILIATION_REQUIRED,
    )


def apply_transition(
    current_run: PaperQualificationRun,
    decision: TransitionDecision,
) -> PaperQualificationRun:
    """Return the immutable run snapshot produced by an accepted decision."""

    if not decision.accepted:
        return current_run
    return current_run.with_transition(
        state=decision.next_state,
        result=decision.result,
        state_revision=decision.next_revision,
    )


def diagnostic_rejection(
    current_run: PaperQualificationRun,
    event: QualificationEvent,
    context: TransitionContext,
    *,
    reason_code: str,
    safe_message: str,
) -> TransitionDecision:
    """Build a rejected decision with diagnostic evidence and no side effects."""

    evidence = EvidenceIntent(
        transition_id="INVALID",
        event_type=event.event_type,
        source_state=current_run.state,
        destination_state=current_run.state,
        qualification_run_id=current_run.qualification_run_id,
        qualification_scenario_id=current_run.qualification_scenario_id,
        correlation_id=current_run.correlation_id,
        command_id=event.command_id,
        idempotency_key=event.idempotency_key,
        result=current_run.result,
        reason_code=reason_code,
        actor_type=event.actor_type,
        environment=context.environment,
        safe_message=safe_message,
        object_reference=event.object_reference,
        diagnostic=True,
    )
    return TransitionDecision(
        accepted=False,
        transition_id="INVALID",
        previous_state=current_run.state,
        next_state=current_run.state,
        previous_revision=current_run.state_revision,
        next_revision=current_run.state_revision,
        result=current_run.result,
        reason_code=reason_code,
        safe_message=safe_message,
        retry_classification=RetryClassification.SAFE_LOCAL_RETRY,
        evidence_intents=(evidence,),
    )


def _idempotent_replay(
    current_run: PaperQualificationRun,
    event: QualificationEvent,
    context: TransitionContext,
) -> TransitionDecision | None:
    record = context.prior_command
    if record is None or record.idempotency_key != event.idempotency_key:
        return None
    if record.payload_fingerprint != event.payload_fingerprint:
        raise IdempotencyConflictError(
            reason_code="IDEMPOTENCY_CONFLICT",
            safe_message="The idempotency key was already used for different input.",
            transition_id=record.decision.transition_id,
        )
    return replace(
        record.decision,
        previous_state=current_run.state,
        next_state=current_run.state,
        previous_revision=current_run.state_revision,
        next_revision=current_run.state_revision,
        side_effects=(),
        replayed=True,
        reconciliation_required=current_run.state
        is QualificationState.RECONCILIATION_REQUIRED,
    )


def _find_transition(
    state: QualificationState,
    event: QualificationEvent,
    context: TransitionContext,
) -> TransitionSpec | None:
    candidates = tuple(
        spec
        for spec in _TRANSITION_SPECS
        if spec.event_type is event.event_type and _source_matches(spec, state, context)
    )
    matches = tuple(
        spec
        for spec in candidates
        if spec.required_guards.issubset(context.satisfied_guards)
    )
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise InvalidTransitionError(
            reason_code="AMBIGUOUS_TRANSITION",
            safe_message="Transition registry matched more than one accepted row.",
        )
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise GuardConditionError(
            reason_code="GUARD_DISAMBIGUATION_FAILED",
            safe_message="Transition guards did not identify one accepted transition.",
        )
    return None


def _source_matches(
    spec: TransitionSpec,
    state: QualificationState,
    context: TransitionContext,
) -> bool:
    if spec.allow_any_non_terminal:
        if state in TERMINAL_WORKFLOW_STATES:
            return False
        if spec.transition_id == "PQ-TRN-033":
            return state not in {
                QualificationState.UNRESOLVED,
                QualificationState.RECONCILIATION_REQUIRED,
            }
        return True
    if spec.allow_any_active_recovery:
        return state not in TERMINAL_WORKFLOW_STATES
    return spec.source_state is state


def _destination_state(
    spec: TransitionSpec,
    current_run: PaperQualificationRun,
    context: TransitionContext,
) -> QualificationState:
    if spec.transition_id == "PQ-TRN-035":
        return context.recovered_state or current_run.state
    if spec.destination_state is None:
        raise InvalidTransitionError(
            reason_code="MISSING_DESTINATION",
            safe_message="Transition destination is not defined.",
            transition_id=spec.transition_id,
        )
    return spec.destination_state


def _result(
    spec: TransitionSpec,
    current_run: PaperQualificationRun,
) -> QualificationResult:
    if spec.transition_id == "PQ-TRN-035":
        return current_run.result
    return spec.result


def _guard_failure(guard: Guard) -> GuardFailure:
    return GuardFailure(
        guard=guard,
        reason_code=f"GUARD_{guard.value}",
        safe_message=_GUARD_MESSAGES.get(
            guard,
            "A required qualification guard did not pass.",
        ),
    )


def _evidence_intent(
    *,
    spec: TransitionSpec,
    current_run: PaperQualificationRun,
    event: QualificationEvent,
    destination: QualificationState,
    result: QualificationResult,
    environment: str,
    diagnostic: bool,
) -> EvidenceIntent:
    return EvidenceIntent(
        transition_id=spec.transition_id,
        event_type=event.event_type,
        source_state=current_run.state,
        destination_state=destination,
        qualification_run_id=current_run.qualification_run_id,
        qualification_scenario_id=current_run.qualification_scenario_id,
        correlation_id=current_run.correlation_id,
        command_id=event.command_id,
        idempotency_key=event.idempotency_key,
        result=result,
        reason_code=spec.reason_code,
        actor_type=event.actor_type,
        environment=environment or _DEFAULT_ENVIRONMENT,
        safe_message=spec.safe_message,
        object_reference=event.object_reference,
        diagnostic=diagnostic,
    )


def _side_effect_description(intent: SideEffectIntentType) -> str:
    return _SIDE_EFFECT_DESCRIPTIONS[intent]


def _spec(
    transition_id: str,
    source: QualificationState | None,
    event: QualificationEventType,
    destination: QualificationState | None,
    guards: tuple[Guard, ...],
    side_effects: tuple[SideEffectIntentType, ...],
    evidence_event: str,
    retry: RetryClassification,
    result: QualificationResult,
    message: str,
    *,
    any_non_terminal: bool = False,
    any_active_recovery: bool = False,
) -> TransitionSpec:
    return TransitionSpec(
        transition_id=transition_id,
        source_state=source,
        event_type=event,
        destination_state=destination,
        required_guards=frozenset(guards),
        side_effects=side_effects,
        evidence_event=evidence_event,
        retry_classification=retry,
        result=result,
        safe_message=message,
        reason_code=transition_id.replace("-", "_"),
        allow_any_non_terminal=any_non_terminal,
        allow_any_active_recovery=any_active_recovery,
    )


_MSG_PRECHECKS_RUNNING = (
    "Qualification prechecks are running. No broker request has been sent."
)
_MSG_READY = "Qualification is ready for operator approval."
_MSG_PRECHECK_FAILED = (
    "Qualification prechecks did not pass. No broker request was sent."
)
_MSG_APPROVAL_REQUIRED = "Operator approval is required before any broker request."
_MSG_APPROVED = "Operator approval was recorded. No broker request has been sent yet."
_MSG_OPERATOR_REJECTED = (
    "The operator rejected the qualification request. No broker request was sent."
)
_MSG_PREPARING = "A broker request is being prepared."
_MSG_SENT = "The request was sent. Broker acknowledgment is pending."
_MSG_ACK = "The broker acknowledged the order. The order has not necessarily filled."
_MSG_PARTIAL = "The broker reported a partial fill."
_MSG_FILLED = "The broker reported the full fill."
_MSG_CANCEL_REQ = "Cancellation was requested but has not yet been confirmed."
_MSG_CANCELLED = "The broker confirmed cancellation."
_MSG_BROKER_REJECTED = "The broker rejected the request."
_MSG_EXPIRED = "The broker reported that the order expired."
_MSG_UNRESOLVED = "The final broker state cannot currently be confirmed."
_MSG_RECONCILE = "Broker reconciliation is required before qualification can continue."
_MSG_DISQUALIFIED = "The qualification run did not meet the approved criteria."
_MSG_QUALIFIED = (
    "The approved Paper qualification criteria were completed successfully."
)
_MSG_ABORTED = "Qualification was aborted. No further action will occur in this run."
_MSG_RECOVERED = "Qualification state was recovered from evidence."

_TRANSITION_SPECS = (
    _spec(
        "PQ-TRN-001",
        QualificationState.NOT_STARTED,
        QualificationEventType.START_QUALIFICATION,
        QualificationState.PRECHECK_PENDING,
        (Guard.SCENARIO_AUTHORIZED, Guard.PAPER_ENVIRONMENT),
        (),
        "QualificationStarted",
        RetryClassification.SAFE_LOCAL_RETRY,
        QualificationResult.PENDING,
        _MSG_PRECHECKS_RUNNING,
    ),
    _spec(
        "PQ-TRN-002",
        QualificationState.PRECHECK_PENDING,
        QualificationEventType.PRECHECKS_PASSED,
        QualificationState.READY_FOR_APPROVAL,
        (
            Guard.PAPER_ENVIRONMENT,
            Guard.BROKER_SUPPORTED,
            Guard.CONFIGURATION_VALID,
            Guard.CREDENTIALS_AVAILABLE,
            Guard.EVIDENCE_AVAILABLE,
        ),
        (),
        "PrechecksPassed",
        RetryClassification.SAFE_LOCAL_RETRY,
        QualificationResult.PENDING,
        _MSG_READY,
    ),
    _spec(
        "PQ-TRN-003",
        QualificationState.PRECHECK_PENDING,
        QualificationEventType.PRECHECKS_FAILED,
        QualificationState.PRECHECK_FAILED,
        (Guard.EVIDENCE_AVAILABLE,),
        (SideEffectIntentType.BLOCK_CONSEQUENTIAL_ACTION,),
        "PrechecksFailed",
        RetryClassification.RETRY_AFTER_CORRECTION,
        QualificationResult.INCONCLUSIVE,
        _MSG_PRECHECK_FAILED,
    ),
    _spec(
        "PQ-TRN-004",
        QualificationState.PRECHECK_FAILED,
        QualificationEventType.START_QUALIFICATION,
        QualificationState.PRECHECK_PENDING,
        (Guard.SCENARIO_AUTHORIZED, Guard.PAPER_ENVIRONMENT),
        (),
        "PrecheckRetryStarted",
        RetryClassification.SAFE_LOCAL_RETRY,
        QualificationResult.PENDING,
        _MSG_PRECHECKS_RUNNING,
    ),
    _spec(
        "PQ-TRN-005",
        QualificationState.READY_FOR_APPROVAL,
        QualificationEventType.APPROVAL_REQUESTED,
        QualificationState.APPROVAL_PENDING,
        (Guard.APPROVAL_SURFACE_AVAILABLE, Guard.EMERGENCY_STOP_INACTIVE),
        (SideEffectIntentType.REQUEST_OPERATOR_APPROVAL,),
        "ApprovalRequested",
        RetryClassification.SAFE_LOCAL_RETRY,
        QualificationResult.PENDING,
        _MSG_APPROVAL_REQUIRED,
    ),
    _spec(
        "PQ-TRN-006",
        QualificationState.APPROVAL_PENDING,
        QualificationEventType.OPERATOR_APPROVED,
        QualificationState.APPROVED,
        (Guard.OPERATOR_APPROVAL_VALID, Guard.PLAN_CURRENT, Guard.EVIDENCE_AVAILABLE),
        (SideEffectIntentType.RECORD_OPERATOR_APPROVAL,),
        "OperatorApproved",
        RetryClassification.SAFE_LOCAL_RETRY,
        QualificationResult.PENDING,
        _MSG_APPROVED,
    ),
    _spec(
        "PQ-TRN-007",
        QualificationState.APPROVAL_PENDING,
        QualificationEventType.OPERATOR_REJECTED,
        QualificationState.REJECTED,
        (Guard.OPERATOR_REJECTION_CAPTURED,),
        (SideEffectIntentType.BLOCK_CONSEQUENTIAL_ACTION,),
        "OperatorRejected",
        RetryClassification.NON_RETRYABLE_SAME_RUN,
        QualificationResult.FAILED,
        _MSG_OPERATOR_REJECTED,
    ),
    _spec(
        "PQ-TRN-008",
        QualificationState.READY_FOR_APPROVAL,
        QualificationEventType.OPERATOR_REJECTED,
        QualificationState.REJECTED,
        (Guard.OPERATOR_REJECTION_CAPTURED,),
        (SideEffectIntentType.BLOCK_CONSEQUENTIAL_ACTION,),
        "OperatorRejected",
        RetryClassification.NON_RETRYABLE_SAME_RUN,
        QualificationResult.FAILED,
        _MSG_OPERATOR_REJECTED,
    ),
    _spec(
        "PQ-TRN-009",
        QualificationState.APPROVED,
        QualificationEventType.SUBMISSION_STARTED,
        QualificationState.SUBMISSION_PENDING,
        (
            Guard.APPROVAL_NOT_EXPIRED,
            Guard.NO_DUPLICATE_KEY,
            Guard.EMERGENCY_STOP_INACTIVE,
        ),
        (SideEffectIntentType.PREPARE_BROKER_SUBMISSION,),
        "SubmissionStarted",
        RetryClassification.SAFE_LOCAL_RETRY,
        QualificationResult.PENDING,
        _MSG_PREPARING,
    ),
    _spec(
        "PQ-TRN-010",
        QualificationState.SUBMISSION_PENDING,
        QualificationEventType.BROKER_REQUEST_SENT,
        QualificationState.SUBMITTED,
        (
            Guard.BROKER_CAPABILITY_AVAILABLE,
            Guard.NO_DUPLICATE_KEY,
            Guard.PAPER_ENVIRONMENT,
        ),
        (SideEffectIntentType.SEND_BROKER_REQUEST,),
        "BrokerRequestSent",
        RetryClassification.UNSAFE_EXTERNAL_RETRY,
        QualificationResult.PENDING,
        _MSG_SENT,
    ),
    _spec(
        "PQ-TRN-011",
        QualificationState.SUBMITTED,
        QualificationEventType.BROKER_ACKNOWLEDGED,
        QualificationState.ACKNOWLEDGED,
        (Guard.BROKER_RESPONSE_MATCHES,),
        (SideEffectIntentType.RECORD_BROKER_REFERENCE,),
        "BrokerAcknowledged",
        RetryClassification.SAFE_EVENT_REPLAY,
        QualificationResult.PENDING,
        _MSG_ACK,
    ),
    _spec(
        "PQ-TRN-012",
        QualificationState.ACKNOWLEDGED,
        QualificationEventType.BROKER_PARTIAL_FILL_REPORTED,
        QualificationState.PARTIALLY_FILLED,
        (Guard.PARTIAL_FILL_VALID,),
        (SideEffectIntentType.RECORD_BROKER_LIFECYCLE,),
        "BrokerPartialFillReported",
        RetryClassification.SAFE_EVENT_REPLAY,
        QualificationResult.PENDING,
        _MSG_PARTIAL,
    ),
    _spec(
        "PQ-TRN-013",
        QualificationState.ACKNOWLEDGED,
        QualificationEventType.BROKER_FILL_REPORTED,
        QualificationState.FILLED,
        (Guard.FULL_FILL_EVIDENCE,),
        (SideEffectIntentType.RECORD_BROKER_LIFECYCLE,),
        "BrokerFillReported",
        RetryClassification.SAFE_EVENT_REPLAY,
        QualificationResult.PENDING,
        _MSG_FILLED,
    ),
    _spec(
        "PQ-TRN-014",
        QualificationState.PARTIALLY_FILLED,
        QualificationEventType.BROKER_FILL_REPORTED,
        QualificationState.FILLED,
        (Guard.FULL_FILL_EVIDENCE,),
        (SideEffectIntentType.RECORD_BROKER_LIFECYCLE,),
        "BrokerFillReported",
        RetryClassification.SAFE_EVENT_REPLAY,
        QualificationResult.PENDING,
        _MSG_FILLED,
    ),
    _spec(
        "PQ-TRN-015",
        QualificationState.ACKNOWLEDGED,
        QualificationEventType.CANCELLATION_REQUESTED,
        QualificationState.CANCELLATION_REQUESTED,
        (
            Guard.CANCELLATION_SUPPORTED,
            Guard.NO_TERMINAL_BROKER_STATE,
            Guard.EMERGENCY_STOP_INACTIVE,
        ),
        (SideEffectIntentType.REQUEST_BROKER_CANCELLATION,),
        "CancellationRequested",
        RetryClassification.IDEMPOTENT_EXTERNAL_RETRY_ONLY,
        QualificationResult.PENDING,
        _MSG_CANCEL_REQ,
    ),
    _spec(
        "PQ-TRN-016",
        QualificationState.PARTIALLY_FILLED,
        QualificationEventType.CANCELLATION_REQUESTED,
        QualificationState.CANCELLATION_REQUESTED,
        (Guard.CANCELLATION_SUPPORTED, Guard.EMERGENCY_STOP_INACTIVE),
        (SideEffectIntentType.REQUEST_BROKER_CANCELLATION,),
        "CancellationRequested",
        RetryClassification.IDEMPOTENT_EXTERNAL_RETRY_ONLY,
        QualificationResult.PENDING,
        _MSG_CANCEL_REQ,
    ),
    _spec(
        "PQ-TRN-017",
        QualificationState.CANCELLATION_REQUESTED,
        QualificationEventType.BROKER_CANCELLATION_CONFIRMED,
        QualificationState.CANCELLED,
        (Guard.CANCELLATION_CONFIRMATION_MATCHES,),
        (SideEffectIntentType.RECORD_BROKER_LIFECYCLE,),
        "BrokerCancellationConfirmed",
        RetryClassification.SAFE_EVENT_REPLAY,
        QualificationResult.PENDING,
        _MSG_CANCELLED,
    ),
    _spec(
        "PQ-TRN-018",
        QualificationState.SUBMITTED,
        QualificationEventType.BROKER_REJECTED,
        QualificationState.REJECTED,
        (Guard.BROKER_REJECTION_MATCHES,),
        (SideEffectIntentType.RECORD_BROKER_LIFECYCLE,),
        "BrokerRejected",
        RetryClassification.SAFE_EVENT_REPLAY,
        QualificationResult.PENDING,
        _MSG_BROKER_REJECTED,
    ),
    _spec(
        "PQ-TRN-019",
        QualificationState.ACKNOWLEDGED,
        QualificationEventType.BROKER_REJECTED,
        QualificationState.REJECTED,
        (Guard.BROKER_REJECTION_MATCHES,),
        (SideEffectIntentType.RECORD_BROKER_LIFECYCLE,),
        "BrokerRejected",
        RetryClassification.SAFE_EVENT_REPLAY,
        QualificationResult.PENDING,
        _MSG_BROKER_REJECTED,
    ),
    _spec(
        "PQ-TRN-020",
        QualificationState.SUBMITTED,
        QualificationEventType.BROKER_EXPIRED,
        QualificationState.EXPIRED,
        (Guard.BROKER_EXPIRATION_MATCHES,),
        (SideEffectIntentType.RECORD_BROKER_LIFECYCLE,),
        "BrokerExpired",
        RetryClassification.SAFE_EVENT_REPLAY,
        QualificationResult.PENDING,
        _MSG_EXPIRED,
    ),
    _spec(
        "PQ-TRN-021",
        QualificationState.ACKNOWLEDGED,
        QualificationEventType.BROKER_EXPIRED,
        QualificationState.EXPIRED,
        (Guard.BROKER_EXPIRATION_MATCHES,),
        (SideEffectIntentType.RECORD_BROKER_LIFECYCLE,),
        "BrokerExpired",
        RetryClassification.SAFE_EVENT_REPLAY,
        QualificationResult.PENDING,
        _MSG_EXPIRED,
    ),
    _spec(
        "PQ-TRN-022",
        QualificationState.SUBMITTED,
        QualificationEventType.TIMEOUT_DETECTED,
        QualificationState.UNRESOLVED,
        (Guard.BROKER_OUTCOME_UNKNOWN,),
        (SideEffectIntentType.BLOCK_CONSEQUENTIAL_ACTION,),
        "SubmissionTimeoutUnresolved",
        RetryClassification.SAFE_READ_RETRY,
        QualificationResult.INCONCLUSIVE,
        _MSG_UNRESOLVED,
    ),
    _spec(
        "PQ-TRN-023",
        QualificationState.SUBMISSION_PENDING,
        QualificationEventType.TIMEOUT_DETECTED,
        QualificationState.UNRESOLVED,
        (Guard.BROKER_SEND_UNCERTAIN,),
        (SideEffectIntentType.BLOCK_CONSEQUENTIAL_ACTION,),
        "SubmissionPreparationTimeout",
        RetryClassification.RECONCILE_BEFORE_RETRY,
        QualificationResult.INCONCLUSIVE,
        _MSG_UNRESOLVED,
    ),
    _spec(
        "PQ-TRN-024",
        QualificationState.UNRESOLVED,
        QualificationEventType.RECONCILIATION_STARTED,
        QualificationState.RECONCILIATION_REQUIRED,
        (Guard.READ_ONLY_RECONCILIATION_AVAILABLE,),
        (SideEffectIntentType.START_RECONCILIATION,),
        "ReconciliationStarted",
        RetryClassification.SAFE_READ_RETRY,
        QualificationResult.INCONCLUSIVE,
        _MSG_RECONCILE,
    ),
    _spec(
        "PQ-TRN-025",
        QualificationState.RECONCILIATION_REQUIRED,
        QualificationEventType.RECONCILIATION_RESOLVED,
        QualificationState.ACKNOWLEDGED,
        (Guard.BROKER_TRUTH_FOUND, Guard.EVIDENCE_AVAILABLE),
        (SideEffectIntentType.RECORD_BROKER_REFERENCE,),
        "ReconciliationResolvedAcknowledged",
        RetryClassification.SAFE_EVENT_REPLAY,
        QualificationResult.PENDING,
        _MSG_ACK,
    ),
    _spec(
        "PQ-TRN-026",
        QualificationState.RECONCILIATION_REQUIRED,
        QualificationEventType.RECONCILIATION_RESOLVED,
        QualificationState.CANCELLED,
        (Guard.BROKER_PROVES_CANCELLATION, Guard.EVIDENCE_AVAILABLE),
        (SideEffectIntentType.RECORD_BROKER_LIFECYCLE,),
        "ReconciliationResolvedCancelled",
        RetryClassification.SAFE_EVENT_REPLAY,
        QualificationResult.PENDING,
        _MSG_CANCELLED,
    ),
    _spec(
        "PQ-TRN-027",
        QualificationState.RECONCILIATION_REQUIRED,
        QualificationEventType.RECONCILIATION_RESOLVED,
        QualificationState.REJECTED,
        (Guard.BROKER_PROVES_REJECTION_OR_NO_ORDER, Guard.EVIDENCE_AVAILABLE),
        (SideEffectIntentType.RECORD_BROKER_LIFECYCLE,),
        "ReconciliationResolvedRejected",
        RetryClassification.SAFE_EVENT_REPLAY,
        QualificationResult.PENDING,
        "The request was rejected or no broker order was found.",
    ),
    _spec(
        "PQ-TRN-028",
        QualificationState.RECONCILIATION_REQUIRED,
        QualificationEventType.QUALIFICATION_CRITERIA_FAILED,
        QualificationState.DISQUALIFIED,
        (Guard.RECONCILIATION_FAILED_OR_EVIDENCE_INCOMPLETE,),
        (SideEffectIntentType.FINALIZE_QUALIFICATION,),
        "QualificationDisqualified",
        RetryClassification.NON_RETRYABLE_SAME_RUN,
        QualificationResult.FAILED,
        _MSG_DISQUALIFIED,
    ),
    _spec(
        "PQ-TRN-029",
        QualificationState.ACKNOWLEDGED,
        QualificationEventType.QUALIFICATION_CRITERIA_MET,
        QualificationState.QUALIFIED,
        (Guard.SCENARIO_REQUIRES_ACK_ONLY, Guard.CRITERIA_EVIDENCE_COMPLETE),
        (SideEffectIntentType.FINALIZE_QUALIFICATION,),
        "QualificationPassed",
        RetryClassification.NON_RETRYABLE_SAME_RUN,
        QualificationResult.PASSED,
        _MSG_QUALIFIED,
    ),
    _spec(
        "PQ-TRN-030",
        QualificationState.CANCELLED,
        QualificationEventType.QUALIFICATION_CRITERIA_MET,
        QualificationState.QUALIFIED,
        (
            Guard.SCENARIO_REQUIRES_CANCELLATION_CLEANUP,
            Guard.CRITERIA_EVIDENCE_COMPLETE,
        ),
        (SideEffectIntentType.FINALIZE_QUALIFICATION,),
        "QualificationPassed",
        RetryClassification.NON_RETRYABLE_SAME_RUN,
        QualificationResult.PASSED,
        _MSG_QUALIFIED,
    ),
    _spec(
        "PQ-TRN-031",
        QualificationState.FILLED,
        QualificationEventType.QUALIFICATION_CRITERIA_MET,
        QualificationState.QUALIFIED,
        (Guard.SCENARIO_REQUIRES_FILL, Guard.CRITERIA_EVIDENCE_COMPLETE),
        (SideEffectIntentType.FINALIZE_QUALIFICATION,),
        "QualificationPassed",
        RetryClassification.NON_RETRYABLE_SAME_RUN,
        QualificationResult.PASSED,
        _MSG_QUALIFIED,
    ),
    _spec(
        "PQ-TRN-032",
        QualificationState.REJECTED,
        QualificationEventType.QUALIFICATION_CRITERIA_MET,
        QualificationState.QUALIFIED,
        (Guard.SCENARIO_REQUIRES_REJECTION, Guard.CRITERIA_EVIDENCE_COMPLETE),
        (SideEffectIntentType.FINALIZE_QUALIFICATION,),
        "QualificationPassed",
        RetryClassification.NON_RETRYABLE_SAME_RUN,
        QualificationResult.PASSED,
        _MSG_QUALIFIED,
    ),
    _spec(
        "PQ-TRN-033",
        None,
        QualificationEventType.QUALIFICATION_CRITERIA_FAILED,
        QualificationState.DISQUALIFIED,
        (Guard.CRITERIA_FAILED,),
        (SideEffectIntentType.FINALIZE_QUALIFICATION,),
        "QualificationDisqualified",
        RetryClassification.NON_RETRYABLE_SAME_RUN,
        QualificationResult.FAILED,
        _MSG_DISQUALIFIED,
        any_non_terminal=True,
    ),
    _spec(
        "PQ-TRN-034",
        None,
        QualificationEventType.ABORT_REQUESTED,
        QualificationState.ABORTED,
        (Guard.ACTOR_AUTHORIZED_TO_ABORT, Guard.NO_UNSAFE_BROKER_EFFECT_IN_PROGRESS),
        (SideEffectIntentType.BLOCK_CONSEQUENTIAL_ACTION,),
        "QualificationAborted",
        RetryClassification.NON_RETRYABLE_SAME_RUN,
        QualificationResult.ABORTED,
        _MSG_ABORTED,
        any_non_terminal=True,
    ),
    _spec(
        "PQ-TRN-035",
        None,
        QualificationEventType.PROCESS_RESTARTED,
        None,
        (Guard.DURABLE_STATE_AND_EVIDENCE_VERIFIED,),
        (SideEffectIntentType.RESUME_OR_REQUIRE_RECONCILIATION,),
        "QualificationRecovered",
        RetryClassification.SAFE_RECOVERY_READ_RETRY,
        QualificationResult.PENDING,
        _MSG_RECOVERED,
        any_active_recovery=True,
    ),
)

_GUARD_MESSAGES = {
    Guard.PAPER_ENVIRONMENT: "Paper environment is required before this transition.",
    Guard.EMERGENCY_STOP_INACTIVE: "Emergency stop is active; consequential action is blocked.",
    Guard.EVIDENCE_AVAILABLE: "Evidence is unavailable; qualification cannot continue safely.",
    Guard.NO_DUPLICATE_KEY: "A duplicate command key blocks this transition.",
    Guard.BROKER_OUTCOME_UNKNOWN: "Broker outcome is unknown; reconciliation is required before retry.",
    Guard.BROKER_SEND_UNCERTAIN: "Broker send status is uncertain; reconciliation is required before retry.",
    Guard.CRITERIA_EVIDENCE_COMPLETE: "Qualification evidence is incomplete.",
}

_SIDE_EFFECT_DESCRIPTIONS = {
    SideEffectIntentType.NONE: "No side effect.",
    SideEffectIntentType.REQUEST_OPERATOR_APPROVAL: "Request explicit operator approval.",
    SideEffectIntentType.RECORD_OPERATOR_APPROVAL: "Record scoped operator approval.",
    SideEffectIntentType.PREPARE_BROKER_SUBMISSION: "Prepare a broker submission command.",
    SideEffectIntentType.SEND_BROKER_REQUEST: "Send one broker request through an outer adapter.",
    SideEffectIntentType.RECORD_BROKER_REFERENCE: "Record broker reference or acknowledgment metadata.",
    SideEffectIntentType.RECORD_BROKER_LIFECYCLE: "Record broker lifecycle observation.",
    SideEffectIntentType.REQUEST_BROKER_CANCELLATION: "Request broker cancellation through an outer adapter.",
    SideEffectIntentType.START_RECONCILIATION: "Start read-only broker reconciliation.",
    SideEffectIntentType.FINALIZE_QUALIFICATION: "Finalize qualification result.",
    SideEffectIntentType.BLOCK_CONSEQUENTIAL_ACTION: "Block consequential action for this run.",
    SideEffectIntentType.RESUME_OR_REQUIRE_RECONCILIATION: "Resume state or require reconciliation after restart.",
}
