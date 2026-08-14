"""Explicit unit of work for caller-owned SQLite execution persistence."""

from __future__ import annotations

import sqlite3
from types import TracebackType
from typing import Self

from volcanoes.application.execution.identities import PaperExecutionRevision
from volcanoes.application.execution.persistence.contracts import (
    AggregateSaveResult,
    CommandRegistrationResult,
    ExecutionAggregateRecord,
    ExecutionCommandRecord,
    ExecutionFailureRecord,
    ExecutionIdempotencyRecord,
    ExecutionPersistenceConflict,
    ExecutionReceiptRecord,
    ExecutionTransitionRecord,
    IdempotencyReservationResult,
    RecordLoadResult,
    TransitionAppendResult,
    UnitOfWorkCommitResult,
)
from volcanoes.application.execution.persistence.enums import (
    ExecutionPersistenceConflictKind,
    ExecutionPersistenceResultStatus,
)
from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionBusyError,
    SqliteExecutionConfigurationError,
    SqliteExecutionSchemaError,
    SqliteExecutionTransactionError,
)
from volcanoes.infrastructure.execution_persistence.sqlite.connection import (
    DEFAULT_BUSY_TIMEOUT_MS,
    MAX_BUSY_TIMEOUT_MS,
)
from volcanoes.infrastructure.execution_persistence.sqlite.migration import (
    CURRENT_SCHEMA_VERSION,
)
from volcanoes.infrastructure.execution_persistence.sqlite.repositories import (
    SqliteExecutionAggregateRepository,
    SqliteExecutionApprovalRepository,
    SqliteExecutionBrokerReferenceRepository,
    SqliteExecutionCommandRepository,
    SqliteExecutionFailureRepository,
    SqliteExecutionIdempotencyRepository,
    SqliteExecutionReceiptRepository,
    SqliteExecutionReconciliationRepository,
    SqliteExecutionRestartDiscoveryRepository,
    SqliteExecutionTransitionJournal,
)
from volcanoes.infrastructure.execution_persistence.sqlite.validation import (
    validate_sqlite_execution_schema,
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


class SqliteExecutionUnitOfWork:
    """One explicit transaction over all SQLite execution repositories."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._transaction = _SqliteExecutionTransaction(connection)
        self.aggregates = SqliteExecutionAggregateRepository(self._transaction)
        self.commands = SqliteExecutionCommandRepository(self._transaction)
        self.idempotency = SqliteExecutionIdempotencyRepository(self._transaction)
        self.transitions = SqliteExecutionTransitionJournal(self._transaction)
        self.broker_references = SqliteExecutionBrokerReferenceRepository(
            self._transaction
        )
        self.receipts = SqliteExecutionReceiptRepository(self._transaction)
        self.failures = SqliteExecutionFailureRepository(self._transaction)
        self.approvals = SqliteExecutionApprovalRepository(self._transaction)
        self.reconciliations = SqliteExecutionReconciliationRepository(
            self._transaction
        )
        self.restart_discovery = SqliteExecutionRestartDiscoveryRepository(
            self._transaction
        )

    def __enter__(self) -> Self:
        self._transaction.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._transaction.__exit__(exc_type, exc, traceback)

    def commit(self) -> UnitOfWorkCommitResult:
        return self._transaction.commit()

    def rollback(self) -> None:
        self._transaction.rollback()

    def register_command(
        self, command: ExecutionCommandRecord
    ) -> CommandRegistrationResult:
        return self.commands.register(command)

    def reserve_idempotency(
        self, reservation: ExecutionIdempotencyRecord
    ) -> IdempotencyReservationResult:
        return self.idempotency.reserve(reservation)

    def load_aggregate(self, aggregate: ExecutionAggregateRecord) -> RecordLoadResult:
        return self.aggregates.get(aggregate.aggregate_id)

    def append_transition(
        self, transition: ExecutionTransitionRecord
    ) -> TransitionAppendResult:
        return self.transitions.append(transition)

    def save_aggregate(
        self,
        aggregate: ExecutionAggregateRecord,
        *,
        expected_revision: PaperExecutionRevision,
    ) -> AggregateSaveResult:
        return self.aggregates.save(
            aggregate,
            expected_revision=expected_revision,
        )

    def record_receipt(self, receipt: ExecutionReceiptRecord) -> RecordLoadResult:
        return self.receipts.record(receipt)

    def record_failure(self, failure: ExecutionFailureRecord) -> RecordLoadResult:
        return self.failures.record(failure)


class SqliteExecutionPersistence:
    """Validated factory bound to one caller-owned configured connection."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        if not isinstance(connection, sqlite3.Connection):
            raise SqliteExecutionConfigurationError(
                "A SQLite connection must be supplied by the caller."
            )
        if busy_timeout_ms <= 0 or busy_timeout_ms > MAX_BUSY_TIMEOUT_MS:
            raise SqliteExecutionConfigurationError(
                "Busy timeout is outside safe bounds."
            )
        try:
            if connection.in_transaction:
                raise SqliteExecutionTransactionError(
                    "Persistence cannot bind inside an active transaction."
                )
            if connection.row_factory is not sqlite3.Row:
                raise SqliteExecutionConfigurationError(
                    "SQLite row_factory must be sqlite3.Row."
                )
            validation = validate_sqlite_execution_schema(
                connection,
                expected_busy_timeout_ms=busy_timeout_ms,
            )
        except sqlite3.Error as exc:
            raise SqliteExecutionConfigurationError(
                "SQLite connection validation failed safely."
            ) from exc
        if validation.blocks_execution and any(
            "pragma" in failure
            or "busy_timeout" in failure
            or "journal_mode" in failure
            for failure in validation.failures
        ):
            raise SqliteExecutionConfigurationError(
                "SQLite connection configuration is invalid."
            )
        if validation.blocks_execution:
            raise SqliteExecutionSchemaError(
                "SQLite execution schema or configuration is invalid."
            )
        self._connection = connection

    def unit_of_work(self) -> SqliteExecutionUnitOfWork:
        return SqliteExecutionUnitOfWork(self._connection)


__all__ = [
    "SqliteExecutionPersistence",
    "SqliteExecutionUnitOfWork",
]
