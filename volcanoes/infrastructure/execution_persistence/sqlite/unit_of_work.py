"""Private transaction kernel for the incomplete SQLite persistence adapter."""

from __future__ import annotations

import sqlite3
from types import TracebackType
from typing import Self

from volcanoes.application.execution.persistence.contracts import (
    ExecutionPersistenceConflict,
    UnitOfWorkCommitResult,
)
from volcanoes.application.execution.persistence.enums import (
    ExecutionPersistenceConflictKind,
    ExecutionPersistenceResultStatus,
)
from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionBusyError,
    SqliteExecutionTransactionError,
)
from volcanoes.infrastructure.execution_persistence.sqlite.migration import (
    CURRENT_SCHEMA_VERSION,
)


class _SqliteExecutionTransaction:
    """Own one explicit authoritative transaction on a caller-owned connection."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self._active = False
        self._committed = False
        self._rolled_back = False
        self._blocking_conflict: ExecutionPersistenceConflict | None = None

    def __enter__(self) -> Self:
        if self.connection.in_transaction or self._active:
            raise SqliteExecutionTransactionError(
                "Nested or caller-owned transactions are not supported."
            )
        self._execute("BEGIN IMMEDIATE")
        self._active = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._active and not self._committed:
            self.rollback()

    def ensure_active(self) -> None:
        if not self._active:
            raise SqliteExecutionTransactionError("Transaction is not active.")

    def mark_conflict(self, conflict: ExecutionPersistenceConflict) -> None:
        self.ensure_active()
        if self._blocking_conflict is None:
            self._blocking_conflict = conflict

    def execute(
        self, statement: str, parameters: tuple[object, ...] = ()
    ) -> sqlite3.Cursor:
        self.ensure_active()
        return self._execute(statement, parameters)

    def commit(self) -> UnitOfWorkCommitResult:
        if self._committed:
            return UnitOfWorkCommitResult(
                status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
                committed=False,
                schema_version=CURRENT_SCHEMA_VERSION,
            )
        self.ensure_active()
        if self._blocking_conflict is not None:
            conflict = self._blocking_conflict
            self.rollback()
            return UnitOfWorkCommitResult(
                status=_status_for_conflict(conflict),
                committed=False,
                conflict=conflict,
                schema_version=CURRENT_SCHEMA_VERSION,
            )
        try:
            self.connection.commit()
        except sqlite3.Error as exc:
            self._rollback_after_failure()
            raise _normalized_error(exc) from exc
        self._active = False
        self._committed = True
        return UnitOfWorkCommitResult(
            status=ExecutionPersistenceResultStatus.SAVED,
            committed=True,
            schema_version=CURRENT_SCHEMA_VERSION,
        )

    def rollback(self) -> None:
        if self._committed or self._rolled_back:
            return
        if self._active or self.connection.in_transaction:
            try:
                self.connection.rollback()
            except sqlite3.Error as exc:
                raise _normalized_error(exc) from exc
        self._active = False
        self._rolled_back = True

    def _execute(
        self, statement: str, parameters: tuple[object, ...] = ()
    ) -> sqlite3.Cursor:
        try:
            return self.connection.execute(statement, parameters)
        except sqlite3.Error as exc:
            raise _normalized_error(exc) from exc

    def _rollback_after_failure(self) -> None:
        if self.connection.in_transaction:
            try:
                self.connection.rollback()
            except sqlite3.Error:
                pass
        self._active = False
        self._rolled_back = True


def _normalized_error(
    exc: sqlite3.Error,
) -> SqliteExecutionTransactionError | SqliteExecutionBusyError:
    message = str(exc).lower()
    if "busy" in message or "locked" in message:
        return SqliteExecutionBusyError("SQLite transaction could not acquire a lock.")
    return SqliteExecutionTransactionError("SQLite transaction failed safely.")


def _status_for_conflict(
    conflict: ExecutionPersistenceConflict,
) -> ExecutionPersistenceResultStatus:
    statuses = {
        ExecutionPersistenceConflictKind.COMMAND_PAYLOAD_CONFLICT: ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
        ExecutionPersistenceConflictKind.IDEMPOTENCY_PAYLOAD_CONFLICT: ExecutionPersistenceResultStatus.IDEMPOTENCY_CONFLICT,
        ExecutionPersistenceConflictKind.STALE_REVISION: ExecutionPersistenceResultStatus.STALE_REVISION,
        ExecutionPersistenceConflictKind.TERMINAL_STATE_CONFLICT: ExecutionPersistenceResultStatus.ALREADY_TERMINAL,
    }
    return statuses.get(
        conflict.kind, ExecutionPersistenceResultStatus.TRANSACTION_ABORTED
    )
