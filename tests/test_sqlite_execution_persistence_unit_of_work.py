from __future__ import annotations

import sqlite3

import pytest

from volcanoes.application.execution.persistence.ports import (
    ExecutionAggregateRepository,
    ExecutionApprovalRepository,
    ExecutionBrokerReferenceRepository,
    ExecutionCommandRepository,
    ExecutionFailureRepository,
    ExecutionIdempotencyRepository,
    ExecutionReceiptRepository,
    ExecutionReconciliationRepository,
    ExecutionRestartDiscoveryRepository,
    ExecutionTransitionJournal,
)
from volcanoes.application.execution.persistence.unit_of_work import (
    ExecutionPersistenceSession,
    ExecutionUnitOfWork,
)
from volcanoes.application.execution.persistence.enums import (
    ExecutionPersistenceResultStatus,
)
from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionConfigurationError,
    SqliteExecutionSchemaError,
    SqliteExecutionTransactionError,
)
from volcanoes.infrastructure.execution_persistence.sqlite.unit_of_work import (
    SqliteExecutionPersistence,
    SqliteExecutionUnitOfWork,
    _SqliteExecutionTransaction,
)
from test_execution_persistence_in_memory_repositories import (
    failure_record,
    receipt_record,
)
from test_sqlite_execution_persistence_repositories import (
    _aggregate,
    _command,
    _connection,
    _idempotency,
    _transition,
)


def test_context_exit_rolls_back_without_closing_caller_connection() -> None:
    connection = sqlite3.connect(":memory:", isolation_level=None)
    connection.execute("CREATE TABLE probe (value INTEGER)")

    with _SqliteExecutionTransaction(connection) as transaction:
        transaction.execute("INSERT INTO probe VALUES (1)")

    assert connection.execute("SELECT count(*) FROM probe").fetchone()[0] == 0
    assert connection.execute("SELECT 1").fetchone()[0] == 1
    connection.close()


def test_commit_is_explicit_and_repeated_commit_is_replay() -> None:
    connection = sqlite3.connect(":memory:", isolation_level=None)
    connection.execute("CREATE TABLE probe (value INTEGER)")

    with _SqliteExecutionTransaction(connection) as transaction:
        transaction.execute("INSERT INTO probe VALUES (1)")
        assert transaction.commit().status is ExecutionPersistenceResultStatus.SAVED
        assert (
            transaction.commit().status is ExecutionPersistenceResultStatus.EXACT_REPLAY
        )
        transaction.rollback()

    assert connection.execute("SELECT count(*) FROM probe").fetchone()[0] == 1
    connection.close()


def test_existing_transaction_and_nested_kernel_fail_closed() -> None:
    connection = sqlite3.connect(":memory:", isolation_level=None)
    connection.execute("BEGIN")
    with pytest.raises(SqliteExecutionTransactionError):
        _SqliteExecutionTransaction(connection).__enter__()
    connection.rollback()

    with _SqliteExecutionTransaction(connection):
        with pytest.raises(SqliteExecutionTransactionError):
            _SqliteExecutionTransaction(connection).__enter__()
    connection.close()


def test_public_unit_of_work_implements_both_protocols_and_all_ports(tmp_path) -> None:
    connection = _connection(tmp_path)
    persistence = SqliteExecutionPersistence(connection)
    first = persistence.unit_of_work()
    second = persistence.unit_of_work()

    assert first is not second
    assert isinstance(first, SqliteExecutionUnitOfWork)
    assert isinstance(first, ExecutionUnitOfWork)
    assert isinstance(first, ExecutionPersistenceSession)
    expected_ports = {
        "aggregates": ExecutionAggregateRepository,
        "commands": ExecutionCommandRepository,
        "idempotency": ExecutionIdempotencyRepository,
        "transitions": ExecutionTransitionJournal,
        "broker_references": ExecutionBrokerReferenceRepository,
        "receipts": ExecutionReceiptRepository,
        "failures": ExecutionFailureRepository,
        "approvals": ExecutionApprovalRepository,
        "reconciliations": ExecutionReconciliationRepository,
        "restart_discovery": ExecutionRestartDiscoveryRepository,
    }
    assert set(expected_ports) <= vars(first).keys()
    for name, protocol in expected_ports.items():
        assert isinstance(getattr(first, name), protocol)
    connection.close()


def test_seven_session_methods_delegate_exact_repository_results(tmp_path) -> None:
    connection = _connection(tmp_path)
    aggregate = _aggregate()
    command = _command()
    reservation = _idempotency()
    transition = _transition()
    receipt = receipt_record()
    failure = failure_record()

    with SqliteExecutionPersistence(connection).unit_of_work() as unit:
        aggregate_result = unit.save_aggregate(
            aggregate, expected_revision=aggregate.execution_revision
        )
        command_result = unit.register_command(command)
        idempotency_result = unit.reserve_idempotency(reservation)
        load_result = unit.load_aggregate(aggregate)
        transition_result = unit.append_transition(transition)
        receipt_result = unit.record_receipt(receipt)
        failure_result = unit.record_failure(failure)
        assert (
            aggregate_result.status,
            aggregate_result.aggregate_fingerprint,
        ) == (ExecutionPersistenceResultStatus.CREATED, aggregate.record_fingerprint)
        assert (command_result.status, command_result.command_fingerprint) == (
            ExecutionPersistenceResultStatus.CREATED,
            command.record_fingerprint,
        )
        assert (
            idempotency_result.status,
            idempotency_result.reservation_fingerprint,
        ) == (
            ExecutionPersistenceResultStatus.CREATED,
            reservation.record_fingerprint,
        )
        assert (load_result.status, load_result.record_fingerprint) == (
            ExecutionPersistenceResultStatus.LOADED,
            aggregate.record_fingerprint,
        )
        assert (
            transition_result.status,
            transition_result.transition_fingerprint,
        ) == (
            ExecutionPersistenceResultStatus.APPENDED,
            transition.record_fingerprint,
        )
        assert (receipt_result.status, receipt_result.record_fingerprint) == (
            ExecutionPersistenceResultStatus.CREATED,
            receipt.record_fingerprint,
        )
        assert (failure_result.status, failure_result.record_fingerprint) == (
            ExecutionPersistenceResultStatus.CREATED,
            failure.record_fingerprint,
        )
        assert unit.commit().committed is True

    assert (
        connection.execute("SELECT count(*) FROM execution_commands").fetchone()[0] == 1
    )
    assert (
        connection.execute("SELECT count(*) FROM execution_idempotency").fetchone()[0]
        == 1
    )
    assert (
        connection.execute("SELECT count(*) FROM execution_aggregates").fetchone()[0]
        == 1
    )
    assert (
        connection.execute("SELECT count(*) FROM execution_transitions").fetchone()[0]
        == 1
    )
    assert (
        connection.execute("SELECT count(*) FROM execution_receipts").fetchone()[0] == 1
    )
    assert (
        connection.execute("SELECT count(*) FROM execution_failures").fetchone()[0] == 1
    )
    connection.close()


def test_public_lifecycle_rolls_back_and_fails_closed(tmp_path) -> None:
    connection = _connection(tmp_path)
    persistence = SqliteExecutionPersistence(connection)
    with persistence.unit_of_work() as unit:
        unit.save_aggregate(
            _aggregate(), expected_revision=_aggregate().execution_revision
        )
    assert (
        connection.execute("SELECT count(*) FROM execution_aggregates").fetchone()[0]
        == 0
    )

    with pytest.raises(RuntimeError):
        with persistence.unit_of_work() as unit:
            unit.save_aggregate(
                _aggregate(), expected_revision=_aggregate().execution_revision
            )
            raise RuntimeError("exceptional exit")
    assert (
        connection.execute("SELECT count(*) FROM execution_aggregates").fetchone()[0]
        == 0
    )

    unit = persistence.unit_of_work()
    with unit:
        unit.rollback()
        unit.rollback()
        with pytest.raises(SqliteExecutionTransactionError):
            unit.load_aggregate(_aggregate())
        with pytest.raises(SqliteExecutionTransactionError):
            unit.commit()
    connection.close()


def test_factory_rejects_configuration_and_schema_without_ownership(tmp_path) -> None:
    unconfigured = sqlite3.connect(":memory:", isolation_level=None)
    with pytest.raises(SqliteExecutionConfigurationError):
        SqliteExecutionPersistence(unconfigured)
    assert unconfigured.execute("SELECT 1").fetchone()[0] == 1
    unconfigured.close()

    connection = _connection(tmp_path)
    with pytest.raises(SqliteExecutionConfigurationError):
        SqliteExecutionPersistence(connection, busy_timeout_ms=60_001)
    assert connection.execute("SELECT 1").fetchone()[0] == 1

    connection.execute("DROP INDEX idx_execution_commands_idempotency_key")
    with pytest.raises(SqliteExecutionSchemaError):
        SqliteExecutionPersistence(connection)
    assert connection.execute("SELECT 1").fetchone()[0] == 1
    connection.close()
