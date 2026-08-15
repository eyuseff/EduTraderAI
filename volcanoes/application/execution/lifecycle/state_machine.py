"""Pure transition engine for the Paper execution lifecycle core."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from volcanoes.application.execution.identities import PaperExecutionRevision
from volcanoes.application.execution.lifecycle.contracts import (
    PaperExecutionLifecycle,
    PaperExecutionLifecycleEvidenceIntent,
    PaperExecutionLifecycleInput,
    PaperExecutionLifecycleSideEffectIntent,
    PaperExecutionTransitionContext,
    PaperExecutionTransitionDecision,
    PaperExecutionTransitionSpecification,
    input_category,
    is_aggregate_terminal,
    is_broker_order_terminal,
    is_command_terminal,
)
from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionLifecycleEvidenceIntentKind as Evidence,
)
from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionLifecycleInputCategory,
    PaperExecutionLifecycleInputType as Input,
)
from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionLifecycleSideEffectIntentKind as Effect,
)
from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionLifecycleState as State,
)
from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionReconciliationOutcome as ReconciliationOutcome,
)
from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionReplayKind as ReplayKind,
)
from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionTransitionDecisionType as DecisionType,
)
from volcanoes.application.execution.lifecycle.transition_table import (
    TRANSITION_BY_ID,
    matching_specs,
)

BROKER_OBSERVATION_INPUTS = frozenset(
    item
    for item in Input
    if input_category(item) is PaperExecutionLifecycleInputCategory.BROKER_OBSERVATION
)

RECONCILIATION_RECOVERY_STATES = frozenset(
    {
        State.BROKER_ACKNOWLEDGED,
        State.PARTIALLY_FILLED,
        State.FILLED,
        State.CANCELLED,
        State.BROKER_REJECTED,
        State.FAILED_TERMINAL,
        State.RECONCILIATION_REQUIRED,
    }
)

TERMINAL_STATES = frozenset(
    {
        State.INELIGIBLE,
        State.ABORTED_BEFORE_DISPATCH,
        State.BROKER_REJECTED,
        State.REPLACED,
        State.FILLED,
        State.CANCELLED,
        State.FAILED_TERMINAL,
    }
)


def transition(
    current: PaperExecutionLifecycle,
    event: PaperExecutionLifecycleInput,
    context: PaperExecutionTransitionContext,
) -> PaperExecutionTransitionDecision:
    """Evaluate one lifecycle transition without executing side effects."""

    _validate_transition_arguments(current, event, context)
    if (
        current.aggregate_id != event.aggregate_id
        or current.correlation_id != event.correlation_id
    ):
        return _rejected(current, "IDENTITY_MISMATCH")
    if context.expected_revision != current.revision:
        return _rejected(current, "STALE_EXECUTION_REVISION")

    replay = _replay_or_conflict_decision(current, context)
    if replay is not None:
        return replay

    if not context.paper_mode_confirmed:
        return _rejected(current, "PAPER_MODE_NOT_CONFIRMED")
    if (
        current.state in TERMINAL_STATES
        and event.input_type is not Input.FAIL_TERMINALLY
    ):
        return _rejected(current, "TERMINAL_STATE")
    if current.state is State.OUTCOME_UNKNOWN and event.input_type not in {
        Input.REQUIRE_RECONCILIATION,
        Input.FAIL_TERMINALLY,
    }:
        return _rejected(current, "OUTCOME_UNKNOWN_REQUIRES_RECONCILIATION")
    if current.state is State.RECONCILIATION_REQUIRED and event.input_type not in {
        Input.RECORD_RECONCILIATION_RESULT,
        Input.FAIL_TERMINALLY,
    }:
        return _rejected(current, "RECONCILIATION_REQUIRED")

    if event.input_type is Input.RECORD_RECONCILIATION_RESULT:
        return _reconciliation_decision(current, event, context)

    specs = matching_specs(current.state, event.input_type)
    if not specs:
        return _rejected(current, "INVALID_LIFECYCLE_TRANSITION")
    spec = specs[0]
    guard_failure = _guard_failure(current, event, context, spec)
    if guard_failure is not None:
        return _rejected(current, guard_failure)
    return _accepted(current, event, context, spec)


def apply_transition(
    current: PaperExecutionLifecycle,
    decision: PaperExecutionTransitionDecision,
) -> PaperExecutionLifecycle:
    """Return the next immutable aggregate for an accepted decision."""

    if not decision.accepted:
        return current
    broker_reference = decision.broker_order_reference or current.broker_order_reference
    requested_quantity = decision.requested_quantity or current.requested_quantity
    cumulative_fill = (
        decision.observed_cumulative_fill_quantity
        if decision.observed_cumulative_fill_quantity is not None
        else current.cumulative_filled_quantity
    )
    return replace(
        current,
        state=decision.next_state,
        revision=decision.next_revision,
        last_command_id=decision.command_id or current.last_command_id,
        last_command_payload_fingerprint=(
            decision.command_payload_fingerprint
            or current.last_command_payload_fingerprint
        ),
        last_idempotency_key=decision.idempotency_key or current.last_idempotency_key,
        last_idempotency_payload_fingerprint=(
            decision.idempotency_payload_fingerprint
            or current.last_idempotency_payload_fingerprint
        ),
        broker_order_reference=broker_reference,
        last_broker_observation_id=(
            decision.broker_observation_id or current.last_broker_observation_id
        ),
        last_broker_observation_fingerprint=(
            decision.broker_observation_fingerprint
            or current.last_broker_observation_fingerprint
        ),
        requested_quantity=requested_quantity,
        cumulative_filled_quantity=cumulative_fill,
        active_replacement_command_id=(
            decision.active_replacement_command_id
            or current.active_replacement_command_id
        ),
        reconciliation_required=decision.reconciliation_required,
        outcome_unknown=decision.outcome_unknown,
        last_transition_id=decision.transition_id or current.last_transition_id,
        last_receipt_fingerprint=(
            decision.receipt_fingerprint or current.last_receipt_fingerprint
        ),
        last_failure_fingerprint=(
            decision.failure_fingerprint or current.last_failure_fingerprint
        ),
    )


def _validate_transition_arguments(
    current: PaperExecutionLifecycle,
    event: PaperExecutionLifecycleInput,
    context: PaperExecutionTransitionContext,
) -> None:
    if not isinstance(current, PaperExecutionLifecycle):
        raise TypeError("current must be a PaperExecutionLifecycle.")
    if not isinstance(event, PaperExecutionLifecycleInput):
        raise TypeError("event must be a PaperExecutionLifecycleInput.")
    if not isinstance(context, PaperExecutionTransitionContext):
        raise TypeError("context must be a PaperExecutionTransitionContext.")


def _accepted(
    current: PaperExecutionLifecycle,
    event: PaperExecutionLifecycleInput,
    context: PaperExecutionTransitionContext,
    spec: PaperExecutionTransitionSpecification,
    *,
    next_state: State | None = None,
    transition_id: str | None = None,
    evidence: Evidence | None = None,
    reconciliation_required: bool | None = None,
) -> PaperExecutionTransitionDecision:
    destination = next_state or spec.destination
    next_revision = current.revision.next()
    effect = spec.side_effect_intent_kind
    evidence_kind = evidence or spec.evidence_intent_kind
    observed_quantity = context.observed_cumulative_fill_quantity
    requested_quantity = context.requested_quantity or current.requested_quantity
    broker_reference = context.broker_reference or current.broker_order_reference
    return PaperExecutionTransitionDecision(
        decision_type=DecisionType.ACCEPTED,
        transition_id=transition_id or spec.transition_id,
        previous_state=current.state,
        next_state=destination,
        previous_revision=current.revision,
        next_revision=next_revision,
        replay_kind=ReplayKind.NONE,
        reason_code="ACCEPTED",
        side_effect_intents=(
            PaperExecutionLifecycleSideEffectIntent(
                effect,
                _intent_reason(spec.transition_id),
            ),
        ),
        evidence_intents=(
            PaperExecutionLifecycleEvidenceIntent(
                evidence_kind,
                _intent_reason(spec.transition_id),
            ),
        ),
        accepted=True,
        revision_incremented=True,
        reconciliation_required=(
            spec.reconciliation_required
            if reconciliation_required is None
            else reconciliation_required
        ),
        outcome_unknown=destination is State.OUTCOME_UNKNOWN,
        command_terminal=is_command_terminal(destination),
        aggregate_terminal=is_aggregate_terminal(destination),
        broker_order_terminal=is_broker_order_terminal(destination),
        command_id=event.command_id,
        command_payload_fingerprint=event.command_payload_fingerprint,
        idempotency_key=event.idempotency_key,
        idempotency_payload_fingerprint=event.idempotency_payload_fingerprint,
        broker_order_reference=broker_reference,
        broker_observation_id=event.broker_observation_id,
        broker_observation_fingerprint=event.broker_observation_fingerprint,
        requested_quantity=requested_quantity,
        observed_cumulative_fill_quantity=observed_quantity,
        active_replacement_command_id=(
            event.command_id if event.input_type is Input.REQUEST_REPLACEMENT else None
        ),
        receipt_fingerprint=event.receipt_fingerprint,
        failure_fingerprint=event.failure_fingerprint,
    )


def _rejected(
    current: PaperExecutionLifecycle,
    reason_code: str,
    *,
    decision_type: DecisionType = DecisionType.REJECTED,
    replay_kind: ReplayKind = ReplayKind.NONE,
    evidence_kind: Evidence = Evidence.LIFECYCLE_TRANSITION_REJECTED,
    reconciliation_required: bool | None = None,
) -> PaperExecutionTransitionDecision:
    return PaperExecutionTransitionDecision(
        decision_type=decision_type,
        transition_id=None,
        previous_state=current.state,
        next_state=current.state,
        previous_revision=current.revision,
        next_revision=current.revision,
        replay_kind=replay_kind,
        reason_code=reason_code,
        side_effect_intents=(
            PaperExecutionLifecycleSideEffectIntent(Effect.NONE, reason_code),
        ),
        evidence_intents=(
            PaperExecutionLifecycleEvidenceIntent(evidence_kind, reason_code),
        ),
        accepted=False,
        revision_incremented=False,
        reconciliation_required=(
            current.reconciliation_required
            if reconciliation_required is None
            else reconciliation_required
        ),
        outcome_unknown=current.outcome_unknown,
        command_terminal=current.command_terminal,
        aggregate_terminal=current.aggregate_terminal,
        broker_order_terminal=current.broker_order_terminal,
    )


def _replay_or_conflict_decision(
    current: PaperExecutionLifecycle,
    context: PaperExecutionTransitionContext,
) -> PaperExecutionTransitionDecision | None:
    if context.command_conflicts_with_prior:
        return _rejected(
            current,
            "COMMAND_CONFLICT",
            decision_type=DecisionType.COMMAND_CONFLICT,
            evidence_kind=Evidence.LIFECYCLE_COMMAND_CONFLICT,
        )
    if context.command_matches_prior:
        return _rejected(
            current,
            "COMMAND_REPLAY",
            decision_type=DecisionType.REPLAYED,
            replay_kind=ReplayKind.COMMAND_REPLAY,
            evidence_kind=Evidence.LIFECYCLE_REPLAYED,
        )
    if context.idempotency_conflicts_with_prior:
        return _rejected(
            current,
            "IDEMPOTENCY_CONFLICT",
            decision_type=DecisionType.IDEMPOTENCY_CONFLICT,
            evidence_kind=Evidence.LIFECYCLE_IDEMPOTENCY_CONFLICT,
        )
    if context.idempotency_matches_prior:
        return _rejected(
            current,
            "IDEMPOTENCY_REPLAY",
            decision_type=DecisionType.REPLAYED,
            replay_kind=ReplayKind.IDEMPOTENCY_REPLAY,
            evidence_kind=Evidence.LIFECYCLE_REPLAYED,
        )
    if context.broker_observation_conflicts_with_prior:
        return _rejected(
            current,
            "BROKER_OBSERVATION_CONFLICT",
            decision_type=DecisionType.BROKER_OBSERVATION_CONFLICT,
            evidence_kind=Evidence.LIFECYCLE_BROKER_OBSERVATION_CONFLICT,
            reconciliation_required=True,
        )
    if context.broker_observation_matches_prior:
        return _rejected(
            current,
            "BROKER_OBSERVATION_REPLAY",
            decision_type=DecisionType.REPLAYED,
            replay_kind=ReplayKind.BROKER_OBSERVATION_REPLAY,
            evidence_kind=Evidence.LIFECYCLE_BROKER_OBSERVATION_REPLAYED,
        )
    return None


def _guard_failure(
    current: PaperExecutionLifecycle,
    event: PaperExecutionLifecycleInput,
    context: PaperExecutionTransitionContext,
    spec: PaperExecutionTransitionSpecification,
) -> str | None:
    if event.input_type is Input.RECORD_ELIGIBILITY:
        return _eligibility_failure(context, expected="ELIGIBLE")
    if event.input_type is Input.RECORD_INELIGIBLE:
        return _eligibility_failure(context, expected="INELIGIBLE")
    if event.input_type is Input.RECORD_INDETERMINATE:
        return _eligibility_failure(context, expected="INDETERMINATE")
    if event.input_type is Input.RECORD_APPROVAL:
        if context.eligibility_decision not in {None, "ELIGIBLE"}:
            return "ELIGIBILITY_NOT_COMPATIBLE"
        if not (
            context.approval_binding_valid
            and context.approval_time_valid
            and context.policy_compatible
        ):
            return "APPROVAL_INVALID"
    if event.input_type is Input.RECORD_IDEMPOTENCY_RESERVATION:
        if not context.idempotency_reservation_confirmed:
            return "IDEMPOTENCY_NOT_CONFIRMED"
    if event.input_type is Input.PREPARE_DISPATCH:
        if not context.emergency_stop_clearance:
            return "EMERGENCY_STOP_ACTIVE"
        if not context.external_prerequisites_satisfied:
            return "EXTERNAL_PREREQUISITES_NOT_SATISFIED"
    if event.input_type in {
        Input.OBSERVE_BROKER_ACKNOWLEDGEMENT,
        Input.OBSERVE_CANCELLATION_CONFIRMATION,
        Input.OBSERVE_REPLACEMENT_CONFIRMATION,
    }:
        if context.broker_reference is None and current.broker_order_reference is None:
            return "BROKER_REFERENCE_MISSING"
    if event.input_type in BROKER_OBSERVATION_INPUTS:
        if not event.broker_observation_id or not event.broker_observation_fingerprint:
            return "BROKER_OBSERVATION_IDENTITY_MISSING"
    if event.input_type in {
        Input.OBSERVE_PARTIAL_FILL,
        Input.OBSERVE_FILL,
    }:
        return _fill_failure(
            current, context, final_fill=event.input_type is Input.OBSERVE_FILL
        )
    if event.input_type is Input.REQUEST_CANCELLATION:
        if current.state is State.PARTIALLY_FILLED and _remaining_quantity(
            current
        ) <= Decimal("0"):
            return "NOTHING_LEFT_TO_CANCEL"
    if event.input_type is Input.REQUEST_REPLACEMENT:
        return _replacement_failure(current, context)
    return None


def _eligibility_failure(
    context: PaperExecutionTransitionContext,
    *,
    expected: str,
) -> str | None:
    if context.eligibility_decision != expected:
        return f"ELIGIBILITY_DECISION_NOT_{expected}"
    return None


def _fill_failure(
    current: PaperExecutionLifecycle,
    context: PaperExecutionTransitionContext,
    *,
    final_fill: bool,
) -> str | None:
    observed = context.observed_cumulative_fill_quantity
    if observed is None:
        return "FILL_QUANTITY_MISSING"
    if observed < current.cumulative_filled_quantity:
        return "FILL_NOT_MONOTONIC"
    requested = context.requested_quantity or current.requested_quantity
    if requested is not None:
        if observed > requested:
            return "FILL_EXCEEDS_REQUESTED_QUANTITY"
        if final_fill and observed != requested:
            return "FINAL_FILL_MUST_EQUAL_REQUESTED_QUANTITY"
        if not final_fill and observed >= requested:
            return "PARTIAL_FILL_MUST_BE_LESS_THAN_REQUESTED_QUANTITY"
    return None


def _replacement_failure(
    current: PaperExecutionLifecycle,
    context: PaperExecutionTransitionContext,
) -> str | None:
    if context.replacement_quantity is None:
        return "REPLACEMENT_QUANTITY_MISSING"
    if context.replacement_quantity < current.cumulative_filled_quantity:
        return "REPLACEMENT_BELOW_FILLED_QUANTITY"
    return None


def _remaining_quantity(current: PaperExecutionLifecycle) -> Decimal:
    if current.requested_quantity is None:
        return Decimal("1")
    return current.requested_quantity - current.cumulative_filled_quantity


def _reconciliation_decision(
    current: PaperExecutionLifecycle,
    event: PaperExecutionLifecycleInput,
    context: PaperExecutionTransitionContext,
) -> PaperExecutionTransitionDecision:
    if current.state is not State.RECONCILIATION_REQUIRED:
        return _rejected(current, "INVALID_LIFECYCLE_TRANSITION")
    if context.reconciliation_outcome is None:
        return _rejected(current, "RECONCILIATION_OUTCOME_MISSING")
    destination = context.reconciliation_destination
    outcome = context.reconciliation_outcome
    if outcome is ReconciliationOutcome.CONSISTENT:
        spec = TRANSITION_BY_ID["PX-TRN-026"]
        destination = destination or State.BROKER_ACKNOWLEDGED
    elif outcome in {
        ReconciliationOutcome.BROKER_AHEAD,
        ReconciliationOutcome.MISSING_LOCALLY,
    }:
        spec = TRANSITION_BY_ID["PX-TRN-027"]
        destination = destination or State.PARTIALLY_FILLED
    elif outcome is ReconciliationOutcome.OPERATOR_ACTION_REQUIRED:
        if not (
            context.approval_binding_valid
            and context.approval_time_valid
            and context.policy_compatible
        ):
            return _rejected(
                current,
                "OPERATOR_RECOVERY_APPROVAL_INVALID",
                reconciliation_required=True,
            )
        if destination is None or destination is State.RECONCILIATION_REQUIRED:
            return _rejected(
                current,
                "OPERATOR_RECOVERY_DESTINATION_REQUIRED",
                reconciliation_required=True,
            )
        spec = TRANSITION_BY_ID["PX-TRN-027"]
    else:
        spec = TRANSITION_BY_ID["PX-TRN-028"]
        destination = State.RECONCILIATION_REQUIRED
    if destination not in RECONCILIATION_RECOVERY_STATES:
        return _rejected(current, "RECONCILIATION_DESTINATION_NOT_BOUNDED")
    unresolved = destination is State.RECONCILIATION_REQUIRED
    return _accepted(
        current,
        event,
        context,
        spec,
        next_state=destination,
        evidence=(
            Evidence.LIFECYCLE_RECONCILIATION_REQUIRED
            if unresolved
            else Evidence.LIFECYCLE_TRANSITION_ACCEPTED
        ),
        reconciliation_required=unresolved,
    )


def next_revision_after_acceptance(
    revision: PaperExecutionRevision,
) -> PaperExecutionRevision:
    """Return the deterministic accepted-transition successor revision."""

    return revision.next()


def _intent_reason(transition_id: str) -> str:
    return transition_id.replace("-", "_")
