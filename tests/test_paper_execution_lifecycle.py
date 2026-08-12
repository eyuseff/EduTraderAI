"""Focused tests for the pure Paper execution lifecycle core."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
from typing import Any

import pytest

from volcanoes.application.execution.fingerprints import (
    command_payload_fingerprint,
    failure_fingerprint,
    receipt_fingerprint,
)
from volcanoes.application.execution.identities import (
    PaperBrokerOrderReference,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionIdempotencyKey,
    PaperExecutionRevision,
)
from volcanoes.application.execution.lifecycle import (
    BROKER_ORDER_TERMINAL_STATES,
    COMMAND_TERMINAL_STATES,
    RESTRICTED_NON_TERMINAL_STATES,
    TRANSITION_BY_ID,
    TRANSITION_IDS,
    TRANSITION_SPECS,
    PaperExecutionLifecycle,
    PaperExecutionLifecycleEvidenceIntentKind as Evidence,
    PaperExecutionLifecycleInput,
    PaperExecutionLifecycleInputCategory,
    PaperExecutionLifecycleInputType as Input,
    PaperExecutionLifecycleSideEffectIntentKind as Effect,
    PaperExecutionLifecycleState as State,
    PaperExecutionReconciliationOutcome as ReconciliationOutcome,
    PaperExecutionReplayKind as ReplayKind,
    PaperExecutionTransitionContext,
    PaperExecutionTransitionDecisionType as DecisionType,
    apply_transition,
    input_category,
    is_aggregate_terminal,
    is_broker_order_terminal,
    is_command_terminal,
    matching_specs,
    next_revision_after_acceptance,
    transition,
)

ACCEPTED_STATES = (
    "CREATED",
    "ELIGIBILITY_EVALUATED",
    "INELIGIBLE",
    "APPROVAL_CONFIRMED",
    "IDEMPOTENCY_RESERVED",
    "READY_FOR_DISPATCH",
    "DISPATCH_PENDING",
    "DISPATCHED",
    "BROKER_ACKNOWLEDGED",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCEL_REQUESTED",
    "CANCEL_PENDING",
    "CANCELLED",
    "REPLACE_REQUESTED",
    "REPLACE_PENDING",
    "REPLACED",
    "BROKER_REJECTED",
    "OUTCOME_UNKNOWN",
    "RECONCILIATION_REQUIRED",
    "FAILED_TERMINAL",
    "ABORTED_BEFORE_DISPATCH",
)

REJECTED_STATE_NAMES = (
    "ELIGIBLE",
    "RECOVERED",
    "DRY_RUN_ACCEPTED",
    "DRY_RUN_REJECTED",
    "WORKING",
    "LIVE",
)

TRANSITION_EXPECTATIONS = (
    ("PX-TRN-001", State.CREATED, Input.CREATE_AGGREGATE, State.CREATED),
    (
        "PX-TRN-002",
        State.CREATED,
        Input.RECORD_ELIGIBILITY,
        State.ELIGIBILITY_EVALUATED,
    ),
    (
        "PX-TRN-003",
        State.ELIGIBILITY_EVALUATED,
        Input.RECORD_INELIGIBLE,
        State.INELIGIBLE,
    ),
    (
        "PX-TRN-004",
        State.ELIGIBILITY_EVALUATED,
        Input.RECORD_INDETERMINATE,
        State.INELIGIBLE,
    ),
    (
        "PX-TRN-005",
        State.ELIGIBILITY_EVALUATED,
        Input.RECORD_APPROVAL,
        State.APPROVAL_CONFIRMED,
    ),
    (
        "PX-TRN-006",
        State.APPROVAL_CONFIRMED,
        Input.RECORD_IDEMPOTENCY_RESERVATION,
        State.IDEMPOTENCY_RESERVED,
    ),
    (
        "PX-TRN-007",
        State.IDEMPOTENCY_RESERVED,
        Input.PREPARE_DISPATCH,
        State.READY_FOR_DISPATCH,
    ),
    (
        "PX-TRN-008",
        State.READY_FOR_DISPATCH,
        Input.RECORD_DISPATCH_PENDING,
        State.DISPATCH_PENDING,
    ),
    ("PX-TRN-009", State.DISPATCH_PENDING, Input.RECORD_DISPATCH, State.DISPATCHED),
    (
        "PX-TRN-010",
        State.DISPATCHED,
        Input.OBSERVE_BROKER_ACKNOWLEDGEMENT,
        State.BROKER_ACKNOWLEDGED,
    ),
    (
        "PX-TRN-011",
        State.DISPATCHED,
        Input.OBSERVE_BROKER_REJECTION,
        State.BROKER_REJECTED,
    ),
    ("PX-TRN-012", State.DISPATCHED, Input.MARK_OUTCOME_UNKNOWN, State.OUTCOME_UNKNOWN),
    (
        "PX-TRN-013",
        State.BROKER_ACKNOWLEDGED,
        Input.OBSERVE_PARTIAL_FILL,
        State.PARTIALLY_FILLED,
    ),
    ("PX-TRN-014", State.BROKER_ACKNOWLEDGED, Input.OBSERVE_FILL, State.FILLED),
    (
        "PX-TRN-015",
        State.PARTIALLY_FILLED,
        Input.OBSERVE_PARTIAL_FILL,
        State.PARTIALLY_FILLED,
    ),
    ("PX-TRN-016", State.PARTIALLY_FILLED, Input.OBSERVE_FILL, State.FILLED),
    (
        "PX-TRN-017",
        State.BROKER_ACKNOWLEDGED,
        Input.REQUEST_CANCELLATION,
        State.CANCEL_REQUESTED,
    ),
    (
        "PX-TRN-018",
        State.CANCEL_REQUESTED,
        Input.RECORD_CANCELLATION_PENDING,
        State.CANCEL_PENDING,
    ),
    (
        "PX-TRN-019",
        State.CANCEL_PENDING,
        Input.OBSERVE_CANCELLATION_CONFIRMATION,
        State.CANCELLED,
    ),
    ("PX-TRN-020", State.CANCEL_PENDING, Input.OBSERVE_FILL, State.FILLED),
    (
        "PX-TRN-021",
        State.BROKER_ACKNOWLEDGED,
        Input.REQUEST_REPLACEMENT,
        State.REPLACE_REQUESTED,
    ),
    (
        "PX-TRN-022",
        State.REPLACE_REQUESTED,
        Input.RECORD_REPLACEMENT_PENDING,
        State.REPLACE_PENDING,
    ),
    (
        "PX-TRN-023",
        State.REPLACE_PENDING,
        Input.OBSERVE_REPLACEMENT_CONFIRMATION,
        State.REPLACED,
    ),
    ("PX-TRN-024", State.REPLACE_PENDING, Input.OBSERVE_FILL, State.FILLED),
    (
        "PX-TRN-025",
        State.OUTCOME_UNKNOWN,
        Input.REQUIRE_RECONCILIATION,
        State.RECONCILIATION_REQUIRED,
    ),
    (
        "PX-TRN-026",
        State.RECONCILIATION_REQUIRED,
        Input.RECORD_RECONCILIATION_RESULT,
        State.BROKER_ACKNOWLEDGED,
    ),
    (
        "PX-TRN-027",
        State.RECONCILIATION_REQUIRED,
        Input.RECORD_RECONCILIATION_RESULT,
        State.PARTIALLY_FILLED,
    ),
    (
        "PX-TRN-028",
        State.RECONCILIATION_REQUIRED,
        Input.RECORD_RECONCILIATION_RESULT,
        State.RECONCILIATION_REQUIRED,
    ),
    (
        "PX-TRN-029",
        State.READY_FOR_DISPATCH,
        Input.ABORT_BEFORE_DISPATCH,
        State.ABORTED_BEFORE_DISPATCH,
    ),
    ("PX-TRN-030", State.CANCEL_PENDING, Input.FAIL_TERMINALLY, State.FAILED_TERMINAL),
)


def aggregate(
    *,
    state: State = State.CREATED,
    revision: int = 0,
    quantity: Decimal = Decimal("10"),
    filled: Decimal = Decimal("0"),
) -> PaperExecutionLifecycle:
    return PaperExecutionLifecycle(
        aggregate_id=PaperExecutionAggregateId.from_seed("aggregate"),
        state=state,
        revision=PaperExecutionRevision(revision),
        correlation_id=PaperExecutionCorrelationId.from_seed("correlation"),
        broker_order_reference=PaperBrokerOrderReference.from_seed("broker-order"),
        requested_quantity=quantity,
        cumulative_filled_quantity=filled,
    )


def event(
    input_type: Input,
    *,
    seed: str = "event",
) -> PaperExecutionLifecycleInput:
    return PaperExecutionLifecycleInput(
        input_type=input_type,
        command_id=PaperExecutionCommandId.from_seed(seed, input_type.value),
        aggregate_id=PaperExecutionAggregateId.from_seed("aggregate"),
        correlation_id=PaperExecutionCorrelationId.from_seed("correlation"),
        idempotency_key=PaperExecutionIdempotencyKey.from_seed(seed, "idempotency"),
        command_payload_fingerprint=command_payload_fingerprint(
            (seed, input_type.value)
        ),
        idempotency_payload_fingerprint=command_payload_fingerprint(
            (seed, "idempotency", input_type.value)
        ),
        broker_observation_id=f"broker-observation-{seed}",
        broker_observation_fingerprint=command_payload_fingerprint(
            (seed, "observation", input_type.value)
        ),
        receipt_fingerprint=receipt_fingerprint((seed, input_type.value)),
        failure_fingerprint=failure_fingerprint((seed, input_type.value)),
    )


def context(
    current: PaperExecutionLifecycle,
    **overrides: object,
) -> PaperExecutionTransitionContext:
    values: dict[str, Any] = {
        "expected_revision": current.revision,
        "eligibility_decision": "ELIGIBLE",
        "approval_binding_valid": True,
        "approval_time_valid": True,
        "policy_compatible": True,
        "idempotency_reservation_confirmed": True,
        "emergency_stop_clearance": True,
        "external_prerequisites_satisfied": True,
        "broker_reference": PaperBrokerOrderReference.from_seed("broker-order"),
        "observed_cumulative_fill_quantity": Decimal("5"),
        "requested_quantity": current.requested_quantity or Decimal("10"),
        "replacement_quantity": Decimal("10"),
    }
    values.update(overrides)
    return PaperExecutionTransitionContext(**values)


def accepted_decision(
    *,
    state: State,
    input_type: Input,
    **context_overrides: object,
):
    current = aggregate(state=state)
    decision = transition(
        current, event(input_type), context(current, **context_overrides)
    )
    assert decision.accepted is True
    return current, decision


def test_state_inventory_is_exactly_the_accepted_adr_006_set() -> None:
    assert tuple(item.value for item in State) == ACCEPTED_STATES


@pytest.mark.parametrize("state_name", REJECTED_STATE_NAMES)
def test_rejected_state_names_are_not_present(state_name: str) -> None:
    assert state_name not in State.__members__


def test_transition_table_has_exactly_thirty_specs() -> None:
    assert len(TRANSITION_SPECS) == 30
    assert TRANSITION_IDS == tuple(f"PX-TRN-{number:03d}" for number in range(1, 31))


@pytest.mark.parametrize(
    ("transition_id", "source", "input_type", "destination"),
    TRANSITION_EXPECTATIONS,
)
def test_transition_specification_matches_expected_table(
    transition_id: str,
    source: State,
    input_type: Input,
    destination: State,
) -> None:
    spec = TRANSITION_BY_ID[transition_id]

    assert source in spec.sources
    assert spec.input_type is input_type
    assert spec.destination is destination
    assert spec.transition_id == transition_id
    assert matching_specs(source, input_type)


@pytest.mark.parametrize(
    ("transition_id", "source", "input_type", "destination"),
    TRANSITION_EXPECTATIONS,
)
def test_each_transition_accepts_when_required_guard_facts_are_present(
    transition_id: str,
    source: State,
    input_type: Input,
    destination: State,
) -> None:
    current = aggregate(
        state=source,
        filled=Decimal("2") if source is State.PARTIALLY_FILLED else Decimal("0"),
    )
    overrides: dict[str, object] = {}
    if transition_id == "PX-TRN-003":
        overrides["eligibility_decision"] = "INELIGIBLE"
    if transition_id == "PX-TRN-004":
        overrides["eligibility_decision"] = "INDETERMINATE"
    if transition_id in {"PX-TRN-014", "PX-TRN-016", "PX-TRN-020", "PX-TRN-024"}:
        overrides["observed_cumulative_fill_quantity"] = Decimal("10")
    if transition_id == "PX-TRN-026":
        overrides["reconciliation_outcome"] = ReconciliationOutcome.CONSISTENT
        overrides["reconciliation_destination"] = State.BROKER_ACKNOWLEDGED
    if transition_id == "PX-TRN-027":
        overrides["reconciliation_outcome"] = ReconciliationOutcome.BROKER_AHEAD
        overrides["reconciliation_destination"] = State.PARTIALLY_FILLED
    if transition_id == "PX-TRN-028":
        overrides["reconciliation_outcome"] = ReconciliationOutcome.CONFLICTING
        overrides["reconciliation_destination"] = State.RECONCILIATION_REQUIRED

    decision = transition(current, event(input_type), context(current, **overrides))

    assert decision.accepted is True
    assert decision.decision_type is DecisionType.ACCEPTED
    assert decision.transition_id == transition_id
    assert decision.next_state is destination
    assert decision.previous_revision == current.revision
    assert decision.next_revision == current.revision.next()
    assert decision.revision_incremented is True


def test_accepted_transitions_emit_only_descriptive_intents() -> None:
    assert all(
        isinstance(spec.side_effect_intent_kind, Effect) for spec in TRANSITION_SPECS
    )
    assert all(
        isinstance(spec.evidence_intent_kind, Evidence) for spec in TRANSITION_SPECS
    )


def test_input_category_is_total_for_every_lifecycle_input() -> None:
    assert all(
        isinstance(input_category(input_type), PaperExecutionLifecycleInputCategory)
        for input_type in Input
    )


@pytest.mark.parametrize(
    "input_type",
    (
        Input.OBSERVE_BROKER_ACKNOWLEDGEMENT,
        Input.OBSERVE_BROKER_REJECTION,
        Input.OBSERVE_PARTIAL_FILL,
        Input.OBSERVE_FILL,
        Input.OBSERVE_CANCELLATION_CONFIRMATION,
        Input.OBSERVE_REPLACEMENT_CONFIRMATION,
    ),
)
def test_broker_observations_are_categorized(input_type: Input) -> None:
    assert (
        input_category(input_type)
        is PaperExecutionLifecycleInputCategory.BROKER_OBSERVATION
    )


@pytest.mark.parametrize(
    "input_type",
    (Input.REQUIRE_RECONCILIATION, Input.RECORD_RECONCILIATION_RESULT),
)
def test_reconciliation_inputs_are_categorized(input_type: Input) -> None:
    assert (
        input_category(input_type)
        is PaperExecutionLifecycleInputCategory.RECONCILIATION
    )


@pytest.mark.parametrize("state", COMMAND_TERMINAL_STATES)
def test_command_terminal_state_helper_matches_table(state: State) -> None:
    assert is_command_terminal(state) is True


@pytest.mark.parametrize("state", BROKER_ORDER_TERMINAL_STATES)
def test_broker_terminal_state_helper_matches_table(state: State) -> None:
    assert is_broker_order_terminal(state) is True


@pytest.mark.parametrize("state", (State.FILLED, State.FAILED_TERMINAL))
def test_aggregate_terminal_state_helper_matches_table(state: State) -> None:
    assert is_aggregate_terminal(state) is True


@pytest.mark.parametrize("state", RESTRICTED_NON_TERMINAL_STATES)
def test_restricted_states_are_not_terminal(state: State) -> None:
    assert is_command_terminal(state) is False
    assert is_broker_order_terminal(state) is False
    assert is_aggregate_terminal(state) is False


def test_lifecycle_aggregate_is_immutable() -> None:
    current = aggregate()

    with pytest.raises(FrozenInstanceError):
        current.state = State.FILLED  # type: ignore[misc]


def test_lifecycle_input_is_immutable() -> None:
    lifecycle_input = event(Input.RECORD_ELIGIBILITY)

    with pytest.raises(FrozenInstanceError):
        lifecycle_input.input_type = Input.FAIL_TERMINALLY  # type: ignore[misc]


def test_transition_context_is_immutable() -> None:
    current = aggregate()
    facts = context(current)

    with pytest.raises(FrozenInstanceError):
        facts.policy_compatible = False  # type: ignore[misc]


def test_transition_decision_is_immutable() -> None:
    _, decision = accepted_decision(
        state=State.CREATED, input_type=Input.RECORD_ELIGIBILITY
    )

    with pytest.raises(FrozenInstanceError):
        decision.reason_code = "changed"  # type: ignore[misc]


def test_expected_revision_mismatch_rejects_without_increment() -> None:
    current = aggregate()
    facts = context(current, expected_revision=PaperExecutionRevision(99))
    decision = transition(current, event(Input.RECORD_ELIGIBILITY), facts)

    assert decision.accepted is False
    assert decision.reason_code == "STALE_EXECUTION_REVISION"
    assert decision.next_revision == current.revision
    assert apply_transition(current, decision) is current


def test_identity_mismatch_rejects_without_increment() -> None:
    current = aggregate()
    mismatched = PaperExecutionLifecycleInput(
        input_type=Input.RECORD_ELIGIBILITY,
        command_id=PaperExecutionCommandId.from_seed("mismatch"),
        aggregate_id=PaperExecutionAggregateId.from_seed("other"),
        correlation_id=current.correlation_id,
    )
    decision = transition(current, mismatched, context(current))

    assert decision.accepted is False
    assert decision.reason_code == "IDENTITY_MISMATCH"
    assert decision.next_revision == current.revision


@pytest.mark.parametrize(
    ("flag", "decision_type", "reason", "replay_kind"),
    (
        (
            "command_matches_prior",
            DecisionType.REPLAYED,
            "COMMAND_REPLAY",
            ReplayKind.COMMAND_REPLAY,
        ),
        (
            "idempotency_matches_prior",
            DecisionType.REPLAYED,
            "IDEMPOTENCY_REPLAY",
            ReplayKind.IDEMPOTENCY_REPLAY,
        ),
        (
            "broker_observation_matches_prior",
            DecisionType.REPLAYED,
            "BROKER_OBSERVATION_REPLAY",
            ReplayKind.BROKER_OBSERVATION_REPLAY,
        ),
    ),
)
def test_replays_do_not_increment_revision_or_emit_side_effects(
    flag: str,
    decision_type: DecisionType,
    reason: str,
    replay_kind: ReplayKind,
) -> None:
    current = aggregate(state=State.DISPATCHED)
    decision = transition(
        current,
        event(Input.OBSERVE_BROKER_ACKNOWLEDGEMENT),
        context(current, **{flag: True}),
    )

    assert decision.accepted is False
    assert decision.decision_type is decision_type
    assert decision.reason_code == reason
    assert decision.replay_kind is replay_kind
    assert decision.next_revision == current.revision
    assert decision.side_effect_intents[0].kind is Effect.NONE


@pytest.mark.parametrize(
    ("flag", "decision_type", "reason", "evidence"),
    (
        (
            "command_conflicts_with_prior",
            DecisionType.COMMAND_CONFLICT,
            "COMMAND_CONFLICT",
            Evidence.LIFECYCLE_COMMAND_CONFLICT,
        ),
        (
            "idempotency_conflicts_with_prior",
            DecisionType.IDEMPOTENCY_CONFLICT,
            "IDEMPOTENCY_CONFLICT",
            Evidence.LIFECYCLE_IDEMPOTENCY_CONFLICT,
        ),
        (
            "broker_observation_conflicts_with_prior",
            DecisionType.BROKER_OBSERVATION_CONFLICT,
            "BROKER_OBSERVATION_CONFLICT",
            Evidence.LIFECYCLE_BROKER_OBSERVATION_CONFLICT,
        ),
    ),
)
def test_conflicts_do_not_increment_revision_or_emit_side_effects(
    flag: str,
    decision_type: DecisionType,
    reason: str,
    evidence: Evidence,
) -> None:
    current = aggregate(state=State.DISPATCHED)
    decision = transition(
        current,
        event(Input.OBSERVE_BROKER_ACKNOWLEDGEMENT),
        context(current, **{flag: True}),
    )

    assert decision.accepted is False
    assert decision.decision_type is decision_type
    assert decision.reason_code == reason
    assert decision.evidence_intents[0].kind is evidence
    assert decision.next_revision == current.revision
    assert decision.side_effect_intents[0].kind is Effect.NONE


@pytest.mark.parametrize("input_type", tuple(Input))
def test_terminal_states_reject_non_failure_inputs(input_type: Input) -> None:
    current = aggregate(state=State.FILLED)
    decision = transition(current, event(input_type), context(current))

    if input_type is Input.FAIL_TERMINALLY:
        assert decision.accepted is True
    else:
        assert decision.accepted is False
        assert decision.reason_code == "TERMINAL_STATE"


@pytest.mark.parametrize(
    "input_type",
    tuple(
        item
        for item in Input
        if item not in {Input.REQUIRE_RECONCILIATION, Input.FAIL_TERMINALLY}
    ),
)
def test_outcome_unknown_rejects_everything_except_reconciliation_or_failure(
    input_type: Input,
) -> None:
    current = aggregate(state=State.OUTCOME_UNKNOWN)
    decision = transition(current, event(input_type), context(current))

    assert decision.accepted is False
    assert decision.reason_code == "OUTCOME_UNKNOWN_REQUIRES_RECONCILIATION"


@pytest.mark.parametrize(
    "input_type",
    tuple(
        item
        for item in Input
        if item not in {Input.RECORD_RECONCILIATION_RESULT, Input.FAIL_TERMINALLY}
    ),
)
def test_reconciliation_required_rejects_everything_except_result_or_failure(
    input_type: Input,
) -> None:
    current = aggregate(state=State.RECONCILIATION_REQUIRED)
    decision = transition(current, event(input_type), context(current))

    assert decision.accepted is False
    assert decision.reason_code == "RECONCILIATION_REQUIRED"


@pytest.mark.parametrize(
    ("input_type", "eligibility", "reason"),
    (
        (Input.RECORD_ELIGIBILITY, "INELIGIBLE", "ELIGIBILITY_DECISION_NOT_ELIGIBLE"),
        (Input.RECORD_INELIGIBLE, "ELIGIBLE", "ELIGIBILITY_DECISION_NOT_INELIGIBLE"),
        (
            Input.RECORD_INDETERMINATE,
            "ELIGIBLE",
            "ELIGIBILITY_DECISION_NOT_INDETERMINATE",
        ),
    ),
)
def test_eligibility_guard_failures_are_explainable(
    input_type: Input,
    eligibility: str,
    reason: str,
) -> None:
    current = aggregate(
        state=(
            State.CREATED
            if input_type is Input.RECORD_ELIGIBILITY
            else State.ELIGIBILITY_EVALUATED
        )
    )
    decision = transition(
        current,
        event(input_type),
        context(current, eligibility_decision=eligibility),
    )

    assert decision.accepted is False
    assert decision.reason_code == reason


@pytest.mark.parametrize(
    ("overrides", "reason"),
    (
        ({"approval_binding_valid": False}, "APPROVAL_INVALID"),
        ({"approval_time_valid": False}, "APPROVAL_INVALID"),
        ({"policy_compatible": False}, "APPROVAL_INVALID"),
        ({"eligibility_decision": "INELIGIBLE"}, "ELIGIBILITY_NOT_COMPATIBLE"),
    ),
)
def test_approval_guard_failures_are_explainable(
    overrides: dict[str, object],
    reason: str,
) -> None:
    current = aggregate(state=State.ELIGIBILITY_EVALUATED)
    decision = transition(
        current, event(Input.RECORD_APPROVAL), context(current, **overrides)
    )

    assert decision.accepted is False
    assert decision.reason_code == reason


def test_idempotency_reservation_requires_confirmation() -> None:
    current = aggregate(state=State.APPROVAL_CONFIRMED)
    decision = transition(
        current,
        event(Input.RECORD_IDEMPOTENCY_RESERVATION),
        context(current, idempotency_reservation_confirmed=False),
    )

    assert decision.accepted is False
    assert decision.reason_code == "IDEMPOTENCY_NOT_CONFIRMED"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    (
        ({"emergency_stop_clearance": False}, "EMERGENCY_STOP_ACTIVE"),
        (
            {"external_prerequisites_satisfied": False},
            "EXTERNAL_PREREQUISITES_NOT_SATISFIED",
        ),
    ),
)
def test_prepare_dispatch_requires_clearance_and_prerequisites(
    overrides: dict[str, object],
    reason: str,
) -> None:
    current = aggregate(state=State.IDEMPOTENCY_RESERVED)
    decision = transition(
        current, event(Input.PREPARE_DISPATCH), context(current, **overrides)
    )

    assert decision.accepted is False
    assert decision.reason_code == reason


@pytest.mark.parametrize(
    "input_type",
    (
        Input.OBSERVE_BROKER_ACKNOWLEDGEMENT,
        Input.OBSERVE_CANCELLATION_CONFIRMATION,
        Input.OBSERVE_REPLACEMENT_CONFIRMATION,
    ),
)
def test_broker_observation_requiring_reference_rejects_when_missing(
    input_type: Input,
) -> None:
    source = {
        Input.OBSERVE_BROKER_ACKNOWLEDGEMENT: State.DISPATCHED,
        Input.OBSERVE_CANCELLATION_CONFIRMATION: State.CANCEL_PENDING,
        Input.OBSERVE_REPLACEMENT_CONFIRMATION: State.REPLACE_PENDING,
    }[input_type]
    current = PaperExecutionLifecycle(
        aggregate_id=PaperExecutionAggregateId.from_seed("aggregate"),
        state=source,
        revision=PaperExecutionRevision.initial(),
        correlation_id=PaperExecutionCorrelationId.from_seed("correlation"),
        requested_quantity=Decimal("10"),
    )
    decision = transition(
        current, event(input_type), context(current, broker_reference=None)
    )

    assert decision.accepted is False
    assert decision.reason_code == "BROKER_REFERENCE_MISSING"


@pytest.mark.parametrize(
    "input_type",
    (
        Input.OBSERVE_BROKER_ACKNOWLEDGEMENT,
        Input.OBSERVE_BROKER_REJECTION,
        Input.OBSERVE_PARTIAL_FILL,
        Input.OBSERVE_FILL,
        Input.OBSERVE_CANCELLATION_CONFIRMATION,
        Input.OBSERVE_REPLACEMENT_CONFIRMATION,
    ),
)
def test_broker_observations_require_observation_identity(input_type: Input) -> None:
    source = {
        Input.OBSERVE_BROKER_ACKNOWLEDGEMENT: State.DISPATCHED,
        Input.OBSERVE_BROKER_REJECTION: State.DISPATCHED,
        Input.OBSERVE_PARTIAL_FILL: State.BROKER_ACKNOWLEDGED,
        Input.OBSERVE_FILL: State.BROKER_ACKNOWLEDGED,
        Input.OBSERVE_CANCELLATION_CONFIRMATION: State.CANCEL_PENDING,
        Input.OBSERVE_REPLACEMENT_CONFIRMATION: State.REPLACE_PENDING,
    }[input_type]
    current = aggregate(state=source)
    missing_identity = PaperExecutionLifecycleInput(
        input_type=input_type,
        command_id=PaperExecutionCommandId.from_seed("missing-identity"),
        aggregate_id=current.aggregate_id,
        correlation_id=current.correlation_id,
    )
    decision = transition(current, missing_identity, context(current))

    assert decision.accepted is False
    assert decision.reason_code == "BROKER_OBSERVATION_IDENTITY_MISSING"


@pytest.mark.parametrize(
    ("observed", "final_fill", "reason"),
    (
        (Decimal("1"), False, "FILL_NOT_MONOTONIC"),
        (Decimal("11"), False, "FILL_EXCEEDS_REQUESTED_QUANTITY"),
        (Decimal("10"), False, "PARTIAL_FILL_MUST_BE_LESS_THAN_REQUESTED_QUANTITY"),
        (Decimal("9"), True, "FINAL_FILL_MUST_EQUAL_REQUESTED_QUANTITY"),
    ),
)
def test_fill_monotonicity_and_finality_guards(
    observed: Decimal,
    final_fill: bool,
    reason: str,
) -> None:
    current = aggregate(state=State.PARTIALLY_FILLED, filled=Decimal("2"))
    decision = transition(
        current,
        event(Input.OBSERVE_FILL if final_fill else Input.OBSERVE_PARTIAL_FILL),
        context(current, observed_cumulative_fill_quantity=observed),
    )

    assert decision.accepted is False
    assert decision.reason_code == reason


def test_partial_fill_updates_cumulative_quantity_when_applied() -> None:
    current, decision = accepted_decision(
        state=State.BROKER_ACKNOWLEDGED,
        input_type=Input.OBSERVE_PARTIAL_FILL,
        observed_cumulative_fill_quantity=Decimal("5"),
    )
    updated = apply_transition(current, decision)

    assert updated.state is State.PARTIALLY_FILLED
    assert updated.cumulative_filled_quantity == Decimal("5")
    assert updated.revision == current.revision.next()


def test_final_fill_marks_broker_order_terminal() -> None:
    _, decision = accepted_decision(
        state=State.BROKER_ACKNOWLEDGED,
        input_type=Input.OBSERVE_FILL,
        observed_cumulative_fill_quantity=Decimal("10"),
    )

    assert decision.next_state is State.FILLED
    assert decision.broker_order_terminal is True
    assert decision.aggregate_terminal is True


def test_cancellation_rejects_when_nothing_remains() -> None:
    current = aggregate(state=State.PARTIALLY_FILLED, filled=Decimal("10"))
    decision = transition(current, event(Input.REQUEST_CANCELLATION), context(current))

    assert decision.accepted is False
    assert decision.reason_code == "NOTHING_LEFT_TO_CANCEL"


@pytest.mark.parametrize(
    ("replacement_quantity", "reason"),
    (
        (None, "REPLACEMENT_QUANTITY_MISSING"),
        (Decimal("1"), "REPLACEMENT_BELOW_FILLED_QUANTITY"),
    ),
)
def test_replacement_guard_failures(
    replacement_quantity: Decimal | None,
    reason: str,
) -> None:
    current = aggregate(state=State.PARTIALLY_FILLED, filled=Decimal("2"))
    decision = transition(
        current,
        event(Input.REQUEST_REPLACEMENT),
        context(current, replacement_quantity=replacement_quantity),
    )

    assert decision.accepted is False
    assert decision.reason_code == reason


def test_replacement_request_tracks_active_replacement_command_when_applied() -> None:
    current, decision = accepted_decision(
        state=State.BROKER_ACKNOWLEDGED,
        input_type=Input.REQUEST_REPLACEMENT,
        replacement_quantity=Decimal("10"),
    )
    updated = apply_transition(current, decision)

    assert updated.state is State.REPLACE_REQUESTED
    assert updated.active_replacement_command_id == decision.command_id


def test_unknown_outcome_marks_reconciliation_required() -> None:
    _, decision = accepted_decision(
        state=State.DISPATCHED, input_type=Input.MARK_OUTCOME_UNKNOWN
    )

    assert decision.next_state is State.OUTCOME_UNKNOWN
    assert decision.outcome_unknown is True
    assert decision.reconciliation_required is True
    assert decision.evidence_intents[0].kind is Evidence.LIFECYCLE_OUTCOME_UNKNOWN


def test_require_reconciliation_keeps_reconciliation_required() -> None:
    _, decision = accepted_decision(
        state=State.OUTCOME_UNKNOWN,
        input_type=Input.REQUIRE_RECONCILIATION,
    )

    assert decision.next_state is State.RECONCILIATION_REQUIRED
    assert decision.reconciliation_required is True
    assert decision.side_effect_intents[0].kind is Effect.WOULD_RECONCILE


@pytest.mark.parametrize(
    ("outcome", "destination", "transition_id", "expected_required"),
    (
        (
            ReconciliationOutcome.CONSISTENT,
            State.BROKER_ACKNOWLEDGED,
            "PX-TRN-026",
            False,
        ),
        (
            ReconciliationOutcome.BROKER_AHEAD,
            State.PARTIALLY_FILLED,
            "PX-TRN-027",
            False,
        ),
        (
            ReconciliationOutcome.CONFLICTING,
            State.RECONCILIATION_REQUIRED,
            "PX-TRN-028",
            True,
        ),
        (
            ReconciliationOutcome.UNRESOLVED,
            State.RECONCILIATION_REQUIRED,
            "PX-TRN-028",
            True,
        ),
    ),
)
def test_reconciliation_result_is_bounded_and_explainable(
    outcome: ReconciliationOutcome,
    destination: State,
    transition_id: str,
    expected_required: bool,
) -> None:
    current = aggregate(state=State.RECONCILIATION_REQUIRED)
    decision = transition(
        current,
        event(Input.RECORD_RECONCILIATION_RESULT),
        context(
            current,
            reconciliation_outcome=outcome,
            reconciliation_destination=destination,
        ),
    )

    assert decision.accepted is True
    assert decision.transition_id == transition_id
    assert decision.next_state is destination
    assert decision.reconciliation_required is expected_required


def test_reconciliation_rejects_unbounded_destination() -> None:
    current = aggregate(state=State.RECONCILIATION_REQUIRED)
    decision = transition(
        current,
        event(Input.RECORD_RECONCILIATION_RESULT),
        context(
            current,
            reconciliation_outcome=ReconciliationOutcome.CONSISTENT,
            reconciliation_destination=State.READY_FOR_DISPATCH,
        ),
    )

    assert decision.accepted is False
    assert decision.reason_code == "RECONCILIATION_DESTINATION_NOT_BOUNDED"


def test_reconciliation_requires_outcome() -> None:
    current = aggregate(state=State.RECONCILIATION_REQUIRED)
    decision = transition(
        current, event(Input.RECORD_RECONCILIATION_RESULT), context(current)
    )

    assert decision.accepted is False
    assert decision.reason_code == "RECONCILIATION_OUTCOME_MISSING"


def test_apply_transition_updates_replay_identities_without_mutating_original() -> None:
    current, decision = accepted_decision(
        state=State.CREATED, input_type=Input.RECORD_ELIGIBILITY
    )
    updated = apply_transition(current, decision)

    assert current.state is State.CREATED
    assert updated.state is State.ELIGIBILITY_EVALUATED
    assert updated.last_command_id == decision.command_id
    assert updated.last_idempotency_key == decision.idempotency_key
    assert updated.last_transition_id == "PX-TRN-002"


@pytest.mark.parametrize(
    ("source", "input_type"),
    (
        (State.CREATED, Input.RECORD_APPROVAL),
        (State.APPROVAL_CONFIRMED, Input.RECORD_DISPATCH),
        (State.DISPATCHED, Input.REQUEST_REPLACEMENT),
        (State.CANCEL_PENDING, Input.REQUEST_CANCELLATION),
    ),
)
def test_invalid_state_input_pairs_reject_without_increment(
    source: State,
    input_type: Input,
) -> None:
    current = aggregate(state=source)
    decision = transition(current, event(input_type), context(current))

    assert decision.accepted is False
    assert decision.reason_code == "INVALID_LIFECYCLE_TRANSITION"
    assert decision.next_revision == current.revision


def test_next_revision_helper_is_deterministic() -> None:
    assert next_revision_after_acceptance(
        PaperExecutionRevision(7)
    ) == PaperExecutionRevision(8)


def test_transition_decisions_contain_no_runtime_authority() -> None:
    _, decision = accepted_decision(
        state=State.IDEMPOTENCY_RESERVED,
        input_type=Input.PREPARE_DISPATCH,
    )

    assert decision.side_effect_intents[0].kind is Effect.WOULD_PREPARE_DISPATCH
    assert "EXECUTION_AUTHORIZED" not in repr(decision)
    assert "submit" not in repr(decision).lower()
