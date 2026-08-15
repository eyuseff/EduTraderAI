from __future__ import annotations

import importlib
import sqlite3
from pathlib import Path

import pytest

import adapters.paper_execution_persistence_runtime as runtime_module
from adapters.paper_execution_persistence_runtime import (
    PaperExecutionPersistenceRuntime,
)
from volcanoes.application.execution import (
    ExecutionPersistenceResultStatus,
    ExecutionRestartDiscoveryQuery,
    PaperExecutionLifecycleState,
)
from volcanoes.application.platform.configuration import (
    PaperExecutionPersistenceRuntimeConfiguration,
)
from volcanoes.infrastructure.execution_persistence.sqlite import (
    CURRENT_SCHEMA_VERSION,
    KNOWN_MIGRATIONS,
    apply_pending_migrations,
    inspect_schema_state,
    open_sqlite_execution_connection,
)
from volcanoes.infrastructure.execution_persistence.sqlite.integrity import (
    IntegrityCheckResult,
    InvariantCheckResult,
)
from volcanoes.infrastructure.execution_persistence.sqlite.validation import (
    SchemaValidationResult,
)
from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionBusyError,
    SqliteExecutionIntegrityError,
    SqliteExecutionMigrationError,
)
from volcanoes.application.execution.persistence.errors import (
    ExecutionPersistenceInvariantError,
)
from test_sqlite_execution_persistence_repositories import NOW, _aggregate


def configuration(
    tmp_path: Path, *, busy_timeout_ms: int = 200
) -> PaperExecutionPersistenceRuntimeConfiguration:
    return PaperExecutionPersistenceRuntimeConfiguration(
        database_path=(tmp_path / "execution.sqlite").resolve(),
        application_version="4.1.0-slice4",
        busy_timeout_ms=busy_timeout_ms,
    )


def query(
    *,
    limit: int | None = None,
    cursor: str | None = None,
    states: tuple[PaperExecutionLifecycleState, ...] = (
        PaperExecutionLifecycleState.DISPATCH_PENDING,
    ),
) -> ExecutionRestartDiscoveryQuery:
    return ExecutionRestartDiscoveryQuery(
        lifecycle_states=states,
        limit=limit,
        cursor=cursor,
        schema_version=CURRENT_SCHEMA_VERSION,
    )


def test_import_and_construction_have_no_persistence_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured = configuration(tmp_path)
    calls: list[object] = []
    monkeypatch.setattr(
        runtime_module,
        "open_sqlite_execution_connection",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    importlib.reload(runtime_module)
    runtime = runtime_module.PaperExecutionPersistenceRuntime(configured)

    assert calls == []
    assert not configured.database_path.exists()
    with pytest.raises(runtime_module.PaperExecutionPersistenceRuntimeError):
        runtime.unit_of_work()
    with pytest.raises(runtime_module.PaperExecutionPersistenceRuntimeError):
        runtime.discover_restart_candidates(query())


def test_empty_database_start_migrates_through_v003_and_builds_units(
    tmp_path: Path,
) -> None:
    configured = configuration(tmp_path)
    runtime = PaperExecutionPersistenceRuntime(configured).start()

    state = inspect_schema_state(runtime._connection, known_migrations=KNOWN_MIGRATIONS)
    assert state.current_version == CURRENT_SCHEMA_VERSION
    assert {
        migration.application_version for migration in state.applied_migrations
    } == {configured.application_version}
    with runtime.unit_of_work() as unit:
        result = unit.save_aggregate(
            _aggregate(), expected_revision=_aggregate().execution_revision
        )
        assert result.status is ExecutionPersistenceResultStatus.CREATED
        assert unit.commit().committed is True

    runtime.close()
    assert configured.database_path.exists()


def test_existing_v003_reopens_and_consequential_records_survive(
    tmp_path: Path,
) -> None:
    configured = configuration(tmp_path)
    runtime = PaperExecutionPersistenceRuntime(configured).start()
    record = _aggregate(lifecycle_state=PaperExecutionLifecycleState.DISPATCH_PENDING)
    with runtime.unit_of_work() as unit:
        unit.save_aggregate(record, expected_revision=record.execution_revision)
        unit.commit()
    runtime.close()

    reopened = PaperExecutionPersistenceRuntime(configured).start()
    result = reopened.discover_restart_candidates(query())

    assert result.aggregates == (record,)
    assert result.complete is True
    reopened.close()


def test_restart_discovery_is_deterministic_paginated_and_read_only(
    tmp_path: Path,
) -> None:
    runtime = PaperExecutionPersistenceRuntime(configuration(tmp_path)).start()
    records = tuple(
        _aggregate(
            symbol,
            lifecycle_state=PaperExecutionLifecycleState.DISPATCH_PENDING,
        )
        for symbol in ("MSFT", "AAPL", "TSLA")
    )
    with runtime.unit_of_work() as unit:
        for record in records:
            unit.save_aggregate(record, expected_revision=record.execution_revision)
        unit.commit()
    connection = runtime._connection
    assert connection is not None
    changes_before = connection.total_changes

    first = runtime.discover_restart_candidates(query(limit=2))
    second = runtime.discover_restart_candidates(
        query(limit=2, cursor=first.next_cursor)
    )
    malformed = runtime.discover_restart_candidates(query(limit=2, cursor="bad"))
    cross_filter = runtime.discover_restart_candidates(
        query(
            limit=2,
            cursor=first.next_cursor,
            states=(PaperExecutionLifecycleState.DISPATCHED,),
        )
    )

    combined = first.aggregates + second.aggregates
    assert tuple(str(record.aggregate_id) for record in combined) == tuple(
        sorted(str(record.aggregate_id) for record in records)
    )
    assert malformed.aggregates == first.aggregates
    assert cross_filter.aggregates == ()
    assert connection.total_changes == changes_before
    assert connection.in_transaction is False
    runtime.close()


def test_unknown_outcomes_remain_operator_review_candidates(tmp_path: Path) -> None:
    runtime = PaperExecutionPersistenceRuntime(configuration(tmp_path)).start()
    record = _aggregate(
        lifecycle_state=PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
        outcome_unknown=True,
        reconciliation_required=True,
    )
    with runtime.unit_of_work() as unit:
        unit.save_aggregate(record, expected_revision=record.execution_revision)
        unit.commit()

    result = runtime.discover_restart_candidates(
        query(states=(PaperExecutionLifecycleState.OUTCOME_UNKNOWN,))
    )

    assert result.aggregates == (record,)
    assert result.aggregates[0].outcome_unknown is True
    assert result.aggregates[0].reconciliation_required is True
    runtime.close()


def test_runtime_rejects_non_consequential_discovery_filter(tmp_path: Path) -> None:
    runtime = PaperExecutionPersistenceRuntime(configuration(tmp_path)).start()
    connection = runtime._connection
    assert connection is not None

    with pytest.raises(ExecutionPersistenceInvariantError):
        runtime.discover_restart_candidates(
            query(states=(PaperExecutionLifecycleState.CREATED,))
        )

    assert connection.in_transaction is False
    runtime.close()


def test_clean_repeated_shutdown_and_use_after_close_rejection(tmp_path: Path) -> None:
    runtime = PaperExecutionPersistenceRuntime(configuration(tmp_path)).start()
    unit = runtime.unit_of_work()
    unit.__enter__()
    runtime.close()
    runtime.close()

    with pytest.raises(runtime_module.PaperExecutionPersistenceRuntimeError):
        runtime.unit_of_work()
    with pytest.raises(runtime_module.PaperExecutionPersistenceRuntimeError):
        runtime.start()


def test_partial_startup_failure_rolls_back_and_closes_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = open_sqlite_execution_connection(configuration(tmp_path).database_path)
    monkeypatch.setattr(
        runtime_module,
        "open_sqlite_execution_connection",
        lambda *args, **kwargs: connection,
    )
    monkeypatch.setattr(
        runtime_module,
        "apply_pending_migrations",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            SqliteExecutionMigrationError("startup failed")
        ),
    )

    with pytest.raises(SqliteExecutionMigrationError):
        PaperExecutionPersistenceRuntime(configuration(tmp_path)).start()
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


@pytest.mark.parametrize(
    ("check_name", "blocked_result"),
    [
        (
            "validate_sqlite_execution_schema",
            SchemaValidationResult(False, ("schema blocked",)),
        ),
        (
            "run_integrity_check",
            IntegrityCheckResult("integrity_check", False, ("bad",), True),
        ),
        (
            "check_foreign_keys",
            IntegrityCheckResult("foreign_key_check", False, ("bad",), True),
        ),
        (
            "check_aggregate_transition_revisions",
            InvariantCheckResult("aggregate_revisions", False, ("bad",), True),
        ),
        (
            "check_idempotency_bindings",
            InvariantCheckResult("idempotency", False, ("bad",), True),
        ),
        (
            "check_broker_reference_ownership",
            InvariantCheckResult("reference_ownership", False, ("bad",), True),
        ),
    ],
)
def test_every_startup_validation_blocker_closes_partial_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    check_name: str,
    blocked_result: object,
) -> None:
    configured = configuration(tmp_path)
    PaperExecutionPersistenceRuntime(configured).start().close()
    opened: list[sqlite3.Connection] = []
    real_open = runtime_module.open_sqlite_execution_connection

    def tracked_open(*args: object, **kwargs: object) -> sqlite3.Connection:
        connection = real_open(*args, **kwargs)  # type: ignore[arg-type]
        opened.append(connection)
        return connection

    monkeypatch.setattr(
        runtime_module, "open_sqlite_execution_connection", tracked_open
    )
    monkeypatch.setattr(
        runtime_module,
        check_name,
        lambda *args, **kwargs: blocked_result,
    )

    with pytest.raises(SqliteExecutionIntegrityError):
        PaperExecutionPersistenceRuntime(configured).start()

    assert len(opened) == 1
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")


def test_existing_transaction_is_rejected_and_cleaned_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = open_sqlite_execution_connection(configuration(tmp_path).database_path)
    connection.execute("BEGIN")
    monkeypatch.setattr(
        runtime_module,
        "open_sqlite_execution_connection",
        lambda *args, **kwargs: connection,
    )

    with pytest.raises(SqliteExecutionMigrationError):
        PaperExecutionPersistenceRuntime(configuration(tmp_path)).start()
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")


def test_locked_database_surfaces_busy_without_retry(tmp_path: Path) -> None:
    configured = configuration(tmp_path, busy_timeout_ms=10)
    owner = open_sqlite_execution_connection(
        configured.database_path,
        busy_timeout_ms=configured.busy_timeout_ms,
    )
    owner.execute("BEGIN IMMEDIATE")

    with pytest.raises(SqliteExecutionBusyError):
        PaperExecutionPersistenceRuntime(configured).start()

    owner.rollback()
    owner.close()


def test_existing_v004_migration_inventory_is_not_reapplied(tmp_path: Path) -> None:
    configured = configuration(tmp_path)
    connection = open_sqlite_execution_connection(configured.database_path)
    first = apply_pending_migrations(
        connection,
        KNOWN_MIGRATIONS,
        applied_at=NOW,
        application_version=configured.application_version,
    )
    connection.close()

    runtime = PaperExecutionPersistenceRuntime(configured).start()
    state = inspect_schema_state(runtime._connection, known_migrations=KNOWN_MIGRATIONS)

    assert first.changed is True
    assert tuple(item.migration_id for item in state.applied_migrations) == (
        "v001",
        "v002",
        "v003",
        "v004",
    )
    runtime.close()
