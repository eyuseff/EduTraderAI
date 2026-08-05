"""Accepted ADR-006 transition table."""

from __future__ import annotations

from volcanoes.application.execution.lifecycle.contracts import (
    PaperExecutionTransitionSpecification,
)
from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionLifecycleEvidenceIntentKind as Evidence,
)
from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionLifecycleGuard as Guard,
)
from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionLifecycleInputType as Input,
)
from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionLifecycleSideEffectIntentKind as Effect,
)
from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionLifecycleState as State,
)


def spec(
    transition_id: str,
    sources: tuple[State, ...],
    input_type: Input,
    destination: State,
    guards: tuple[Guard, ...] = (),
    effect: Effect = Effect.NONE,
    evidence: Evidence = Evidence.LIFECYCLE_TRANSITION_ACCEPTED,
    *,
    reconciliation_required: bool = False,
) -> PaperExecutionTransitionSpecification:
    """Build one immutable transition specification."""

    return PaperExecutionTransitionSpecification(
        transition_id=transition_id,
        sources=sources,
        input_type=input_type,
        destination=destination,
        guards=guards,
        side_effect_intent_kind=effect,
        evidence_intent_kind=evidence,
        reconciliation_required=reconciliation_required,
        command_terminal=destination
        in {
            State.INELIGIBLE,
            State.ABORTED_BEFORE_DISPATCH,
            State.BROKER_REJECTED,
            State.REPLACED,
            State.FAILED_TERMINAL,
        },
        aggregate_terminal=destination in {State.FILLED, State.FAILED_TERMINAL},
    )


TRANSITION_SPECS: tuple[PaperExecutionTransitionSpecification, ...] = (
    spec("PX-TRN-001", (State.CREATED,), Input.CREATE_AGGREGATE, State.CREATED),
    spec(
        "PX-TRN-002",
        (State.CREATED,),
        Input.RECORD_ELIGIBILITY,
        State.ELIGIBILITY_EVALUATED,
        (Guard.ELIGIBILITY_RECORDED,),
    ),
    spec(
        "PX-TRN-003",
        (State.ELIGIBILITY_EVALUATED,),
        Input.RECORD_INELIGIBLE,
        State.INELIGIBLE,
        (Guard.ELIGIBILITY_RECORDED,),
        evidence=Evidence.LIFECYCLE_TERMINAL_STATE_REACHED,
    ),
    spec(
        "PX-TRN-004",
        (State.ELIGIBILITY_EVALUATED,),
        Input.RECORD_INDETERMINATE,
        State.INELIGIBLE,
        (Guard.ELIGIBILITY_RECORDED,),
        evidence=Evidence.LIFECYCLE_TERMINAL_STATE_REACHED,
    ),
    spec(
        "PX-TRN-005",
        (State.ELIGIBILITY_EVALUATED,),
        Input.RECORD_APPROVAL,
        State.APPROVAL_CONFIRMED,
        (Guard.ELIGIBILITY_COMPATIBLE, Guard.APPROVAL_VALID),
    ),
    spec(
        "PX-TRN-006",
        (State.APPROVAL_CONFIRMED,),
        Input.RECORD_IDEMPOTENCY_RESERVATION,
        State.IDEMPOTENCY_RESERVED,
        (Guard.IDEMPOTENCY_CONFIRMED,),
        Effect.WOULD_RESERVE_IDEMPOTENCY,
    ),
    spec(
        "PX-TRN-007",
        (State.IDEMPOTENCY_RESERVED,),
        Input.PREPARE_DISPATCH,
        State.READY_FOR_DISPATCH,
        (Guard.EMERGENCY_STOP_CLEAR,),
        Effect.WOULD_PREPARE_DISPATCH,
    ),
    spec(
        "PX-TRN-008",
        (State.READY_FOR_DISPATCH,),
        Input.RECORD_DISPATCH_PENDING,
        State.DISPATCH_PENDING,
        effect=Effect.WOULD_DISPATCH,
    ),
    spec(
        "PX-TRN-009",
        (State.DISPATCH_PENDING,),
        Input.RECORD_DISPATCH,
        State.DISPATCHED,
        effect=Effect.WOULD_DISPATCH,
    ),
    spec(
        "PX-TRN-010",
        (State.DISPATCHED,),
        Input.OBSERVE_BROKER_ACKNOWLEDGEMENT,
        State.BROKER_ACKNOWLEDGED,
        (Guard.BROKER_REFERENCE_PRESENT, Guard.BROKER_OBSERVATION_IDENTITY_PRESENT),
    ),
    spec(
        "PX-TRN-011",
        (State.DISPATCHED,),
        Input.OBSERVE_BROKER_REJECTION,
        State.BROKER_REJECTED,
        (Guard.BROKER_OBSERVATION_IDENTITY_PRESENT,),
        evidence=Evidence.LIFECYCLE_TERMINAL_STATE_REACHED,
    ),
    spec(
        "PX-TRN-012",
        (State.DISPATCHED,),
        Input.MARK_OUTCOME_UNKNOWN,
        State.OUTCOME_UNKNOWN,
        evidence=Evidence.LIFECYCLE_OUTCOME_UNKNOWN,
        reconciliation_required=True,
    ),
    spec(
        "PX-TRN-013",
        (State.BROKER_ACKNOWLEDGED,),
        Input.OBSERVE_PARTIAL_FILL,
        State.PARTIALLY_FILLED,
        (Guard.FILL_MONOTONIC,),
    ),
    spec(
        "PX-TRN-014",
        (State.BROKER_ACKNOWLEDGED,),
        Input.OBSERVE_FILL,
        State.FILLED,
        (Guard.FILL_MONOTONIC,),
        evidence=Evidence.LIFECYCLE_TERMINAL_STATE_REACHED,
    ),
    spec(
        "PX-TRN-015",
        (State.PARTIALLY_FILLED,),
        Input.OBSERVE_PARTIAL_FILL,
        State.PARTIALLY_FILLED,
        (Guard.FILL_MONOTONIC,),
    ),
    spec(
        "PX-TRN-016",
        (State.PARTIALLY_FILLED,),
        Input.OBSERVE_FILL,
        State.FILLED,
        (Guard.FILL_MONOTONIC,),
        evidence=Evidence.LIFECYCLE_TERMINAL_STATE_REACHED,
    ),
    spec(
        "PX-TRN-017",
        (State.BROKER_ACKNOWLEDGED, State.PARTIALLY_FILLED),
        Input.REQUEST_CANCELLATION,
        State.CANCEL_REQUESTED,
        (Guard.CANCELLATION_VALID,),
    ),
    spec(
        "PX-TRN-018",
        (State.CANCEL_REQUESTED,),
        Input.RECORD_CANCELLATION_PENDING,
        State.CANCEL_PENDING,
        effect=Effect.WOULD_REQUEST_CANCEL,
    ),
    spec(
        "PX-TRN-019",
        (State.CANCEL_PENDING,),
        Input.OBSERVE_CANCELLATION_CONFIRMATION,
        State.CANCELLED,
        (Guard.BROKER_REFERENCE_PRESENT, Guard.BROKER_OBSERVATION_IDENTITY_PRESENT),
        evidence=Evidence.LIFECYCLE_TERMINAL_STATE_REACHED,
    ),
    spec(
        "PX-TRN-020",
        (State.CANCEL_PENDING,),
        Input.OBSERVE_FILL,
        State.FILLED,
        (Guard.FILL_MONOTONIC,),
        evidence=Evidence.LIFECYCLE_TERMINAL_STATE_REACHED,
    ),
    spec(
        "PX-TRN-021",
        (State.BROKER_ACKNOWLEDGED, State.PARTIALLY_FILLED),
        Input.REQUEST_REPLACEMENT,
        State.REPLACE_REQUESTED,
        (Guard.REPLACEMENT_VALID,),
    ),
    spec(
        "PX-TRN-022",
        (State.REPLACE_REQUESTED,),
        Input.RECORD_REPLACEMENT_PENDING,
        State.REPLACE_PENDING,
        effect=Effect.WOULD_REQUEST_REPLACE,
    ),
    spec(
        "PX-TRN-023",
        (State.REPLACE_PENDING,),
        Input.OBSERVE_REPLACEMENT_CONFIRMATION,
        State.REPLACED,
        (Guard.BROKER_REFERENCE_PRESENT, Guard.BROKER_OBSERVATION_IDENTITY_PRESENT),
        evidence=Evidence.LIFECYCLE_TERMINAL_STATE_REACHED,
    ),
    spec(
        "PX-TRN-024",
        (State.REPLACE_PENDING,),
        Input.OBSERVE_FILL,
        State.FILLED,
        (Guard.FILL_MONOTONIC,),
        evidence=Evidence.LIFECYCLE_TERMINAL_STATE_REACHED,
    ),
    spec(
        "PX-TRN-025",
        (State.OUTCOME_UNKNOWN,),
        Input.REQUIRE_RECONCILIATION,
        State.RECONCILIATION_REQUIRED,
        effect=Effect.WOULD_RECONCILE,
        evidence=Evidence.LIFECYCLE_RECONCILIATION_REQUIRED,
        reconciliation_required=True,
    ),
    spec(
        "PX-TRN-026",
        (State.RECONCILIATION_REQUIRED,),
        Input.RECORD_RECONCILIATION_RESULT,
        State.BROKER_ACKNOWLEDGED,
        (Guard.RECONCILIATION_DESTINATION_BOUNDED,),
    ),
    spec(
        "PX-TRN-027",
        (State.RECONCILIATION_REQUIRED,),
        Input.RECORD_RECONCILIATION_RESULT,
        State.PARTIALLY_FILLED,
        (Guard.RECONCILIATION_DESTINATION_BOUNDED,),
    ),
    spec(
        "PX-TRN-028",
        (State.RECONCILIATION_REQUIRED,),
        Input.RECORD_RECONCILIATION_RESULT,
        State.RECONCILIATION_REQUIRED,
        (Guard.RECONCILIATION_DESTINATION_BOUNDED,),
        evidence=Evidence.LIFECYCLE_RECONCILIATION_REQUIRED,
        reconciliation_required=True,
    ),
    spec(
        "PX-TRN-029",
        (
            State.CREATED,
            State.ELIGIBILITY_EVALUATED,
            State.APPROVAL_CONFIRMED,
            State.IDEMPOTENCY_RESERVED,
            State.READY_FOR_DISPATCH,
        ),
        Input.ABORT_BEFORE_DISPATCH,
        State.ABORTED_BEFORE_DISPATCH,
        evidence=Evidence.LIFECYCLE_TERMINAL_STATE_REACHED,
    ),
    spec(
        "PX-TRN-030",
        tuple(state for state in State if state not in {State.FAILED_TERMINAL}),
        Input.FAIL_TERMINALLY,
        State.FAILED_TERMINAL,
        evidence=Evidence.LIFECYCLE_TERMINAL_STATE_REACHED,
    ),
)

TRANSITION_IDS = tuple(item.transition_id for item in TRANSITION_SPECS)
TRANSITION_BY_ID = {item.transition_id: item for item in TRANSITION_SPECS}


def matching_specs(
    state: State,
    input_type: Input,
) -> tuple[PaperExecutionTransitionSpecification, ...]:
    """Return accepted specs matching a state/input pair."""

    return tuple(
        item
        for item in TRANSITION_SPECS
        if input_type is item.input_type and state in item.sources
    )
