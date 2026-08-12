from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from volcanoes.application.execution import (
    ExecutionApprovalRecord,
    ExecutionBrokerReferenceRecord,
    ExecutionBrokerReferenceStatus,
    ExecutionCommandProcessingOutcome,
    ExecutionCommandRecord,
    ExecutionFailureRecord,
    ExecutionIdempotencyRecord,
    ExecutionIdempotencyReservationStatus,
    ExecutionPersistenceResultStatus,
    ExecutionReceiptRecord,
    ExecutionReconciliationRecord,
    ExecutionReconciliationResultClassification,
    ExecutionReplayKind,
    ExecutionTransitionRecord,
    InMemoryExecutionPersistence,
    InMemoryExecutionPersistenceState,
    PaperBrokerOrderReference,
    PaperExecutionAggregateId,
    PaperExecutionApprovalKind,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionFailure,
    PaperExecutionFailureKind,
    PaperExecutionFailureSeverity,
    PaperExecutionIdempotencyKey,
    PaperExecutionLifecycleEvidenceIntentKind,
    PaperExecutionLifecycleInputType,
    PaperExecutionLifecycleSideEffectIntentKind,
    PaperExecutionLifecycleState,
    PaperExecutionOperation,
    PaperExecutionReceipt,
    PaperExecutionReceiptKind,
    PaperExecutionRevision,
    PaperExecutionStatus,
)
from volcanoes.application.execution.fingerprints import (
    approval_fingerprint,
    command_payload_fingerprint,
    fingerprint_payload,
    policy_fingerprint,
)

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=1)
SCHEMA_VERSION = 1


def aggregate_id(symbol: str = "AAPL") -> PaperExecutionAggregateId:
    return PaperExecutionAggregateId.from_seed("aggregate", symbol)


def command_id(symbol: str = "AAPL") -> PaperExecutionCommandId:
    return PaperExecutionCommandId.from_seed("command", symbol)


def correlation_id(symbol: str = "AAPL") -> PaperExecutionCorrelationId:
    return PaperExecutionCorrelationId.from_seed("correlation", symbol)


def idempotency_key(symbol: str = "AAPL") -> PaperExecutionIdempotencyKey:
    return PaperExecutionIdempotencyKey.from_seed("idempotency", symbol)


def broker_reference(symbol: str = "AAPL") -> PaperBrokerOrderReference:
    return PaperBrokerOrderReference.from_seed("reference", symbol)


def aggregate_record(symbol: str = "AAPL", **overrides: object):
    values = {
        "aggregate_id": aggregate_id(symbol),
        "correlation_id": correlation_id(symbol),
        "lifecycle_state": PaperExecutionLifecycleState.CREATED,
        "execution_revision": PaperExecutionRevision.initial(),
        "cumulative_filled_quantity": Decimal("0"),
        "requested_quantity": Decimal("1"),
        "active_broker_reference": None,
        "outcome_unknown": False,
        "reconciliation_required": False,
        "command_terminal": False,
        "aggregate_terminal": False,
        "last_transition_id": f"transition-{symbol}-0",
        "last_command_id": command_id(symbol),
        "last_idempotency_key": idempotency_key(symbol),
        "last_receipt_fingerprint": None,
        "last_failure_fingerprint": None,
        "created_at": NOW,
        "updated_at": LATER,
        "schema_version": SCHEMA_VERSION,
    }
    values.update(overrides)
    return __import__(
        "volcanoes.application.execution", fromlist=["ExecutionAggregateRecord"]
    ).ExecutionAggregateRecord(**values)


def aggregate_revision_one(symbol: str = "AAPL", **overrides: object):
    values = {
        "lifecycle_state": PaperExecutionLifecycleState.ELIGIBILITY_EVALUATED,
        "execution_revision": PaperExecutionRevision(1),
        "last_transition_id": f"transition-{symbol}-1",
    }
    values.update(overrides)
    return aggregate_record(symbol, **values)


def command_record(
    symbol: str = "AAPL", payload: object | None = None, **overrides: object
):
    payload = payload or {"symbol": symbol, "quantity": 1, "operation": "SUBMIT"}
    values = {
        "command_id": command_id(symbol),
        "aggregate_id": aggregate_id(symbol),
        "correlation_id": correlation_id(symbol),
        "idempotency_key": idempotency_key(symbol),
        "operation": PaperExecutionOperation.SUBMIT,
        "expected_execution_revision": PaperExecutionRevision.initial(),
        "canonical_payload_fingerprint": command_payload_fingerprint(payload),
        "canonical_command_json": '{"operation":"SUBMIT","quantity":1,"symbol":"%s"}'
        % symbol,
        "approval_fingerprint": approval_fingerprint(("approval", symbol)),
        "policy_fingerprint": policy_fingerprint(("policy", symbol)),
        "received_at": NOW,
        "processing_outcome": ExecutionCommandProcessingOutcome.ACCEPTED,
        "schema_version": SCHEMA_VERSION,
    }
    values.update(overrides)
    return ExecutionCommandRecord(**values)


def idempotency_record(symbol: str = "AAPL", **overrides: object):
    values = {
        "idempotency_key": idempotency_key(symbol),
        "logical_operation_fingerprint": fingerprint_payload("plo", ("submit", symbol)),
        "command_id": command_id(symbol),
        "aggregate_id": aggregate_id(symbol),
        "reservation_status": ExecutionIdempotencyReservationStatus.RESERVED,
        "original_result_fingerprint": None,
        "created_at": NOW,
        "resolved_at": None,
        "conflict": False,
        "schema_version": SCHEMA_VERSION,
    }
    values.update(overrides)
    return ExecutionIdempotencyRecord(**values)


def transition_record(symbol: str = "AAPL", number: int = 1, **overrides: object):
    values = {
        "transition_record_id": f"transition-record-{symbol}-{number}",
        "aggregate_id": aggregate_id(symbol),
        "transition_id": f"transition-{symbol}-{number}",
        "source_state": PaperExecutionLifecycleState.CREATED,
        "destination_state": PaperExecutionLifecycleState.ELIGIBILITY_EVALUATED,
        "previous_revision": PaperExecutionRevision(number - 1),
        "next_revision": PaperExecutionRevision(number),
        "lifecycle_input_kind": PaperExecutionLifecycleInputType.RECORD_ELIGIBILITY,
        "input_identity": f"input-{symbol}-{number}",
        "command_id": command_id(symbol),
        "correlation_id": correlation_id(symbol),
        "idempotency_key": idempotency_key(symbol),
        "replay_indicator": ExecutionReplayKind.NONE,
        "side_effect_intent_kinds": (PaperExecutionLifecycleSideEffectIntentKind.NONE,),
        "evidence_intent_kinds": (
            PaperExecutionLifecycleEvidenceIntentKind.LIFECYCLE_TRANSITION_ACCEPTED,
        ),
        "safe_reason_code": "ELIGIBILITY_RECORDED",
        "recorded_at": NOW + timedelta(seconds=number),
        "schema_version": SCHEMA_VERSION,
    }
    values.update(overrides)
    return ExecutionTransitionRecord(**values)


def broker_reference_record(symbol: str = "AAPL", **overrides: object):
    values = {
        "broker_reference": broker_reference(symbol),
        "aggregate_id": aggregate_id(symbol),
        "command_id": command_id(symbol),
        "adapter_identity": "paper.adapter",
        "reference_status": ExecutionBrokerReferenceStatus.ACTIVE,
        "first_seen_at": NOW,
        "last_seen_at": LATER,
        "active": True,
        "schema_version": SCHEMA_VERSION,
    }
    values.update(overrides)
    return ExecutionBrokerReferenceRecord(**values)


def receipt(symbol: str = "AAPL") -> PaperExecutionReceipt:
    return PaperExecutionReceipt(
        command_id=command_id(symbol),
        aggregate_id=aggregate_id(symbol),
        correlation_id=correlation_id(symbol),
        operation=PaperExecutionOperation.SUBMIT,
        receipt_kind=PaperExecutionReceiptKind.COMMAND_ACCEPTED_LOCALLY,
        status=PaperExecutionStatus.CREATED,
        observed_execution_revision=PaperExecutionRevision.initial(),
        observed_at=NOW,
        message_code="COMMAND_ACCEPTED",
    )


def failure(symbol: str = "AAPL") -> PaperExecutionFailure:
    return PaperExecutionFailure(
        failure_kind=PaperExecutionFailureKind.STALE_REVISION,
        severity=PaperExecutionFailureSeverity.ERROR,
        code="STALE_REVISION",
        safe_message="State changed before command.",
        retryable=False,
        reconciliation_required=False,
        operator_action_required=False,
        terminal=False,
        authority_impacting=False,
        command_id=command_id(symbol),
        aggregate_id=aggregate_id(symbol),
        correlation_id=correlation_id(symbol),
    )


def receipt_record(symbol: str = "AAPL"):
    return ExecutionReceiptRecord(
        receipt=receipt(symbol), recorded_at=NOW, schema_version=SCHEMA_VERSION
    )


def failure_record(symbol: str = "AAPL"):
    return ExecutionFailureRecord(
        failure=failure(symbol), recorded_at=NOW, schema_version=SCHEMA_VERSION
    )


def approval_record(symbol: str = "AAPL", **overrides: object):
    values = {
        "approval_fingerprint": approval_fingerprint(("approval", symbol)),
        "bound_fingerprint": command_payload_fingerprint(("intent", symbol)),
        "approval_kind": PaperExecutionApprovalKind.OPERATOR.value,
        "approver_safe_reference": "operator.local",
        "approved_at": NOW,
        "recorded_at": LATER,
        "schema_version": SCHEMA_VERSION,
    }
    values.update(overrides)
    return ExecutionApprovalRecord(**values)


def reconciliation_record(symbol: str = "AAPL", **overrides: object):
    values = {
        "reconciliation_id": f"reconciliation-{symbol}",
        "aggregate_id": aggregate_id(symbol),
        "starting_local_revision": PaperExecutionRevision(3),
        "starting_lifecycle_state": PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
        "broker_observation_references": (f"observation-{symbol}",),
        "result_classification": ExecutionReconciliationResultClassification.UNRESOLVED,
        "operator_action_required": True,
        "unresolved": True,
        "safe_reason_code": "OUTCOME_UNKNOWN",
        "recorded_at": NOW,
        "schema_version": SCHEMA_VERSION,
    }
    values.update(overrides)
    return ExecutionReconciliationRecord(**values)


def committed_store_with_aggregate(
    symbol: str = "AAPL",
) -> InMemoryExecutionPersistence:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    result = uow.aggregates.save(
        aggregate_record(symbol), expected_revision=PaperExecutionRevision.initial()
    )
    assert result.status is ExecutionPersistenceResultStatus.CREATED
    assert uow.commit().committed is True
    return store


def test_adapter_instances_do_not_share_state() -> None:
    first = committed_store_with_aggregate("AAPL")
    second = InMemoryExecutionPersistence()

    assert len(first.snapshot().aggregate_records()) == 1
    assert second.snapshot().aggregate_records() == ()


def test_state_snapshot_does_not_expose_mutable_base() -> None:
    store = committed_store_with_aggregate("AAPL")
    snapshot = store.snapshot()
    snapshot._aggregates.clear()

    assert len(store.snapshot().aggregate_records()) == 1


def test_state_records_are_returned_as_tuples() -> None:
    store = committed_store_with_aggregate("AAPL")

    assert isinstance(store.snapshot().aggregate_records(), tuple)


def test_aggregate_create_load_and_save() -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()

    assert (
        uow.aggregates.get(aggregate_id()).status
        is ExecutionPersistenceResultStatus.NOT_FOUND
    )
    created = uow.aggregates.save(
        aggregate_record(), expected_revision=PaperExecutionRevision.initial()
    )
    assert created.status is ExecutionPersistenceResultStatus.CREATED
    assert (
        uow.aggregates.get(aggregate_id()).status
        is ExecutionPersistenceResultStatus.LOADED
    )
    updated = uow.aggregates.save(
        aggregate_revision_one(), expected_revision=PaperExecutionRevision.initial()
    )
    assert updated.status is ExecutionPersistenceResultStatus.SAVED
    assert uow.aggregates.load_record(
        aggregate_id()
    ).execution_revision == PaperExecutionRevision(1)


def test_aggregate_stale_revision_is_data_not_mutation() -> None:
    store = committed_store_with_aggregate()
    uow = store.unit_of_work()

    result = uow.aggregates.save(
        aggregate_revision_one(), expected_revision=PaperExecutionRevision(99)
    )

    assert result.status is ExecutionPersistenceResultStatus.STALE_REVISION
    assert result.conflict is not None
    assert (
        store.snapshot().aggregate_records()[0].execution_revision
        == PaperExecutionRevision.initial()
    )


def test_aggregate_terminal_state_is_protected() -> None:
    terminal = aggregate_record(aggregate_terminal=True)
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    assert (
        uow.aggregates.save(
            terminal, expected_revision=PaperExecutionRevision.initial()
        ).status
        is ExecutionPersistenceResultStatus.CREATED
    )
    assert uow.commit().committed is True

    second = store.unit_of_work()
    result = second.aggregates.save(
        aggregate_revision_one(), expected_revision=PaperExecutionRevision.initial()
    )

    assert result.status is ExecutionPersistenceResultStatus.ALREADY_TERMINAL


def test_command_register_replay_and_conflict() -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    record = command_record()

    assert (
        uow.commands.register(record).status is ExecutionPersistenceResultStatus.CREATED
    )
    assert (
        uow.commands.register(record).status
        is ExecutionPersistenceResultStatus.EXACT_REPLAY
    )
    conflict = uow.commands.register(command_record(payload={"different": True}))

    assert conflict.status is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
    assert (
        uow.commands.load_record(command_id()).record_fingerprint
        == record.record_fingerprint
    )


def test_command_lookup_replay_distinguishes_missing_exact_and_conflict() -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    record = command_record()

    assert (
        uow.commands.lookup_replay(
            record.command_id, record.canonical_payload_fingerprint
        ).status
        is ExecutionPersistenceResultStatus.NOT_FOUND
    )
    uow.commands.register(record)
    assert (
        uow.commands.lookup_replay(
            record.command_id, record.canonical_payload_fingerprint
        ).status
        is ExecutionPersistenceResultStatus.EXACT_REPLAY
    )
    assert (
        uow.commands.lookup_replay(
            record.command_id, command_payload_fingerprint({"different": True})
        ).status
        is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
    )


def test_idempotency_reservation_replay_and_conflict() -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    record = idempotency_record()

    assert (
        uow.idempotency.reserve(record).status
        is ExecutionPersistenceResultStatus.CREATED
    )
    replay = uow.idempotency.reserve(
        idempotency_record(command_id=PaperExecutionCommandId.from_seed("command", "B"))
    )
    assert replay.status is ExecutionPersistenceResultStatus.LOGICAL_REPLAY
    conflict = uow.idempotency.reserve(
        idempotency_record(
            logical_operation_fingerprint=fingerprint_payload("plo", ("other", "AAPL"))
        )
    )
    assert conflict.status is ExecutionPersistenceResultStatus.IDEMPOTENCY_CONFLICT


@pytest.mark.parametrize(
    "reservation_status",
    [
        ExecutionIdempotencyReservationStatus.RESERVED,
        ExecutionIdempotencyReservationStatus.COMPLETED,
        ExecutionIdempotencyReservationStatus.RECONCILIATION_REQUIRED,
    ],
)
def test_idempotency_statuses_are_stored_without_expiry(reservation_status) -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    record = idempotency_record(reservation_status=reservation_status)

    assert (
        uow.idempotency.reserve(record).status
        is ExecutionPersistenceResultStatus.CREATED
    )
    assert (
        uow.idempotency.load_record(idempotency_key()).reservation_status
        is reservation_status
    )


def test_transition_append_order_replay_and_conflict() -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    first = transition_record("AAPL", 1)
    second = transition_record(
        "AAPL",
        2,
        source_state=PaperExecutionLifecycleState.ELIGIBILITY_EVALUATED,
        destination_state=PaperExecutionLifecycleState.DISPATCH_PENDING,
    )

    assert (
        uow.transitions.append(first).status
        is ExecutionPersistenceResultStatus.APPENDED
    )
    assert (
        uow.transitions.append(second).status
        is ExecutionPersistenceResultStatus.APPENDED
    )
    assert (
        uow.transitions.append(first).status
        is ExecutionPersistenceResultStatus.EXACT_REPLAY
    )
    conflict = uow.transitions.append(
        replace(first, safe_reason_code="DIFFERENT_REASON")
    )

    assert conflict.status is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
    assert uow.transitions.history(aggregate_id()) == (first, second)


def test_broker_reference_register_replay_and_conflict_without_access() -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    record = broker_reference_record()

    assert (
        uow.broker_references.register(record).status
        is ExecutionPersistenceResultStatus.CREATED
    )
    assert (
        uow.broker_references.register(record).status
        is ExecutionPersistenceResultStatus.EXACT_REPLAY
    )
    conflict = uow.broker_references.register(
        broker_reference_record(
            aggregate_id=aggregate_id("MSFT"), command_id=command_id("MSFT")
        )
    )

    assert (
        conflict.status is ExecutionPersistenceResultStatus.DUPLICATE_BROKER_REFERENCE
    )


@pytest.mark.parametrize(
    ("repository_name", "record_factory", "records_method"),
    [
        ("receipts", receipt_record, "receipt_records"),
        ("failures", failure_record, "failure_records"),
        ("approvals", approval_record, "approval_records"),
        ("reconciliations", reconciliation_record, "reconciliation_records"),
    ],
)
def test_fact_repositories_record_duplicate_and_iterate(
    repository_name, record_factory, records_method
) -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    repository = getattr(uow, repository_name)
    record = record_factory()

    assert repository.record(record).status is ExecutionPersistenceResultStatus.CREATED
    assert (
        repository.record(record).status
        is ExecutionPersistenceResultStatus.EXACT_REPLAY
    )
    assert getattr(uow.transaction_state, records_method)() == (record,)


def test_approval_same_identity_different_content_conflicts() -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    record = approval_record()
    other = approval_record(
        bound_fingerprint=command_payload_fingerprint(("other", "AAPL"))
    )

    assert (
        uow.approvals.record(record).status is ExecutionPersistenceResultStatus.CREATED
    )
    assert (
        uow.approvals.record(other).status
        is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
    )


def test_reconciliation_same_identity_different_content_conflicts() -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    record = reconciliation_record()
    other = reconciliation_record(safe_reason_code="DIFFERENT_REASON")

    assert (
        uow.reconciliations.record(record).status
        is ExecutionPersistenceResultStatus.CREATED
    )
    assert (
        uow.reconciliations.record(other).status
        is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
    )


def test_returned_records_are_immutable() -> None:
    store = committed_store_with_aggregate()
    record = store.snapshot().aggregate_records()[0]

    with pytest.raises(FrozenInstanceError):
        record.schema_version = 2


def test_state_sequence_is_deterministic_and_instance_local() -> None:
    first = InMemoryExecutionPersistenceState()
    second = InMemoryExecutionPersistenceState()

    assert first.next_sequence() == 1
    assert first.next_sequence() == 2
    assert second.next_sequence() == 1
