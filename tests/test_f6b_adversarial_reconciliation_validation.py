from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from volcanoes.application.execution import (
    ExecutionAggregateRecord,
    ExecutionPersistenceResultStatus,
    ExecutionReconciliationRecord,
    ExecutionReconciliationResultClassification,
    PaperExecutionAggregateId,
    PaperExecutionCorrelationId,
    PaperExecutionLifecycleState,
    PaperExecutionMode,
    PaperExecutionRevision,
)
from volcanoes.infrastructure.execution_persistence.sqlite import (
    CURRENT_SCHEMA_VERSION,
    KNOWN_MIGRATIONS,
    SqliteExecutionPersistence,
    apply_pending_migrations,
    open_sqlite_execution_connection,
)
from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionBusyError,
    SqliteExecutionSchemaError,
)
from volcanoes.infrastructure.execution_persistence.sqlite.repositories import (
    SqliteExecutionAggregateRepository,
    SqliteExecutionReconciliationRepository,
)
from volcanoes.infrastructure.execution_persistence.sqlite.unit_of_work import (
    _SqliteExecutionTransaction,
)

NOW = datetime(2026, 8, 15, 18, 50, tzinfo=UTC)


def _database(tmp_path):
    path = tmp_path / "f6b-adversarial.sqlite"
    connection = open_sqlite_execution_connection(path)
    apply_pending_migrations(
        connection,
        KNOWN_MIGRATIONS,
        applied_at=NOW,
        application_version="f6b-adversarial-test",
    )
    return path, connection


def _aggregate() -> ExecutionAggregateRecord:
    return ExecutionAggregateRecord(
        aggregate_id=PaperExecutionAggregateId.from_seed("f6b", "aggregate"),
        correlation_id=PaperExecutionCorrelationId.from_seed("f6b", "correlation"),
        lifecycle_state=PaperExecutionLifecycleState.RECONCILIATION_REQUIRED,
        execution_revision=PaperExecutionRevision(7),
        cumulative_filled_quantity=Decimal("0"),
        requested_quantity=Decimal("1"),
        outcome_unknown=True,
        reconciliation_required=True,
        command_terminal=False,
        aggregate_terminal=False,
        last_transition_id="f6b-transition-7",
        created_at=NOW,
        updated_at=NOW,
        schema_version=CURRENT_SCHEMA_VERSION,
        mode=PaperExecutionMode.PAPER,
    )


def _reconciliation(reason: str = "BROKER_ORDER_MISSING_LOCALLY") -> ExecutionReconciliationRecord:
    return ExecutionReconciliationRecord(
        reconciliation_id="recon-f6b-adversarial-0001",
        aggregate_id=_aggregate().aggregate_id,
        starting_local_revision=PaperExecutionRevision(7),
        starting_lifecycle_state=PaperExecutionLifecycleState.RECONCILIATION_REQUIRED,
        broker_observation_references=("prf-adversarial-evidence",),
        result_classification=ExecutionReconciliationResultClassification.MISSING_LOCALLY,
        operator_action_required=True,
        unresolved=False,
        safe_reason_code=reason,
        recorded_at=NOW,
        schema_version=CURRENT_SCHEMA_VERSION,
    )


def _seed_aggregate(connection) -> None:
    with _SqliteExecutionTransaction(connection) as transaction:
        saved = SqliteExecutionAggregateRepository(transaction).save(
            _aggregate(),
            expected_revision=PaperExecutionRevision.initial(),
        )
        assert saved.status is ExecutionPersistenceResultStatus.CREATED
        assert transaction.commit().committed is True


def test_reconciliation_rollback_leaves_no_partial_history(tmp_path) -> None:
    _, connection = _database(tmp_path)
    _seed_aggregate(connection)
    record = _reconciliation()

    with _SqliteExecutionTransaction(connection) as transaction:
        created = SqliteExecutionReconciliationRepository(transaction).record(record)
        assert created.status is ExecutionPersistenceResultStatus.CREATED
        transaction.rollback()

    with _SqliteExecutionTransaction(connection) as transaction:
        assert SqliteExecutionReconciliationRepository(transaction).load_record(
            record.reconciliation_id
        ) is None
        transaction.rollback()
    connection.close()


def test_reconciliation_restart_replays_exact_record_without_mutation(tmp_path) -> None:
    path, connection = _database(tmp_path)
    _seed_aggregate(connection)
    record = _reconciliation()

    with _SqliteExecutionTransaction(connection) as transaction:
        created = SqliteExecutionReconciliationRepository(transaction).record(record)
        assert created.status is ExecutionPersistenceResultStatus.CREATED
        assert transaction.commit().committed is True
    connection.close()

    reopened = open_sqlite_execution_connection(path)
    persistence = SqliteExecutionPersistence(reopened)
    with persistence.unit_of_work() as unit:
        repository = unit.reconciliations
        assert repository.load_record(record.reconciliation_id) == record
        replay = repository.record(record)
        assert replay.status is ExecutionPersistenceResultStatus.EXACT_REPLAY
        unit.rollback()
    reopened.close()


def test_second_writer_fails_closed_while_first_transaction_holds_lock(tmp_path) -> None:
    path, first = _database(tmp_path)
    second = open_sqlite_execution_connection(path)

    first_tx = _SqliteExecutionTransaction(first)
    first_tx.__enter__()
    try:
        with pytest.raises(SqliteExecutionBusyError):
            with _SqliteExecutionTransaction(second):
                pass
    finally:
        first_tx.rollback()
        first.close()
        second.close()


def test_reconciliation_history_rejects_update_and_delete(tmp_path) -> None:
    _, connection = _database(tmp_path)
    _seed_aggregate(connection)
    record = _reconciliation()
    with _SqliteExecutionTransaction(connection) as transaction:
        assert (
            SqliteExecutionReconciliationRepository(transaction).record(record).status
            is ExecutionPersistenceResultStatus.CREATED
        )
        assert transaction.commit().committed is True

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "UPDATE execution_reconciliations SET safe_reason_code = ? WHERE reconciliation_id = ?",
            ("TAMPERED", record.reconciliation_id),
        )
    connection.rollback()
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "DELETE FROM execution_reconciliations WHERE reconciliation_id = ?",
            (record.reconciliation_id,),
        )
    connection.rollback()
    connection.close()


def test_schema_tamper_blocks_persistence_reopen(tmp_path) -> None:
    path, connection = _database(tmp_path)
    connection.close()

    tamper = sqlite3.connect(path)
    tamper.execute("DROP TRIGGER trg_execution_reconciliations_no_update")
    tamper.commit()
    tamper.close()

    reopened = open_sqlite_execution_connection(path)
    try:
        with pytest.raises(SqliteExecutionSchemaError):
            SqliteExecutionPersistence(reopened)
    finally:
        reopened.close()
