from __future__ import annotations

from volcanoes.application.execution import (
    ExecutionPersistenceResultStatus,
    InMemoryExecutionPersistence,
    PaperExecutionRevision,
)
from test_execution_persistence_in_memory_repositories import (
    aggregate_id,
    aggregate_record,
    aggregate_revision_one,
    broker_reference_record,
    transition_record,
)


def test_first_commit_wins_for_same_expected_revision() -> None:
    store = InMemoryExecutionPersistence()
    setup = store.unit_of_work()
    setup.aggregates.save(
        aggregate_record(), expected_revision=PaperExecutionRevision.initial()
    )
    setup.commit()

    first = store.unit_of_work()
    second = store.unit_of_work()
    first.aggregates.save(
        aggregate_revision_one(), expected_revision=PaperExecutionRevision.initial()
    )
    second.aggregates.save(
        aggregate_revision_one(last_transition_id="transition-B"),
        expected_revision=PaperExecutionRevision.initial(),
    )

    assert first.commit().committed is True
    result = second.commit()

    assert result.status is ExecutionPersistenceResultStatus.STALE_REVISION
    assert store.snapshot().aggregate_records()[
        0
    ].execution_revision == PaperExecutionRevision(1)


def test_competing_transition_identity_second_commit_aborts_without_partial_state() -> (
    None
):
    store = InMemoryExecutionPersistence()
    first = store.unit_of_work()
    second = store.unit_of_work()
    first.transitions.append(transition_record())
    second.transitions.append(transition_record(safe_reason_code="DIFFERENT_REASON"))

    assert first.commit().committed is True
    result = second.commit()

    assert result.status is ExecutionPersistenceResultStatus.TRANSACTION_ABORTED
    assert len(store.snapshot().transition_records()) == 1


def test_competing_command_identity_second_commit_aborts_without_partial_state() -> (
    None
):
    from test_execution_persistence_in_memory_repositories import command_record

    store = InMemoryExecutionPersistence()
    first = store.unit_of_work()
    second = store.unit_of_work()
    first.commands.register(command_record())
    second.commands.register(command_record(payload={"different": True}))

    assert first.commit().committed is True
    result = second.commit()

    assert result.status is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
    assert len(store.snapshot().command_records()) == 1


def test_competing_idempotency_second_commit_aborts_without_partial_state() -> None:
    from volcanoes.application.execution.fingerprints import fingerprint_payload
    from test_execution_persistence_in_memory_repositories import idempotency_record

    store = InMemoryExecutionPersistence()
    first = store.unit_of_work()
    second = store.unit_of_work()
    first.idempotency.reserve(idempotency_record())
    second.idempotency.reserve(
        idempotency_record(
            logical_operation_fingerprint=fingerprint_payload("plo", ("other", "AAPL"))
        )
    )

    assert first.commit().committed is True
    result = second.commit()

    assert result.status is ExecutionPersistenceResultStatus.IDEMPOTENCY_CONFLICT
    assert len(store.snapshot().idempotency_records()) == 1


def test_competing_broker_reference_second_commit_aborts_without_partial_state() -> (
    None
):
    store = InMemoryExecutionPersistence()
    first = store.unit_of_work()
    second = store.unit_of_work()
    first.broker_references.register(broker_reference_record())
    second.broker_references.register(
        broker_reference_record(aggregate_id=aggregate_id("MSFT"))
    )

    assert first.commit().committed is True
    result = second.commit()

    assert result.status is ExecutionPersistenceResultStatus.DUPLICATE_BROKER_REFERENCE
    assert len(store.snapshot().broker_reference_records()) == 1


def test_commit_order_deterministically_selects_winner() -> None:
    store = InMemoryExecutionPersistence()
    setup = store.unit_of_work()
    setup.aggregates.save(
        aggregate_record(), expected_revision=PaperExecutionRevision.initial()
    )
    setup.commit()

    first = store.unit_of_work()
    second = store.unit_of_work()
    first.aggregates.save(
        aggregate_revision_one(last_transition_id="transition-first"),
        expected_revision=PaperExecutionRevision.initial(),
    )
    second.aggregates.save(
        aggregate_revision_one(last_transition_id="transition-second"),
        expected_revision=PaperExecutionRevision.initial(),
    )

    second.commit()
    first_result = first.commit()

    assert first_result.status is ExecutionPersistenceResultStatus.STALE_REVISION
    assert (
        store.snapshot().aggregate_records()[0].last_transition_id
        == "transition-second"
    )
