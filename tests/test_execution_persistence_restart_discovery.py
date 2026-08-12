from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from volcanoes.application.execution import (
    ExecutionAggregateRecord,
    ExecutionRestartDiscoveryQuery,
    PaperExecutionAggregateId,
    PaperExecutionCorrelationId,
    PaperExecutionLifecycleState,
    PaperExecutionRevision,
    RestartDiscoveryResult,
)
from volcanoes.application.execution.persistence.errors import (
    ExecutionPersistenceInvariantError,
)

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
SCHEMA_VERSION = 1


def aggregate_record(state: PaperExecutionLifecycleState) -> ExecutionAggregateRecord:
    return ExecutionAggregateRecord(
        aggregate_id=PaperExecutionAggregateId.from_seed("aggregate", state.value),
        correlation_id=PaperExecutionCorrelationId.from_seed(
            "correlation", state.value
        ),
        lifecycle_state=state,
        execution_revision=PaperExecutionRevision(4),
        cumulative_filled_quantity=Decimal("0"),
        outcome_unknown=state is PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
        reconciliation_required=(
            state is PaperExecutionLifecycleState.RECONCILIATION_REQUIRED
        ),
        command_terminal=False,
        aggregate_terminal=False,
        last_transition_id="PX-TRN-010",
        created_at=NOW,
        updated_at=NOW,
        schema_version=SCHEMA_VERSION,
    )


def test_restart_query_targets_consequential_states() -> None:
    states = (
        PaperExecutionLifecycleState.DISPATCH_PENDING,
        PaperExecutionLifecycleState.DISPATCHED,
        PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
        PaperExecutionLifecycleState.RECONCILIATION_REQUIRED,
        PaperExecutionLifecycleState.CANCEL_PENDING,
        PaperExecutionLifecycleState.REPLACE_PENDING,
        PaperExecutionLifecycleState.PARTIALLY_FILLED,
    )

    query = ExecutionRestartDiscoveryQuery(
        lifecycle_states=states,
        schema_version=SCHEMA_VERSION,
    )

    assert query.lifecycle_states == states
    assert query.query_fingerprint.startswith("pdq-")


def test_restart_query_is_immutable_and_action_free() -> None:
    query = ExecutionRestartDiscoveryQuery(
        lifecycle_states=(PaperExecutionLifecycleState.DISPATCH_PENDING,),
        schema_version=SCHEMA_VERSION,
        limit=25,
        cursor="cursor-1",
    )

    with pytest.raises(FrozenInstanceError):
        query.limit = 50

    assert not hasattr(query, "recover")
    assert not hasattr(query, "query_broker")


def test_restart_query_rejects_empty_state_filter() -> None:
    with pytest.raises(ExecutionPersistenceInvariantError):
        ExecutionRestartDiscoveryQuery(
            lifecycle_states=(),
            schema_version=SCHEMA_VERSION,
        )


def test_restart_query_rejects_invalid_time_window() -> None:
    with pytest.raises(ExecutionPersistenceInvariantError):
        ExecutionRestartDiscoveryQuery(
            lifecycle_states=(PaperExecutionLifecycleState.DISPATCH_PENDING,),
            minimum_updated_at=NOW,
            maximum_updated_at=NOW - timedelta(seconds=1),
            schema_version=SCHEMA_VERSION,
        )


def test_restart_query_rejects_non_positive_limit() -> None:
    with pytest.raises(ExecutionPersistenceInvariantError):
        ExecutionRestartDiscoveryQuery(
            lifecycle_states=(PaperExecutionLifecycleState.DISPATCH_PENDING,),
            limit=0,
            schema_version=SCHEMA_VERSION,
        )


def test_restart_result_is_immutable_page() -> None:
    query = ExecutionRestartDiscoveryQuery(
        lifecycle_states=(PaperExecutionLifecycleState.OUTCOME_UNKNOWN,),
        schema_version=SCHEMA_VERSION,
    )
    result = RestartDiscoveryResult(
        aggregates=(aggregate_record(PaperExecutionLifecycleState.OUTCOME_UNKNOWN),),
        next_cursor="cursor-2",
        complete=False,
        query_fingerprint=query.query_fingerprint,
        schema_version=SCHEMA_VERSION,
    )

    with pytest.raises(FrozenInstanceError):
        result.complete = True

    assert result.aggregates[0].outcome_unknown is True
    assert result.result_fingerprint.startswith("pdr-")


def test_restart_result_rejects_mutable_record_collection() -> None:
    with pytest.raises(ExecutionPersistenceInvariantError):
        RestartDiscoveryResult(
            aggregates=[aggregate_record(PaperExecutionLifecycleState.DISPATCHED)],
            complete=True,
            schema_version=SCHEMA_VERSION,
        )


def test_restart_result_has_no_automatic_recovery_behavior() -> None:
    result = RestartDiscoveryResult(
        aggregates=(
            aggregate_record(PaperExecutionLifecycleState.RECONCILIATION_REQUIRED),
        ),
        complete=True,
        schema_version=SCHEMA_VERSION,
    )

    assert not hasattr(result, "recover")
    assert not hasattr(result, "call_broker")
    assert not hasattr(result, "dispatch")
