from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from volcanoes.application.execution import (
    ExecutionAggregateRecord,
    ExecutionCommandProcessingOutcome,
    ExecutionCommandRecord,
    ExecutionIdempotencyRecord,
    ExecutionIdempotencyReservationStatus,
    ExecutionPersistenceResultStatus,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionIdempotencyKey,
    PaperExecutionLifecycleState,
    PaperExecutionMode,
    PaperExecutionOperation,
    PaperExecutionRevision,
)
from volcanoes.application.execution.fingerprints import fingerprint_payload
from volcanoes.infrastructure.execution_persistence.sqlite import (
    KNOWN_MIGRATIONS,
    apply_pending_migrations,
    open_sqlite_execution_connection,
)
from volcanoes.infrastructure.execution_persistence.sqlite.repositories import (
    SqliteExecutionAggregateRepository,
    SqliteExecutionCommandRepository,
    SqliteExecutionIdempotencyRepository,
)
from volcanoes.infrastructure.execution_persistence.sqlite.unit_of_work import (
    _SqliteExecutionTransaction,
)

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def _aggregate(symbol: str = "AAPL", **overrides: object) -> ExecutionAggregateRecord:
    values: dict[str, object] = {
        "aggregate_id": PaperExecutionAggregateId.from_seed("aggregate", symbol),
        "correlation_id": PaperExecutionCorrelationId.from_seed("correlation", symbol),
        "lifecycle_state": PaperExecutionLifecycleState.CREATED,
        "execution_revision": PaperExecutionRevision.initial(),
        "cumulative_filled_quantity": Decimal("0"),
        "requested_quantity": Decimal("1"),
        "outcome_unknown": False,
        "reconciliation_required": False,
        "command_terminal": False,
        "aggregate_terminal": False,
        "last_transition_id": f"transition-{symbol}-0",
        "created_at": NOW,
        "updated_at": NOW,
        "schema_version": 3,
        "mode": PaperExecutionMode.PAPER,
    }
    values.update(overrides)
    return ExecutionAggregateRecord(**values)


def _command(symbol: str = "AAPL", **overrides: object) -> ExecutionCommandRecord:
    values: dict[str, object] = {
        "command_id": PaperExecutionCommandId.from_seed("command", symbol),
        "aggregate_id": PaperExecutionAggregateId.from_seed("aggregate", symbol),
        "correlation_id": PaperExecutionCorrelationId.from_seed("correlation", symbol),
        "idempotency_key": PaperExecutionIdempotencyKey.from_seed(
            "idempotency", symbol
        ),
        "operation": PaperExecutionOperation.SUBMIT,
        "expected_execution_revision": PaperExecutionRevision.initial(),
        "canonical_payload_fingerprint": fingerprint_payload(
            "pcf", ("payload", symbol)
        ),
        "canonical_command_json": '{"operation":"SUBMIT"}',
        "approval_fingerprint": fingerprint_payload("pap", ("approval", symbol)),
        "policy_fingerprint": fingerprint_payload("pps", ("policy", symbol)),
        "received_at": NOW,
        "processing_outcome": ExecutionCommandProcessingOutcome.ACCEPTED,
        "schema_version": 3,
    }
    values.update(overrides)
    return ExecutionCommandRecord(**values)


def _idempotency(
    symbol: str = "AAPL", **overrides: object
) -> ExecutionIdempotencyRecord:
    values: dict[str, object] = {
        "idempotency_key": PaperExecutionIdempotencyKey.from_seed(
            "idempotency", symbol
        ),
        "logical_operation_fingerprint": fingerprint_payload(
            "plo", ("operation", symbol)
        ),
        "command_id": PaperExecutionCommandId.from_seed("command", symbol),
        "aggregate_id": PaperExecutionAggregateId.from_seed("aggregate", symbol),
        "reservation_status": ExecutionIdempotencyReservationStatus.RESERVED,
        "created_at": NOW,
        "schema_version": 3,
    }
    values.update(overrides)
    return ExecutionIdempotencyRecord(**values)


def _connection(tmp_path):
    connection = open_sqlite_execution_connection(tmp_path / "execution.sqlite")
    apply_pending_migrations(
        connection,
        KNOWN_MIGRATIONS,
        applied_at=NOW,
        application_version="test",
    )
    return connection


def test_aggregate_round_trip_uses_canonical_v003_values(tmp_path) -> None:
    connection = _connection(tmp_path)
    aggregate = _aggregate()

    with _SqliteExecutionTransaction(connection) as transaction:
        result = SqliteExecutionAggregateRepository(transaction).save(
            aggregate,
            expected_revision=PaperExecutionRevision.initial(),
        )
        assert result.status is ExecutionPersistenceResultStatus.CREATED
        assert transaction.commit().committed is True

    with _SqliteExecutionTransaction(connection) as transaction:
        loaded = SqliteExecutionAggregateRepository(transaction).load_record(
            aggregate.aggregate_id
        )
        assert loaded == aggregate
        transaction.rollback()
    connection.close()


def test_command_exact_replay_and_conflict_are_non_mutating(tmp_path) -> None:
    connection = _connection(tmp_path)
    aggregate = _aggregate()
    command = _command()

    with _SqliteExecutionTransaction(connection) as transaction:
        aggregates = SqliteExecutionAggregateRepository(transaction)
        commands = SqliteExecutionCommandRepository(transaction)
        aggregates.save(aggregate, expected_revision=PaperExecutionRevision.initial())
        assert (
            commands.register(command).status
            is ExecutionPersistenceResultStatus.CREATED
        )
        assert transaction.commit().committed is True

    with _SqliteExecutionTransaction(connection) as transaction:
        commands = SqliteExecutionCommandRepository(transaction)
        assert (
            commands.register(command).status
            is ExecutionPersistenceResultStatus.EXACT_REPLAY
        )
        assert transaction.commit().committed is True

    conflicting = _command(
        canonical_payload_fingerprint=fingerprint_payload("pcf", ("payload", "MSFT"))
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        result = SqliteExecutionCommandRepository(transaction).register(conflicting)
        assert result.status is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
        assert transaction.commit().committed is False
        assert transaction._rolled_back is True
    assert (
        connection.execute("SELECT count(*) FROM execution_commands").fetchone()[0] == 1
    )
    connection.close()


def test_idempotency_replay_and_conflict_are_revision_neutral(tmp_path) -> None:
    connection = _connection(tmp_path)
    aggregate = _aggregate()
    command = _command()
    reservation = _idempotency()

    with _SqliteExecutionTransaction(connection) as transaction:
        SqliteExecutionAggregateRepository(transaction).save(
            aggregate, expected_revision=PaperExecutionRevision.initial()
        )
        SqliteExecutionCommandRepository(transaction).register(command)
        assert (
            SqliteExecutionIdempotencyRepository(transaction)
            .reserve(reservation)
            .status
            is ExecutionPersistenceResultStatus.CREATED
        )
        assert transaction.commit().committed is True

    with _SqliteExecutionTransaction(connection) as transaction:
        result = SqliteExecutionIdempotencyRepository(transaction).reserve(reservation)
        assert result.status is ExecutionPersistenceResultStatus.LOGICAL_REPLAY
        assert transaction.commit().committed is True

    conflicting = _idempotency(
        logical_operation_fingerprint=fingerprint_payload("plo", ("operation", "MSFT"))
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        result = SqliteExecutionIdempotencyRepository(transaction).reserve(conflicting)
        assert result.status is ExecutionPersistenceResultStatus.IDEMPOTENCY_CONFLICT
        assert transaction.commit().committed is False
    assert (
        connection.execute("SELECT count(*) FROM execution_idempotency").fetchone()[0]
        == 1
    )
    connection.close()


def test_aggregate_cas_rejects_stale_update_without_mutation(tmp_path) -> None:
    connection = _connection(tmp_path)
    original = _aggregate()
    revised = _aggregate(
        lifecycle_state=PaperExecutionLifecycleState.ELIGIBILITY_EVALUATED,
        execution_revision=PaperExecutionRevision(1),
        last_transition_id="transition-AAPL-1",
        updated_at=NOW + timedelta(seconds=1),
    )

    with _SqliteExecutionTransaction(connection) as transaction:
        SqliteExecutionAggregateRepository(transaction).save(
            original, expected_revision=PaperExecutionRevision.initial()
        )
        transaction.commit()

    with _SqliteExecutionTransaction(connection) as transaction:
        result = SqliteExecutionAggregateRepository(transaction).save(
            revised,
            expected_revision=PaperExecutionRevision(1),
        )
        assert result.status is ExecutionPersistenceResultStatus.STALE_REVISION
        assert transaction.commit().committed is False

    with _SqliteExecutionTransaction(connection) as transaction:
        assert (
            SqliteExecutionAggregateRepository(transaction).load_record(
                original.aggregate_id
            )
            == original
        )
        transaction.rollback()
    connection.close()
