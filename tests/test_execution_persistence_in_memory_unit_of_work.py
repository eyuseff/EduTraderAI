from __future__ import annotations

import pytest

from volcanoes.application.execution import (
    ExecutionPersistenceResultStatus,
    InMemoryExecutionPersistence,
    InMemoryUnitOfWorkClosedError,
    PaperExecutionRevision,
)
from volcanoes.application.execution.persistence import RecordLoadResult
from volcanoes.application.execution.persistence.in_memory.repositories import (
    InMemoryExecutionAggregateRepository,
    InMemoryExecutionBrokerReferenceRepository,
    InMemoryExecutionDispatchResolutionRepository,
    InMemoryExecutionReceiptRepository,
    InMemoryExecutionTransitionJournal,
)
from volcanoes.application.execution.persistence.in_memory.unit_of_work import (
    InMemoryExecutionUnitOfWork,
)
from volcanoes.application.execution.submission import (
    ControlledPaperSubmissionService,
    PaperDispatchObservation,
)
from volcanoes.application.execution import PaperBrokerOrderReference
from test_sqlite_execution_persistence_unit_of_work import (
    DISPATCH_NOW,
    _seed_dispatch_authority,
)
from test_execution_persistence_in_memory_repositories import (
    aggregate_id,
    aggregate_record,
    aggregate_revision_one,
    command_record,
    idempotency_record,
    receipt_record,
    transition_record,
)


def test_staged_changes_are_invisible_before_commit() -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()

    uow.aggregates.save(
        aggregate_record(), expected_revision=PaperExecutionRevision.initial()
    )

    assert store.snapshot().aggregate_records() == ()
    assert (
        uow.aggregates.get(aggregate_id()).status
        is ExecutionPersistenceResultStatus.LOADED
    )


def test_commit_makes_staged_changes_visible() -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    uow.aggregates.save(
        aggregate_record(), expected_revision=PaperExecutionRevision.initial()
    )

    result = uow.commit()

    assert result.committed is True
    assert len(store.snapshot().aggregate_records()) == 1


def test_explicit_rollback_discards_staged_changes() -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    uow.aggregates.save(
        aggregate_record(), expected_revision=PaperExecutionRevision.initial()
    )

    uow.rollback()

    assert store.snapshot().aggregate_records() == ()


def test_context_manager_does_not_auto_commit() -> None:
    store = InMemoryExecutionPersistence()
    with store.unit_of_work() as uow:
        uow.aggregates.save(
            aggregate_record(), expected_revision=PaperExecutionRevision.initial()
        )

    assert store.snapshot().aggregate_records() == ()


def test_context_manager_rolls_back_on_exception() -> None:
    store = InMemoryExecutionPersistence()

    with pytest.raises(RuntimeError):
        with store.unit_of_work() as uow:
            uow.aggregates.save(
                aggregate_record(), expected_revision=PaperExecutionRevision.initial()
            )
            raise RuntimeError("boom")

    assert store.snapshot().aggregate_records() == ()


def test_commit_may_occur_once() -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    uow.aggregates.save(
        aggregate_record(), expected_revision=PaperExecutionRevision.initial()
    )

    assert uow.commit().committed is True
    replay = uow.commit()

    assert replay.status is ExecutionPersistenceResultStatus.EXACT_REPLAY
    assert replay.committed is False


def test_operations_after_commit_are_rejected() -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    uow.commit()

    with pytest.raises(InMemoryUnitOfWorkClosedError):
        uow.aggregates.get(aggregate_id())


def test_operations_after_rollback_are_rejected() -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    uow.rollback()

    with pytest.raises(InMemoryUnitOfWorkClosedError):
        uow.commands.register(command_record())


def test_commit_after_rollback_is_rejected() -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    uow.rollback()

    with pytest.raises(InMemoryUnitOfWorkClosedError):
        uow.commit()


def test_rollback_after_commit_is_documented_noop() -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    uow.aggregates.save(
        aggregate_record(), expected_revision=PaperExecutionRevision.initial()
    )
    uow.commit()

    uow.rollback()

    assert len(store.snapshot().aggregate_records()) == 1


def test_repositories_participate_in_same_transaction() -> None:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    uow.register_command(command_record())
    uow.reserve_idempotency(idempotency_record())
    uow.save_aggregate(
        aggregate_record(), expected_revision=PaperExecutionRevision.initial()
    )
    uow.append_transition(transition_record())
    uow.record_receipt(receipt_record())

    assert uow.commit().committed is True
    snapshot = store.snapshot()
    assert len(snapshot.command_records()) == 1
    assert len(snapshot.idempotency_records()) == 1
    assert len(snapshot.aggregate_records()) == 1
    assert len(snapshot.transition_records()) == 1
    assert len(snapshot.receipt_records()) == 1


def test_failed_commit_closes_transaction_without_partial_state() -> None:
    store = InMemoryExecutionPersistence()
    creator = store.unit_of_work()
    creator.aggregates.save(
        aggregate_record(), expected_revision=PaperExecutionRevision.initial()
    )
    creator.commit()

    stale = store.unit_of_work()
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
    assert len(store.snapshot().aggregate_records()) == 1
    assert store.snapshot().aggregate_records()[
        0
    ].execution_revision == PaperExecutionRevision(1)
    with pytest.raises(InMemoryUnitOfWorkClosedError):
        stale.aggregates.get(aggregate_id())


@pytest.mark.parametrize(
    ("target", "method", "raise_call"),
    (
        (InMemoryExecutionBrokerReferenceRepository, "register", 1),
        (InMemoryExecutionReceiptRepository, "record", 1),
        (InMemoryExecutionTransitionJournal, "append", 1),
        (InMemoryExecutionTransitionJournal, "append", 2),
        (InMemoryExecutionAggregateRepository, "_save_dispatch_outcome", 1),
        (InMemoryExecutionDispatchResolutionRepository, "record", 1),
    ),
)
def test_dispatch_outcome_exception_restores_every_stage_before_later_commit(
    monkeypatch, target, method, raise_call
) -> None:
    store = InMemoryExecutionPersistence()
    request = _seed_dispatch_authority(store)
    captured = []

    def capture(self, write_set):
        captured.append(write_set)
        return RecordLoadResult(ExecutionPersistenceResultStatus.CREATED, 4)

    monkeypatch.setattr(InMemoryExecutionUnitOfWork, "record_dispatch_outcome", capture)
    ControlledPaperSubmissionService(
        store,
        lambda order: PaperDispatchObservation(
            request.submission_id,
            PaperBrokerOrderReference("pbr-" + "5" * 64),
            True,
            "ACK",
        ),
        clock=lambda: DISPATCH_NOW,
    ).apply_once(request)
    assert len(captured) == 1
    monkeypatch.undo()

    original = getattr(target, method)
    calls = 0

    def injected(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == raise_call:
            raise RuntimeError("injected coordinated-outcome failure")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(target, method, injected)
    unit = store.unit_of_work()
    with pytest.raises(RuntimeError, match="injected coordinated-outcome failure"):
        unit.record_dispatch_outcome(captured[0])
    assert unit.commit().committed
    state = store.snapshot()
    assert len(state._dispatch_claims) == 1
    assert len(state._dispatch_authorizations) == 1
    assert not state._broker_references
    assert not state._receipts
    assert not state._transitions_by_id
    assert not state._dispatch_resolutions
    assert state.aggregate_records()[0].lifecycle_state.value == "DISPATCH_PENDING"
