from __future__ import annotations

from volcanoes.application.execution.persistence.enums import (
    ExecutionPersistenceResultStatus,
)
from volcanoes.infrastructure.execution_persistence.sqlite.repositories import (
    SqliteExecutionAggregateRepository,
    SqliteExecutionCommandRepository,
)
from volcanoes.infrastructure.execution_persistence.sqlite.unit_of_work import (
    _SqliteExecutionTransaction,
)
from test_sqlite_execution_persistence_repositories import (
    _aggregate,
    _command,
    _connection,
)


def test_blocking_command_conflict_rolls_back_earlier_aggregate_write(tmp_path) -> None:
    connection = _connection(tmp_path)
    aggregate = _aggregate()
    command = _command()

    with _SqliteExecutionTransaction(connection) as transaction:
        SqliteExecutionAggregateRepository(transaction).save(
            aggregate,
            expected_revision=aggregate.execution_revision,
        )
        SqliteExecutionCommandRepository(transaction).register(command)
        assert transaction.commit().committed is True

    conflicting = _command(canonical_payload_fingerprint="pcf-" + "a" * 64)
    later_aggregate = _aggregate("MSFT")
    with _SqliteExecutionTransaction(connection) as transaction:
        aggregates = SqliteExecutionAggregateRepository(transaction)
        commands = SqliteExecutionCommandRepository(transaction)
        assert (
            aggregates.save(
                later_aggregate,
                expected_revision=later_aggregate.execution_revision,
            ).status
            is ExecutionPersistenceResultStatus.CREATED
        )
        assert (
            commands.register(conflicting).status
            is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
        )
        assert (
            transaction.commit().status
            is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
        )

    assert (
        connection.execute("SELECT count(*) FROM execution_aggregates").fetchone()[0]
        == 1
    )
    connection.close()
