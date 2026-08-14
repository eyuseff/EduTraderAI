from __future__ import annotations

import sqlite3

import pytest

from volcanoes.application.execution.persistence.enums import (
    ExecutionPersistenceResultStatus,
)
from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionTransactionError,
)
from volcanoes.infrastructure.execution_persistence.sqlite.unit_of_work import (
    _SqliteExecutionTransaction,
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
