from __future__ import annotations

import pytest

from volcanoes.application.execution import (
    ExecutionPersistenceResultStatus,
    InMemoryExecutionPersistence,
    PaperExecutionRevision,
)
from volcanoes.application.execution.fingerprints import fingerprint_payload
from test_execution_persistence_in_memory_repositories import (
    LATER,
    aggregate_record,
    aggregate_revision_one,
    approval_record,
    broker_reference_record,
    command_record,
    failure_record,
    idempotency_record,
    receipt_record,
    reconciliation_record,
    transition_record,
)


def _stage_full_success(store: InMemoryExecutionPersistence, symbol: str = "AAPL"):
    uow = store.unit_of_work()
    uow.commands.register(command_record(symbol))
    uow.idempotency.reserve(idempotency_record(symbol))
    uow.aggregates.save(
        aggregate_record(symbol), expected_revision=PaperExecutionRevision.initial()
    )
    uow.transitions.append(transition_record(symbol))
    uow.broker_references.register(broker_reference_record(symbol))
    uow.receipts.record(receipt_record(symbol))
    uow.failures.record(failure_record(symbol))
    uow.approvals.record(approval_record(symbol))
    uow.reconciliations.record(reconciliation_record(symbol))
    return uow


def test_all_record_success_commits_atomically() -> None:
    store = InMemoryExecutionPersistence()
    result = _stage_full_success(store).commit()
    snapshot = store.snapshot()

    assert result.committed is True
    assert len(snapshot.command_records()) == 1
    assert len(snapshot.idempotency_records()) == 1
    assert len(snapshot.aggregate_records()) == 1
    assert len(snapshot.transition_records()) == 1
    assert len(snapshot.broker_reference_records()) == 1
    assert len(snapshot.receipt_records()) == 1
    assert len(snapshot.failure_records()) == 1
    assert len(snapshot.approval_records()) == 1
    assert len(snapshot.reconciliation_records()) == 1


def test_command_conflict_rolls_back_all_staged_records() -> None:
    store = InMemoryExecutionPersistence()
    first = store.unit_of_work()
    first.commands.register(command_record())
    first.commit()

    second = store.unit_of_work()
    second.commands.register(command_record(payload={"different": True}))
    second.aggregates.save(
        aggregate_record(), expected_revision=PaperExecutionRevision.initial()
    )
    result = second.commit()

    assert result.status is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
    assert len(store.snapshot().aggregate_records()) == 0
    assert len(store.snapshot().command_records()) == 1


def test_idempotency_conflict_rolls_back_all_staged_records() -> None:
    store = InMemoryExecutionPersistence()
    first = store.unit_of_work()
    first.idempotency.reserve(idempotency_record())
    first.commit()

    second = store.unit_of_work()
    second.idempotency.reserve(
        idempotency_record(
            logical_operation_fingerprint=fingerprint_payload("plo", ("other", "AAPL"))
        )
    )
    second.aggregates.save(
        aggregate_record(), expected_revision=PaperExecutionRevision.initial()
    )
    result = second.commit()

    assert result.status is ExecutionPersistenceResultStatus.IDEMPOTENCY_CONFLICT
    assert len(store.snapshot().aggregate_records()) == 0
    assert len(store.snapshot().idempotency_records()) == 1


def test_stale_revision_rolls_back_all_staged_records() -> None:
    store = InMemoryExecutionPersistence()
    setup = store.unit_of_work()
    setup.aggregates.save(
        aggregate_record(), expected_revision=PaperExecutionRevision.initial()
    )
    setup.commit()

    stale = store.unit_of_work()
    stale.commands.register(command_record("MSFT"))
    stale.aggregates.save(
        aggregate_revision_one(), expected_revision=PaperExecutionRevision.initial()
    )
    winner = store.unit_of_work()
    winner.aggregates.save(
        aggregate_revision_one(), expected_revision=PaperExecutionRevision.initial()
    )
    winner.commit()
    result = stale.commit()

    assert result.status is ExecutionPersistenceResultStatus.STALE_REVISION
    assert len(store.snapshot().command_records()) == 0


def test_transition_conflict_rolls_back_all_staged_records() -> None:
    store = InMemoryExecutionPersistence()
    first = store.unit_of_work()
    first.transitions.append(transition_record())
    first.commit()

    second = store.unit_of_work()
    second.commands.register(command_record("MSFT"))
    second.transitions.append(transition_record(safe_reason_code="DIFFERENT_REASON"))
    result = second.commit()

    assert result.status is ExecutionPersistenceResultStatus.TRANSACTION_ABORTED
    assert len(store.snapshot().command_records()) == 0
    assert len(store.snapshot().transition_records()) == 1


def test_broker_reference_conflict_rolls_back_all_staged_records() -> None:
    from test_execution_persistence_in_memory_repositories import aggregate_id

    store = InMemoryExecutionPersistence()
    first = store.unit_of_work()
    first.broker_references.register(broker_reference_record())
    first.commit()

    second = store.unit_of_work()
    second.commands.register(command_record("MSFT"))
    second.broker_references.register(
        broker_reference_record(aggregate_id=aggregate_id("MSFT"))
    )
    result = second.commit()

    assert result.status is ExecutionPersistenceResultStatus.DUPLICATE_BROKER_REFERENCE
    assert len(store.snapshot().command_records()) == 0


def test_active_broker_reference_conflict_rolls_back_all_staged_records() -> None:
    store = InMemoryExecutionPersistence()
    first = store.unit_of_work()
    original = broker_reference_record()
    first.broker_references.register(original)
    first.commit()

    second = store.unit_of_work()
    second.commands.register(command_record("MSFT"))
    second.broker_references.register(
        broker_reference_record(
            "MSFT",
            aggregate_id=original.aggregate_id,
            command_id=original.command_id,
        )
    )
    result = second.commit()

    assert result.status is ExecutionPersistenceResultStatus.DUPLICATE_BROKER_REFERENCE
    assert len(store.snapshot().command_records()) == 0
    assert len(store.snapshot().broker_reference_records()) == 1


@pytest.mark.parametrize(
    ("repository_name", "record_factory", "snapshot_method"),
    [
        ("receipts", receipt_record, "receipt_records"),
        ("failures", failure_record, "failure_records"),
    ],
)
def test_fact_content_conflict_rolls_back_all_staged_records(
    repository_name, record_factory, snapshot_method
) -> None:
    store = InMemoryExecutionPersistence()
    first = store.unit_of_work()
    getattr(first, repository_name).record(record_factory())
    first.commit()

    second = store.unit_of_work()
    second.commands.register(command_record("MSFT"))
    getattr(second, repository_name).record(record_factory(recorded_at=LATER))
    result = second.commit()

    assert result.status is ExecutionPersistenceResultStatus.TRANSACTION_ABORTED
    assert len(store.snapshot().command_records()) == 0
    assert len(getattr(store.snapshot(), snapshot_method)()) == 1


@pytest.mark.parametrize(
    ("repository_name", "original", "conflicting", "snapshot_method"),
    [
        (
            "approvals",
            approval_record(),
            approval_record(
                bound_fingerprint=fingerprint_payload("pcf", ("other", "approval"))
            ),
            "approval_records",
        ),
        (
            "reconciliations",
            reconciliation_record(),
            reconciliation_record(safe_reason_code="DIFFERENT_REASON"),
            "reconciliation_records",
        ),
    ],
)
def test_reference_content_conflict_rolls_back_all_staged_records(
    repository_name, original, conflicting, snapshot_method
) -> None:
    store = InMemoryExecutionPersistence()
    first = store.unit_of_work()
    getattr(first, repository_name).record(original)
    first.commit()

    second = store.unit_of_work()
    second.commands.register(command_record("MSFT"))
    getattr(second, repository_name).record(conflicting)
    result = second.commit()

    assert result.status is ExecutionPersistenceResultStatus.TRANSACTION_ABORTED
    assert len(store.snapshot().command_records()) == 0
    assert len(getattr(store.snapshot(), snapshot_method)()) == 1


def test_explicit_rollback_of_full_stage_leaves_no_partial_records() -> None:
    store = InMemoryExecutionPersistence()
    uow = _stage_full_success(store)

    uow.rollback()

    snapshot = store.snapshot()
    assert snapshot.aggregate_records() == ()
    assert snapshot.command_records() == ()
    assert snapshot.transition_records() == ()
