from __future__ import annotations

from datetime import timedelta

from volcanoes.application.execution import (
    ExecutionRestartDiscoveryQuery,
    InMemoryExecutionPersistence,
    PaperExecutionLifecycleState,
    PaperExecutionRevision,
)
from test_execution_persistence_in_memory_repositories import NOW, aggregate_record


def _store_with_states() -> InMemoryExecutionPersistence:
    store = InMemoryExecutionPersistence()
    uow = store.unit_of_work()
    for index, (symbol, state) in enumerate(
        (
            ("AAPL", PaperExecutionLifecycleState.DISPATCH_PENDING),
            ("MSFT", PaperExecutionLifecycleState.DISPATCHED),
            ("NVDA", PaperExecutionLifecycleState.CREATED),
            ("TSLA", PaperExecutionLifecycleState.OUTCOME_UNKNOWN),
        )
    ):
        record = aggregate_record(
            symbol,
            lifecycle_state=state,
            updated_at=NOW + timedelta(minutes=index),
            outcome_unknown=state is PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
            execution_revision=PaperExecutionRevision.initial(),
        )
        uow.aggregates.save(record, expected_revision=PaperExecutionRevision.initial())
    uow.commit()
    return store


def test_restart_discovery_filters_requested_states() -> None:
    store = _store_with_states()
    uow = store.unit_of_work()
    result = uow.restart_discovery.discover(
        ExecutionRestartDiscoveryQuery(
            lifecycle_states=(PaperExecutionLifecycleState.DISPATCH_PENDING,),
            schema_version=1,
        )
    )

    assert len(result.aggregates) == 1
    assert (
        result.aggregates[0].lifecycle_state
        is PaperExecutionLifecycleState.DISPATCH_PENDING
    )


def test_restart_discovery_order_is_deterministic() -> None:
    store = _store_with_states()
    uow = store.unit_of_work()
    result = uow.restart_discovery.discover(
        ExecutionRestartDiscoveryQuery(
            lifecycle_states=(
                PaperExecutionLifecycleState.DISPATCH_PENDING,
                PaperExecutionLifecycleState.DISPATCHED,
                PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
            ),
            schema_version=1,
        )
    )

    assert [record.aggregate_id.value for record in result.aggregates] == sorted(
        record.aggregate_id.value for record in result.aggregates
    )


def test_restart_discovery_limit_and_cursor() -> None:
    store = _store_with_states()
    first = store.unit_of_work().restart_discovery.discover(
        ExecutionRestartDiscoveryQuery(
            lifecycle_states=(
                PaperExecutionLifecycleState.DISPATCH_PENDING,
                PaperExecutionLifecycleState.DISPATCHED,
                PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
            ),
            limit=2,
            schema_version=1,
        )
    )
    second = store.unit_of_work().restart_discovery.discover(
        ExecutionRestartDiscoveryQuery(
            lifecycle_states=(
                PaperExecutionLifecycleState.DISPATCH_PENDING,
                PaperExecutionLifecycleState.DISPATCHED,
                PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
            ),
            cursor=first.next_cursor,
            limit=2,
            schema_version=1,
        )
    )

    assert first.complete is False
    assert first.next_cursor == "cursor-2"
    assert second.complete is True
    assert first.aggregates != second.aggregates


def test_restart_discovery_empty_result_is_complete() -> None:
    store = _store_with_states()
    result = store.unit_of_work().restart_discovery.discover(
        ExecutionRestartDiscoveryQuery(
            lifecycle_states=(PaperExecutionLifecycleState.CANCEL_PENDING,),
            schema_version=1,
        )
    )

    assert result.aggregates == ()
    assert result.complete is True


def test_restart_discovery_does_not_mutate_state() -> None:
    store = _store_with_states()
    before = store.snapshot().aggregate_records()
    store.unit_of_work().restart_discovery.discover(
        ExecutionRestartDiscoveryQuery(
            lifecycle_states=(PaperExecutionLifecycleState.DISPATCH_PENDING,),
            schema_version=1,
        )
    )

    assert store.snapshot().aggregate_records() == before


def test_restart_discovery_time_window_filters() -> None:
    store = _store_with_states()
    result = store.unit_of_work().restart_discovery.discover(
        ExecutionRestartDiscoveryQuery(
            lifecycle_states=(
                PaperExecutionLifecycleState.DISPATCH_PENDING,
                PaperExecutionLifecycleState.DISPATCHED,
                PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
            ),
            minimum_updated_at=NOW + timedelta(minutes=1),
            maximum_updated_at=NOW + timedelta(minutes=2),
            schema_version=1,
        )
    )

    assert all(
        NOW + timedelta(minutes=1) <= record.updated_at <= NOW + timedelta(minutes=2)
        for record in result.aggregates
    )
