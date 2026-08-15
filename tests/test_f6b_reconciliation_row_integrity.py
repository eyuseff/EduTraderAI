from __future__ import annotations

import sqlite3

import pytest

from volcanoes.application.execution import ExecutionPersistenceResultStatus
from volcanoes.infrastructure.execution_persistence.sqlite import (
    SqliteExecutionPersistence,
    open_sqlite_execution_connection,
)
from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionSchemaError,
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


def test_restart_rejects_reconciliation_row_with_restored_trigger_but_bad_fingerprint(
    tmp_path,
) -> None:
    path, connection = _database(tmp_path)
    _seed_aggregate(connection)
    record = _reconciliation()

    with _SqliteExecutionTransaction(connection) as transaction:
        result = SqliteExecutionReconciliationRepository(transaction).record(record)
        assert result.status is ExecutionPersistenceResultStatus.CREATED
        assert transaction.commit().committed is True
    connection.close()

    tamper = sqlite3.connect(path)
    trigger_sql = tamper.execute(
        "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
        ("trg_execution_reconciliations_no_update",),
    ).fetchone()[0]
    assert trigger_sql
    tamper.execute("DROP TRIGGER trg_execution_reconciliations_no_update")
    tamper.execute(
        "UPDATE execution_reconciliations SET record_fingerprint=? WHERE reconciliation_id=?",
        ("prc-" + "0" * 64, record.reconciliation_id),
    )
    tamper.execute(trigger_sql)
    tamper.commit()
    tamper.close()

    reopened = open_sqlite_execution_connection(path)
    try:
        with pytest.raises(SqliteExecutionSchemaError):
            SqliteExecutionPersistence(reopened)
    finally:
        reopened.close()
