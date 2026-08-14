"""Explicit process-scoped runtime for local Paper SQLite persistence."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Self

from volcanoes.application.execution.persistence.contracts import (
    ExecutionRestartDiscoveryQuery,
    RestartDiscoveryResult,
)
from volcanoes.application.execution.lifecycle import PaperExecutionLifecycleState
from volcanoes.application.execution.persistence.errors import (
    ExecutionPersistenceInvariantError,
)
from volcanoes.application.platform.configuration import (
    PaperExecutionPersistenceRuntimeConfiguration,
    validate_paper_execution_persistence_runtime_configuration,
)
from volcanoes.infrastructure.execution_persistence.sqlite import (
    KNOWN_MIGRATIONS,
    SqliteExecutionPersistence,
    SqliteExecutionUnitOfWork,
    apply_pending_migrations,
    check_aggregate_transition_revisions,
    check_broker_reference_ownership,
    check_foreign_keys,
    check_idempotency_bindings,
    open_sqlite_execution_connection,
    run_integrity_check,
    validate_sqlite_execution_schema,
)
from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionBusyError,
    SqliteExecutionIntegrityError,
    SqliteExecutionTransactionError,
)


class PaperExecutionPersistenceRuntimeError(RuntimeError):
    """The local persistence runtime is unavailable in its current state."""


_CONSEQUENTIAL_RESTART_STATES = frozenset(
    {
        PaperExecutionLifecycleState.CANCEL_PENDING,
        PaperExecutionLifecycleState.DISPATCH_PENDING,
        PaperExecutionLifecycleState.DISPATCHED,
        PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
        PaperExecutionLifecycleState.PARTIALLY_FILLED,
        PaperExecutionLifecycleState.RECONCILIATION_REQUIRED,
        PaperExecutionLifecycleState.REPLACE_PENDING,
    }
)


class PaperExecutionPersistenceRuntime:
    """Own one explicitly started local SQLite persistence connection."""

    def __init__(
        self, configuration: PaperExecutionPersistenceRuntimeConfiguration
    ) -> None:
        if not isinstance(configuration, PaperExecutionPersistenceRuntimeConfiguration):
            raise TypeError(
                "configuration must be PaperExecutionPersistenceRuntimeConfiguration."
            )
        self._configuration = configuration
        self._connection: sqlite3.Connection | None = None
        self._persistence: SqliteExecutionPersistence | None = None
        self._started = False
        self._closed = False

    def start(self) -> Self:
        """Open, migrate, verify, and bind the local persistence runtime."""

        if self._closed:
            raise PaperExecutionPersistenceRuntimeError("Runtime is already closed.")
        if self._started:
            raise PaperExecutionPersistenceRuntimeError("Runtime is already started.")
        validate_paper_execution_persistence_runtime_configuration(self._configuration)
        connection: sqlite3.Connection | None = None
        try:
            connection = open_sqlite_execution_connection(
                self._configuration.database_path,
                busy_timeout_ms=self._configuration.busy_timeout_ms,
            )
            apply_pending_migrations(
                connection,
                KNOWN_MIGRATIONS,
                applied_at=datetime.now(UTC),
                application_version=self._configuration.application_version,
            )
            _validate_started_connection(connection, self._configuration)
            persistence = SqliteExecutionPersistence(
                connection,
                busy_timeout_ms=self._configuration.busy_timeout_ms,
            )
        except Exception as exc:
            _close_after_startup_failure(connection)
            normalized = _busy_error(exc)
            if normalized is not None:
                raise normalized from exc
            raise
        self._connection = connection
        self._persistence = persistence
        self._started = True
        return self

    def unit_of_work(self) -> SqliteExecutionUnitOfWork:
        """Return a fresh short-lived explicit unit of work."""

        return self._require_persistence().unit_of_work()

    def discover_restart_candidates(
        self, query: ExecutionRestartDiscoveryQuery
    ) -> RestartDiscoveryResult:
        """Read deterministic operator-review candidates without mutation."""

        if not isinstance(query, ExecutionRestartDiscoveryQuery) or not set(
            query.lifecycle_states
        ).issubset(_CONSEQUENTIAL_RESTART_STATES):
            raise ExecutionPersistenceInvariantError(
                "INVALID_RUNTIME_RESTART_FILTER",
                "Runtime discovery accepts consequential lifecycle states only.",
            )
        with self.unit_of_work() as unit:
            result = unit.restart_discovery.discover(query)
            unit.rollback()
            return result

    def close(self) -> None:
        """Roll back active work and close the owned connection safely."""

        if self._closed:
            return
        connection = self._connection
        self._persistence = None
        self._connection = None
        self._started = False
        self._closed = True
        if connection is None:
            return
        rollback_error: sqlite3.Error | None = None
        try:
            if connection.in_transaction:
                connection.rollback()
        except sqlite3.Error as exc:
            rollback_error = exc
        finally:
            connection.close()
        if rollback_error is not None:
            normalized = _busy_error(rollback_error)
            if normalized is not None:
                raise normalized from rollback_error
            raise SqliteExecutionTransactionError(
                "SQLite shutdown rollback failed safely."
            ) from rollback_error

    def _require_persistence(self) -> SqliteExecutionPersistence:
        if not self._started or self._closed or self._persistence is None:
            raise PaperExecutionPersistenceRuntimeError("Runtime is not active.")
        return self._persistence


def _validate_started_connection(
    connection: sqlite3.Connection,
    configuration: PaperExecutionPersistenceRuntimeConfiguration,
) -> None:
    validation = validate_sqlite_execution_schema(
        connection,
        expected_busy_timeout_ms=configuration.busy_timeout_ms,
    )
    if validation.blocks_execution:
        raise SqliteExecutionIntegrityError(
            "SQLite schema or connection validation blocked startup."
        )
    checks = (
        run_integrity_check(connection),
        check_foreign_keys(connection),
        check_aggregate_transition_revisions(connection),
        check_idempotency_bindings(connection),
        check_broker_reference_ownership(connection),
    )
    if any(check.blocks_execution for check in checks):
        raise SqliteExecutionIntegrityError(
            "SQLite integrity or persistence invariants blocked startup."
        )


def _close_after_startup_failure(connection: sqlite3.Connection | None) -> None:
    if connection is None:
        return
    try:
        if connection.in_transaction:
            connection.rollback()
    except sqlite3.Error:
        pass
    finally:
        connection.close()


def _busy_error(exc: BaseException) -> SqliteExecutionBusyError | None:
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, SqliteExecutionBusyError):
            return current
        if isinstance(current, sqlite3.Error):
            message = str(current).lower()
            if "busy" in message or "locked" in message:
                return SqliteExecutionBusyError(
                    "SQLite persistence runtime could not acquire a lock."
                )
        current = current.__cause__
    return None


__all__ = [
    "PaperExecutionPersistenceRuntime",
    "PaperExecutionPersistenceRuntimeError",
]
