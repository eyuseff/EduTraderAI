from __future__ import annotations

from dataclasses import replace

from volcanoes.application.execution import ExecutionPersistenceResultStatus
from volcanoes.infrastructure.execution_persistence.sqlite import (
    open_sqlite_execution_connection,
)
from volcanoes.infrastructure.execution_persistence.sqlite.repositories import (
    SqliteExecutionReconciliationRepository,
)
from volcanoes.infrastructure.execution_persistence.sqlite.unit_of_work import (
    _SqliteExecutionTransaction,
)
from test_f6b_adversarial_reconciliation_validation import (
    _database,
    _reconciliation,
    _seed_aggregate,
)


def test_connection_loss_before_commit_rolls_back_reconciliation(tmp_path) -> None:
    path, connection = _database(tmp_path)
    _seed_aggregate(connection)
    record = _reconciliation()

    transaction = _SqliteExecutionTransaction(connection)
    transaction.__enter__()
    created = SqliteExecutionReconciliationRepository(transaction).record(record)
    assert created.status is ExecutionPersistenceResultStatus.CREATED

    # Simulate process/connection loss before the transaction can commit.
    connection.close()

    reopened = open_sqlite_execution_connection(path)
    with _SqliteExecutionTransaction(reopened) as verification:
        assert (
            SqliteExecutionReconciliationRepository(verification).load_record(
                record.reconciliation_id
            )
            is None
        )
        verification.rollback()
    reopened.close()


def test_committed_reconciliation_survives_restart_as_exact_replay(tmp_path) -> None:
    path, connection = _database(tmp_path)
    _seed_aggregate(connection)
    record = _reconciliation()

    with _SqliteExecutionTransaction(connection) as transaction:
        repository = SqliteExecutionReconciliationRepository(transaction)
        assert repository.record(record).status is ExecutionPersistenceResultStatus.CREATED
        assert transaction.commit().committed is True
    connection.close()

    reopened = open_sqlite_execution_connection(path)
    with _SqliteExecutionTransaction(reopened) as transaction:
        repository = SqliteExecutionReconciliationRepository(transaction)
        assert repository.load_record(record.reconciliation_id) == record
        assert (
            repository.record(record).status
            is ExecutionPersistenceResultStatus.EXACT_REPLAY
        )
        transaction.rollback()
    reopened.close()


def test_conflicting_reconciliation_in_same_transaction_rolls_back_first_write(
    tmp_path,
) -> None:
    path, connection = _database(tmp_path)
    _seed_aggregate(connection)
    record = _reconciliation()
    conflicting = replace(record, safe_reason_code="CONFLICTING_RECONCILIATION_EVIDENCE")

    with _SqliteExecutionTransaction(connection) as transaction:
        repository = SqliteExecutionReconciliationRepository(transaction)
        assert repository.record(record).status is ExecutionPersistenceResultStatus.CREATED
        conflict = repository.record(conflicting)
        assert conflict.status is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
        assert conflict.conflict is not None
        assert conflict.conflict.code == "RECONCILIATION_CONFLICT"
        assert (
            transaction.commit().status
            is ExecutionPersistenceResultStatus.TRANSACTION_ABORTED
        )
    connection.close()

    reopened = open_sqlite_execution_connection(path)
    with _SqliteExecutionTransaction(reopened) as verification:
        assert (
            SqliteExecutionReconciliationRepository(verification).load_record(
                record.reconciliation_id
            )
            is None
        )
        verification.rollback()
    reopened.close()


def test_fault_before_reconciliation_insert_leaves_no_durable_history(
    tmp_path, monkeypatch
) -> None:
    path, connection = _database(tmp_path)
    _seed_aggregate(connection)
    record = _reconciliation()
    original = _SqliteExecutionTransaction.execute

    def injected(self, sql, parameters=()):
        if "INSERT INTO execution_reconciliations" in sql:
            raise RuntimeError("injected reconciliation write failure")
        return original(self, sql, parameters)

    monkeypatch.setattr(_SqliteExecutionTransaction, "execute", injected)
    transaction = _SqliteExecutionTransaction(connection)
    transaction.__enter__()
    try:
        try:
            SqliteExecutionReconciliationRepository(transaction).record(record)
        except RuntimeError as exc:
            assert str(exc) == "injected reconciliation write failure"
        else:
            raise AssertionError("fault injection did not fire")
        transaction.rollback()
    finally:
        connection.close()

    reopened = open_sqlite_execution_connection(path)
    with _SqliteExecutionTransaction(reopened) as verification:
        assert (
            SqliteExecutionReconciliationRepository(verification).load_record(
                record.reconciliation_id
            )
            is None
        )
        verification.rollback()
    reopened.close()
