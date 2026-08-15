from __future__ import annotations

from datetime import UTC, datetime

import pytest

from volcanoes.application.execution.fingerprints import fingerprint_payload
from volcanoes.application.execution.identities import (
    PaperBrokerOrderReference,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionIdempotencyKey,
    PaperExecutionRevision,
)
from volcanoes.application.execution.lifecycle import (
    PaperExecutionLifecycle,
    PaperExecutionLifecycleInput,
    PaperExecutionLifecycleInputType as Input,
    PaperExecutionLifecycleState as State,
    PaperExecutionReconciliationOutcome as Outcome,
    PaperExecutionTransitionContext,
    apply_transition,
    transition,
)
from volcanoes.application.execution.reconciliation import (
    ReconciliationDecision,
    ReconciliationFacts,
    build_operator_recovery_command_record,
    build_reconciliation_history_record,
)

NOW = datetime(2026, 8, 15, 22, 0, tzinfo=UTC)
AGGREGATE_ID = PaperExecutionAggregateId.from_seed("f6b", "operator-transition")
CORRELATION_ID = PaperExecutionCorrelationId.from_seed("f6b", "operator-transition")
COMMAND_ID = PaperExecutionCommandId.from_seed("f6b", "operator-transition")
IDEMPOTENCY_KEY = PaperExecutionIdempotencyKey.from_seed("f6b", "operator-transition")


def _current() -> PaperExecutionLifecycle:
    return PaperExecutionLifecycle(
        aggregate_id=AGGREGATE_ID,
        state=State.RECONCILIATION_REQUIRED,
        revision=PaperExecutionRevision(11),
        correlation_id=CORRELATION_ID,
        broker_order_reference=PaperBrokerOrderReference.from_seed("f6b", "broker"),
        reconciliation_required=True,
    )


def _recovery_command(destination: State = State.FILLED):
    history = build_reconciliation_history_record(
        aggregate_id=AGGREGATE_ID,
        starting_revision=PaperExecutionRevision(11),
        starting_state=State.RECONCILIATION_REQUIRED,
        facts=ReconciliationFacts(
            local_present=True,
            broker_present=True,
            local_state=State.RECONCILIATION_REQUIRED,
            broker_state=destination,
            observation_conflict=True,
        ),
        decision=ReconciliationDecision(
            outcome=Outcome.OPERATOR_ACTION_REQUIRED,
            reason="CONFLICTING_EVIDENCE",
            proposed_state=State.RECONCILIATION_REQUIRED,
            operator_action_required=True,
        ),
        recorded_at=NOW,
        schema_version=4,
    )
    return build_operator_recovery_command_record(
        reconciliation=history,
        destination=destination,
        command_id=COMMAND_ID,
        correlation_id=CORRELATION_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        approval_fingerprint=fingerprint_payload("pap", {"operator": "approved"}),
        policy_fingerprint=fingerprint_payload("pps", {"policy": "f6b-recovery"}),
        received_at=NOW,
        schema_version=4,
    )


def _event(destination: State = State.FILLED) -> PaperExecutionLifecycleInput:
    command = _recovery_command(destination)
    return PaperExecutionLifecycleInput(
        input_type=Input.RECORD_RECONCILIATION_RESULT,
        command_id=command.command_id,
        aggregate_id=command.aggregate_id,
        correlation_id=command.correlation_id,
        idempotency_key=command.idempotency_key,
        command_payload_fingerprint=command.canonical_payload_fingerprint,
        idempotency_payload_fingerprint=command.canonical_payload_fingerprint,
    )


def _context(current: PaperExecutionLifecycle, destination: State = State.FILLED, **overrides: object):
    values: dict[str, object] = {
        "expected_revision": current.revision,
        "approval_binding_valid": True,
        "approval_time_valid": True,
        "policy_compatible": True,
        "reconciliation_outcome": Outcome.OPERATOR_ACTION_REQUIRED,
        "reconciliation_destination": destination,
    }
    values.update(overrides)
    return PaperExecutionTransitionContext(**values)


def test_approved_operator_recovery_advances_exactly_one_revision() -> None:
    current = _current()
    command = _recovery_command(State.FILLED)
    decision = transition(current, _event(State.FILLED), _context(current, State.FILLED))

    assert decision.accepted is True
    assert decision.command_id == command.command_id
    assert decision.command_payload_fingerprint == command.canonical_payload_fingerprint
    assert decision.next_state is State.FILLED
    assert decision.previous_revision == PaperExecutionRevision(11)
    assert decision.next_revision == PaperExecutionRevision(12)
    assert decision.reconciliation_required is False

    updated = apply_transition(current, decision)
    assert updated.state is State.FILLED
    assert updated.revision == PaperExecutionRevision(12)
    assert updated.last_command_id == command.command_id
    assert updated.last_transition_id == decision.transition_id
    assert updated.reconciliation_required is False


@pytest.mark.parametrize(
    "invalid_flag",
    ("approval_binding_valid", "approval_time_valid", "policy_compatible"),
)
def test_operator_recovery_without_complete_approval_fails_closed(invalid_flag: str) -> None:
    current = _current()
    decision = transition(
        current,
        _event(),
        _context(current, **{invalid_flag: False}),
    )

    assert decision.accepted is False
    assert decision.reason_code == "OPERATOR_RECOVERY_APPROVAL_INVALID"
    assert decision.next_state is State.RECONCILIATION_REQUIRED
    assert decision.next_revision == current.revision
    assert decision.reconciliation_required is True


def test_operator_recovery_requires_resolved_destination() -> None:
    current = _current()
    decision = transition(
        current,
        _event(),
        _context(current, reconciliation_destination=None),
    )

    assert decision.accepted is False
    assert decision.reason_code == "OPERATOR_RECOVERY_DESTINATION_REQUIRED"
    assert decision.next_revision == current.revision
    assert decision.reconciliation_required is True


def test_unresolved_outcome_cannot_escape_with_valid_operator_approval() -> None:
    current = _current()
    decision = transition(
        current,
        _event(),
        _context(
            current,
            reconciliation_outcome=Outcome.UNRESOLVED,
            reconciliation_destination=State.FILLED,
        ),
    )

    assert decision.accepted is True
    assert decision.next_state is State.RECONCILIATION_REQUIRED
    assert decision.reconciliation_required is True


def test_operator_recovery_still_rejects_unbounded_destination() -> None:
    current = _current()
    decision = transition(
        current,
        _event(),
        _context(current, State.READY_FOR_DISPATCH),
    )

    assert decision.accepted is False
    assert decision.reason_code == "RECONCILIATION_DESTINATION_NOT_BOUNDED"
    assert decision.next_revision == current.revision
