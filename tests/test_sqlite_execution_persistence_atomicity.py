from __future__ import annotations

import pytest

from volcanoes.application.execution.persistence.enums import (
    ExecutionPersistenceResultStatus,
)
from volcanoes.application.execution.persistence import RecordLoadResult
from volcanoes.application.execution import PaperBrokerOrderReference
from volcanoes.application.execution.submission import (
    ControlledPaperSubmissionService,
    PaperDispatchObservation,
)
from volcanoes.infrastructure.execution_persistence.sqlite.connection import (
    open_sqlite_execution_connection,
)
from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionBusyError,
    SqliteExecutionTransactionError,
)
from volcanoes.infrastructure.execution_persistence.sqlite.repositories import (
    SqliteExecutionAggregateRepository,
    SqliteExecutionBrokerReferenceRepository,
    SqliteExecutionCommandRepository,
    SqliteExecutionDispatchResolutionRepository,
    SqliteExecutionReceiptRepository,
    SqliteExecutionTransitionJournal,
)
from volcanoes.infrastructure.execution_persistence.sqlite.unit_of_work import (
    SqliteExecutionPersistence,
    SqliteExecutionUnitOfWork,
    _SqliteExecutionTransaction,
)
from test_sqlite_execution_persistence_unit_of_work import (
    DISPATCH_NOW,
    _seed_dispatch_authority,
)
from test_execution_persistence_in_memory_repositories import receipt_record
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


def test_deferred_foreign_key_commit_failure_rolls_back_and_keeps_connection(
    tmp_path,
) -> None:
    connection = _connection(tmp_path)
    persistence = SqliteExecutionPersistence(connection)

    with persistence.unit_of_work() as unit:
        connection.execute("PRAGMA defer_foreign_keys = ON")
        result = unit.record_receipt(receipt_record())
        assert result.status is ExecutionPersistenceResultStatus.CREATED
        with pytest.raises(SqliteExecutionTransactionError):
            unit.commit()

    assert (
        connection.execute("SELECT count(*) FROM execution_receipts").fetchone()[0] == 0
    )
    assert connection.execute("SELECT 1").fetchone()[0] == 1
    connection.close()


def test_two_connection_contention_fails_busy_without_hidden_retry(tmp_path) -> None:
    first_connection = _connection(tmp_path)
    second_connection = open_sqlite_execution_connection(tmp_path / "execution.sqlite")
    first = SqliteExecutionPersistence(first_connection)
    second = SqliteExecutionPersistence(second_connection)
    statements: list[str] = []
    second_connection.set_trace_callback(statements.append)

    with first.unit_of_work():
        with pytest.raises(SqliteExecutionBusyError):
            second.unit_of_work().__enter__()

    begin_attempts = [
        statement for statement in statements if statement == "BEGIN IMMEDIATE"
    ]
    assert begin_attempts == ["BEGIN IMMEDIATE"]
    with second.unit_of_work() as unit:
        assert unit.commit().committed is True
    assert first_connection.execute("SELECT 1").fetchone()[0] == 1
    assert second_connection.execute("SELECT 1").fetchone()[0] == 1
    first_connection.close()
    second_connection.close()


@pytest.mark.parametrize(
    ("target", "method", "raise_call"),
    (
        (SqliteExecutionBrokerReferenceRepository, "register", 1),
        (SqliteExecutionReceiptRepository, "record", 1),
        (SqliteExecutionTransitionJournal, "append", 1),
        (SqliteExecutionTransitionJournal, "append", 2),
        (SqliteExecutionAggregateRepository, "_save_dispatch_outcome", 1),
        (SqliteExecutionDispatchResolutionRepository, "record", 1),
    ),
)
def test_dispatch_outcome_savepoint_rolls_back_every_repository_stage(
    tmp_path, monkeypatch, target, method, raise_call
) -> None:
    connection = _connection(tmp_path)
    persistence = SqliteExecutionPersistence(connection)
    request = _seed_dispatch_authority(persistence)
    captured = []

    def capture(self, write_set):
        captured.append(write_set)
        return RecordLoadResult(ExecutionPersistenceResultStatus.CREATED, 4)

    monkeypatch.setattr(SqliteExecutionUnitOfWork, "record_dispatch_outcome", capture)
    ControlledPaperSubmissionService(
        persistence,
        lambda order: PaperDispatchObservation(
            request.submission_id,
            PaperBrokerOrderReference("pbr-" + "5" * 64),
            True,
            "ACK",
        ),
        clock=lambda: DISPATCH_NOW,
    ).apply_once(request)
    assert len(captured) == 1
    monkeypatch.undo()
    original = getattr(target, method)
    calls = 0

    def injected(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == raise_call:
            raise RuntimeError("injected SQLite outcome failure")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(target, method, injected)
    unit = persistence.unit_of_work()
    unit.__enter__()
    with pytest.raises(RuntimeError, match="injected SQLite outcome failure"):
        unit.record_dispatch_outcome(captured[0])
    assert unit.commit().committed
    assert (
        connection.execute("SELECT count(*) FROM execution_dispatch_claims").fetchone()[
            0
        ]
        == 1
    )
    assert (
        connection.execute(
            "SELECT count(*) FROM execution_dispatch_authorizations"
        ).fetchone()[0]
        == 1
    )
    for table in (
        "execution_broker_references",
        "execution_receipts",
        "execution_transitions",
        "execution_dispatch_resolutions",
    ):
        assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    assert (
        connection.execute(
            "SELECT lifecycle_state FROM execution_aggregates"
        ).fetchone()[0]
        == "DISPATCH_PENDING"
    )
    connection.close()


def test_dispatch_outcome_failure_before_savepoint_release_rolls_back_all(
    tmp_path, monkeypatch
) -> None:
    connection = _connection(tmp_path)
    persistence = SqliteExecutionPersistence(connection)
    request = _seed_dispatch_authority(persistence)
    captured = []

    def capture(self, write_set):
        captured.append(write_set)
        return RecordLoadResult(ExecutionPersistenceResultStatus.CREATED, 4)

    monkeypatch.setattr(SqliteExecutionUnitOfWork, "record_dispatch_outcome", capture)
    ControlledPaperSubmissionService(
        persistence,
        lambda order: PaperDispatchObservation(
            request.submission_id,
            PaperBrokerOrderReference("pbr-" + "5" * 64),
            True,
            "ACK",
        ),
        clock=lambda: DISPATCH_NOW,
    ).apply_once(request)
    monkeypatch.undo()
    original = _SqliteExecutionTransaction.execute
    injected = False

    def fail_release(self, sql, parameters=()):
        nonlocal injected
        if sql == "RELEASE SAVEPOINT dispatch_outcome" and not injected:
            injected = True
            raise RuntimeError("injected before release")
        return original(self, sql, parameters)

    monkeypatch.setattr(_SqliteExecutionTransaction, "execute", fail_release)
    unit = persistence.unit_of_work()
    unit.__enter__()
    with pytest.raises(RuntimeError, match="injected before release"):
        unit.record_dispatch_outcome(captured[0])
    assert unit.commit().committed
    for table in (
        "execution_broker_references",
        "execution_receipts",
        "execution_transitions",
        "execution_dispatch_resolutions",
    ):
        assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    connection.close()
