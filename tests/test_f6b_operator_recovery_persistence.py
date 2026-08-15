from __future__ import annotations

from datetime import UTC, datetime

import pytest

from volcanoes.application.execution.enums import PaperExecutionOperation
from volcanoes.application.execution.fingerprints import fingerprint_payload
from volcanoes.application.execution.identities import (
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionIdempotencyKey,
    PaperExecutionRevision,
)
from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionLifecycleState as State,
    PaperExecutionReconciliationOutcome as Outcome,
)
from volcanoes.application.execution.persistence.enums import (
    ExecutionCommandProcessingOutcome,
)
from volcanoes.application.execution.reconciliation import (
    ReconciliationDecision,
    ReconciliationFacts,
    build_operator_recovery_command_record,
    build_reconciliation_history_record,
)

NOW = datetime(2026, 8, 15, 21, 30, tzinfo=UTC)
AGGREGATE_ID = PaperExecutionAggregateId.from_seed("f6b", "recovery")
COMMAND_ID = PaperExecutionCommandId.from_seed("f6b", "operator-recovery")
CORRELATION_ID = PaperExecutionCorrelationId.from_seed("f6b", "recovery")
IDEMPOTENCY_KEY = PaperExecutionIdempotencyKey.from_seed("f6b", "operator-recovery")
APPROVAL = fingerprint_payload("pap", {"operator": "approved"})
POLICY = fingerprint_payload("pps", {"policy": "f6b-recovery"})


def _operator_history():
    decision = ReconciliationDecision(
        outcome=Outcome.OPERATOR_ACTION_REQUIRED,
        reason="STATE_CONFLICT",
        proposed_state=State.RECONCILIATION_REQUIRED,
        operator_action_required=True,
    )
    return build_reconciliation_history_record(
        aggregate_id=AGGREGATE_ID,
        starting_revision=PaperExecutionRevision(11),
        starting_state=State.RECONCILIATION_REQUIRED,
        facts=ReconciliationFacts(
            local_present=True,
            broker_present=True,
            local_state=State.RECONCILIATION_REQUIRED,
            broker_state=State.FILLED,
            observation_conflict=True,
        ),
        decision=decision,
        recorded_at=NOW,
        schema_version=4,
    )


def _build(destination: State = State.FILLED):
    return build_operator_recovery_command_record(
        reconciliation=_operator_history(),
        destination=destination,
        command_id=COMMAND_ID,
        correlation_id=CORRELATION_ID,
        idempotency_key=IDEMPOTENCY_KEY,
        approval_fingerprint=APPROVAL,
        policy_fingerprint=POLICY,
        received_at=NOW,
        schema_version=4,
    )


def test_operator_recovery_is_a_durable_pending_reconcile_command() -> None:
    history = _operator_history()
    command = _build()

    assert command.aggregate_id == history.aggregate_id
    assert command.expected_execution_revision == history.starting_local_revision
    assert command.operation is PaperExecutionOperation.RECONCILE
    assert command.processing_outcome is ExecutionCommandProcessingOutcome.PENDING
    assert history.reconciliation_id in command.canonical_command_json
    assert history.record_fingerprint in command.canonical_command_json
    assert '"destination":"FILLED"' in command.canonical_command_json


def test_same_operator_recovery_payload_is_deterministic() -> None:
    first = _build()
    second = _build()

    assert first.canonical_payload_fingerprint == second.canonical_payload_fingerprint
    assert first.record_fingerprint == second.record_fingerprint


def test_recovery_destination_is_bound_into_command_identity() -> None:
    filled = _build(State.FILLED)
    cancelled = _build(State.CANCELLED)

    assert filled.canonical_payload_fingerprint != cancelled.canonical_payload_fingerprint
    assert filled.record_fingerprint != cancelled.record_fingerprint


def test_operator_recovery_cannot_persist_a_still_unresolved_destination() -> None:
    with pytest.raises(ValueError, match="resolved destination"):
        _build(State.RECONCILIATION_REQUIRED)


def test_non_operator_reconciliation_cannot_be_promoted_to_operator_recovery() -> None:
    history = build_reconciliation_history_record(
        aggregate_id=AGGREGATE_ID,
        starting_revision=PaperExecutionRevision(11),
        starting_state=State.RECONCILIATION_REQUIRED,
        facts=ReconciliationFacts(
            local_present=True,
            broker_present=True,
            local_state=State.RECONCILIATION_REQUIRED,
            broker_state=State.FILLED,
        ),
        decision=ReconciliationDecision(
            outcome=Outcome.BROKER_AHEAD,
            reason="BROKER_HAS_PROVABLE_LATER_STATE",
            proposed_state=State.FILLED,
            operator_action_required=False,
        ),
        recorded_at=NOW,
        schema_version=4,
    )

    with pytest.raises(ValueError, match="operator-action reconciliation"):
        build_operator_recovery_command_record(
            reconciliation=history,
            destination=State.FILLED,
            command_id=COMMAND_ID,
            correlation_id=CORRELATION_ID,
            idempotency_key=IDEMPOTENCY_KEY,
            approval_fingerprint=APPROVAL,
            policy_fingerprint=POLICY,
            received_at=NOW,
            schema_version=4,
        )
