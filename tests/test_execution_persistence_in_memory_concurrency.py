from __future__ import annotations

from dataclasses import replace
import pytest

from volcanoes.application.execution import (
    ExecutionPersistenceResultStatus,
    InMemoryExecutionPersistence,
    PaperBrokerOrderReference,
    PaperExecutionRevision,
    PaperExecutionLifecycleState,
)
from volcanoes.application.execution.persistence import ExecutionDispatchControlRecord
from volcanoes.application.execution.submission import (
    ControlledPaperSubmissionService,
    ControlledSubmissionStatus,
    PaperDispatchObservation,
)
from test_sqlite_execution_persistence_unit_of_work import (
    DISPATCH_NOW,
    _seed_dispatch_authority,
)
from test_execution_persistence_in_memory_repositories import (
    LATER,
    aggregate_id,
    aggregate_record,
    aggregate_revision_one,
    broker_reference_record,
    failure_record,
    receipt_record,
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


def test_broker_reference_conflict_reports_exact_authoritative_owner() -> None:
    store = InMemoryExecutionPersistence()
    owner = broker_reference_record()
    with store.unit_of_work() as first:
        assert (
            first.broker_references.register(owner).status
            is ExecutionPersistenceResultStatus.CREATED
        )
        assert first.commit().committed
    with store.unit_of_work() as second:
        result = second.broker_references.register(
            broker_reference_record(aggregate_id=aggregate_id("MSFT"))
        )
        second.rollback()

    assert result.status is ExecutionPersistenceResultStatus.DUPLICATE_BROKER_REFERENCE
    assert result.conflict is not None
    assert result.conflict.aggregate_id == owner.aggregate_id
    assert result.conflict.command_id == owner.command_id
    assert result.record_fingerprint == owner.record_fingerprint
    assert store.snapshot().broker_reference_records() == (owner,)


def test_competing_active_broker_reference_first_commit_wins() -> None:
    store = InMemoryExecutionPersistence()
    first = store.unit_of_work()
    second = store.unit_of_work()
    original = broker_reference_record()
    competing = broker_reference_record(
        "MSFT",
        aggregate_id=original.aggregate_id,
        command_id=original.command_id,
    )
    first.broker_references.register(original)
    second.broker_references.register(competing)

    assert first.commit().committed is True
    result = second.commit()

    assert result.status is ExecutionPersistenceResultStatus.DUPLICATE_BROKER_REFERENCE
    assert len(store.snapshot().broker_reference_records()) == 1


@pytest.mark.parametrize(
    ("repository_name", "record_factory", "snapshot_method"),
    [
        ("receipts", receipt_record, "receipt_records"),
        ("failures", failure_record, "failure_records"),
    ],
)
def test_competing_fact_wrapper_first_commit_wins(
    repository_name, record_factory, snapshot_method
) -> None:
    store = InMemoryExecutionPersistence()
    first = store.unit_of_work()
    second = store.unit_of_work()
    getattr(first, repository_name).record(record_factory())
    getattr(second, repository_name).record(record_factory(recorded_at=LATER))

    assert first.commit().committed is True
    result = second.commit()

    assert result.status is ExecutionPersistenceResultStatus.TRANSACTION_ABORTED
    assert len(getattr(store.snapshot(), snapshot_method)()) == 1


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


@pytest.mark.parametrize(
    ("enabled", "stop", "legacy"),
    ((False, False, False), (True, True, False), (True, False, True)),
)
def test_coordinated_outcome_revalidates_concurrent_control_authority(
    enabled, stop, legacy
) -> None:
    store = InMemoryExecutionPersistence()
    request = _seed_dispatch_authority(store)

    def effect(order):
        with store.unit_of_work() as competing:
            saved = competing.dispatch_control.save(
                ExecutionDispatchControlRecord(
                    enabled, stop, legacy, 3, DISPATCH_NOW, 4
                ),
                expected_generation=2,
            )
            assert saved.status is ExecutionPersistenceResultStatus.SAVED
            assert competing.commit().committed
        return PaperDispatchObservation(
            request.submission_id,
            PaperBrokerOrderReference("pbr-" + "5" * 64),
            True,
            "ACK",
        )

    result = ControlledPaperSubmissionService(
        store, effect, clock=lambda: DISPATCH_NOW
    ).apply_once(request)
    assert result.status is ControlledSubmissionStatus.OUTCOME_UNKNOWN
    assert result.reason_code == "DURABLE_RECORDING_FAILED"
    state = store.snapshot()
    assert state._dispatch_control is not None
    assert state._dispatch_control.generation == 3
    assert not state._receipts
    assert not state._transitions_by_id
    assert not state._dispatch_resolutions


def test_coordinated_outcome_preserves_concurrent_aggregate_revision_and_state() -> (
    None
):
    store = InMemoryExecutionPersistence()
    request = _seed_dispatch_authority(store)

    def effect(order):
        with store.unit_of_work() as competing:
            current = competing.aggregates.load_record(
                store.snapshot().aggregate_records()[0].aggregate_id
            )
            assert current is not None
            changed = replace(
                current,
                lifecycle_state=PaperExecutionLifecycleState.DISPATCHED,
                execution_revision=current.execution_revision.next(),
                last_transition_id="concurrent-transition",
            )
            saved = competing.aggregates.save(
                changed, expected_revision=current.execution_revision
            )
            assert saved.status is ExecutionPersistenceResultStatus.SAVED
            assert competing.commit().committed
        return PaperDispatchObservation(
            request.submission_id,
            PaperBrokerOrderReference("pbr-" + "5" * 64),
            True,
            "ACK",
        )

    result = ControlledPaperSubmissionService(
        store, effect, clock=lambda: DISPATCH_NOW
    ).apply_once(request)
    assert result.status is ControlledSubmissionStatus.OUTCOME_UNKNOWN
    state = store.snapshot()
    assert (
        state.aggregate_records()[0].lifecycle_state
        is PaperExecutionLifecycleState.DISPATCHED
    )
    assert state.aggregate_records()[0].execution_revision == PaperExecutionRevision(1)
    assert not state._receipts and not state._dispatch_resolutions
