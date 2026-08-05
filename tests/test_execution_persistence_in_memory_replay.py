from __future__ import annotations

from volcanoes.application.execution import (
    ExecutionPersistenceResultStatus,
    InMemoryExecutionPersistence,
    PaperExecutionCommandId,
    PaperExecutionRevision,
)
from volcanoes.application.execution.fingerprints import fingerprint_payload
from test_execution_persistence_in_memory_repositories import (
    aggregate_record,
    command_record,
    idempotency_record,
    transition_record,
)


def test_exact_command_replay_across_units_of_work_does_not_duplicate() -> None:
    store = InMemoryExecutionPersistence()
    first = store.unit_of_work()
    command = command_record()
    first.commands.register(command)
    first.aggregates.save(
        aggregate_record(), expected_revision=PaperExecutionRevision.initial()
    )
    first.transitions.append(transition_record())
    first.commit()

    replay = store.unit_of_work()
    result = replay.commands.register(command)
    replay.commit()

    assert result.status is ExecutionPersistenceResultStatus.EXACT_REPLAY
    assert len(store.snapshot().command_records()) == 1
    assert len(store.snapshot().transition_records()) == 1
    assert (
        store.snapshot().aggregate_records()[0].execution_revision
        == PaperExecutionRevision.initial()
    )


def test_logical_idempotency_replay_preserves_original_reference() -> None:
    store = InMemoryExecutionPersistence()
    first = store.unit_of_work()
    original = idempotency_record(original_result_fingerprint="puw-original")
    first.idempotency.reserve(original)
    first.commit()

    second = store.unit_of_work()
    replay = second.idempotency.reserve(
        idempotency_record(
            command_id=PaperExecutionCommandId.from_seed("command", "second")
        )
    )
    second.commit()

    assert replay.status is ExecutionPersistenceResultStatus.LOGICAL_REPLAY
    assert replay.original_command_id == original.command_id
    assert replay.original_result_fingerprint == "puw-original"
    assert len(store.snapshot().idempotency_records()) == 1


def test_idempotency_conflict_across_units_of_work_does_not_mutate() -> None:
    store = InMemoryExecutionPersistence()
    first = store.unit_of_work()
    first.idempotency.reserve(idempotency_record())
    first.commit()

    second = store.unit_of_work()
    result = second.idempotency.reserve(
        idempotency_record(
            logical_operation_fingerprint=fingerprint_payload("plo", ("other", "AAPL"))
        )
    )

    assert result.status is ExecutionPersistenceResultStatus.IDEMPOTENCY_CONFLICT
    assert (
        second.commit().status is ExecutionPersistenceResultStatus.IDEMPOTENCY_CONFLICT
    )
    assert len(store.snapshot().idempotency_records()) == 1


def test_replay_does_not_increment_aggregate_revision() -> None:
    store = InMemoryExecutionPersistence()
    first = store.unit_of_work()
    first.aggregates.save(
        aggregate_record(), expected_revision=PaperExecutionRevision.initial()
    )
    first.commit()

    replay = store.unit_of_work()
    assert (
        replay.aggregates.save(
            aggregate_record(), expected_revision=PaperExecutionRevision.initial()
        ).status
        is ExecutionPersistenceResultStatus.EXACT_REPLAY
    )
    replay.commit()

    assert (
        store.snapshot().aggregate_records()[0].execution_revision
        == PaperExecutionRevision.initial()
    )


def test_exact_replay_result_is_deterministic() -> None:
    store = InMemoryExecutionPersistence()
    first = store.unit_of_work()
    command = command_record()
    first.commands.register(command)
    first.commit()

    replay_a = store.unit_of_work().commands.register(command)
    replay_b = store.unit_of_work().commands.register(command)

    assert replay_a.to_primitive() == replay_b.to_primitive()
