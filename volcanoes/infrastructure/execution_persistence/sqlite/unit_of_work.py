"""Explicit unit of work for caller-owned SQLite execution persistence."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import datetime
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
    DispatchClaimResult,
    ExecutionDispatchClaimAttempt,
    DispatchOutcomeWriteSet,
    ExecutionDispatchClaim,
)
from volcanoes.application.execution.persistence.enums import (
    DispatchClaimStatus,
    DispatchResolutionStatus,
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
    SqliteExecutionDispatchAuthorizationRepository,
    SqliteExecutionDispatchClaimRepository,
    SqliteExecutionDispatchControlRepository,
    SqliteExecutionDispatchResolutionRepository,
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
        self.dispatch_control = SqliteExecutionDispatchControlRepository(
            self._transaction
        )
        self.dispatch_claims = SqliteExecutionDispatchClaimRepository(self._transaction)
        self.dispatch_authorizations = SqliteExecutionDispatchAuthorizationRepository(
            self._transaction
        )
        self.dispatch_resolutions = SqliteExecutionDispatchResolutionRepository(
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

    def record_dispatch_outcome(
        self, write_set: DispatchOutcomeWriteSet
    ) -> RecordLoadResult:
        self._transaction.execute("SAVEPOINT dispatch_outcome")
        try:
            claim = self.dispatch_claims.get(write_set.claim.claim_token)
            authorization = self.dispatch_authorizations.get(
                write_set.claim.claim_token
            )
            if (
                claim is None
                or claim.to_public() != write_set.claim
                or authorization != write_set.authorization
                or write_set.claim.client_order_id
                != _dispatch_client_order_id(write_set.claim)
                or not self._authoritative_outcome_start_is_valid(write_set)
            ):
                return self._abort_dispatch_outcome(
                    RecordLoadResult(
                        ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
                        CURRENT_SCHEMA_VERSION,
                    )
                )
            if write_set.broker_reference is not None:
                owned = self.broker_references.register(write_set.broker_reference)
                if owned.status is not ExecutionPersistenceResultStatus.CREATED:
                    return self._abort_dispatch_outcome(owned)
            evidence_result = (
                self.receipts.record(write_set.evidence)
                if isinstance(write_set.evidence, ExecutionReceiptRecord)
                else self.failures.record(write_set.evidence)
            )
            if evidence_result.status is not ExecutionPersistenceResultStatus.CREATED:
                return self._abort_dispatch_outcome(evidence_result)
            for transition in write_set.transitions:
                appended = self.transitions.append(transition)
                if appended.status is not ExecutionPersistenceResultStatus.APPENDED:
                    return self._abort_dispatch_outcome(
                        RecordLoadResult(appended.status, CURRENT_SCHEMA_VERSION)
                    )
            aggregate = self.aggregates._save_dispatch_outcome(
                write_set.aggregate,
                expected_revision=write_set.expected_revision,
                revision_increment=len(write_set.transitions),
            )
            if aggregate.status is not ExecutionPersistenceResultStatus.SAVED:
                return self._abort_dispatch_outcome(
                    RecordLoadResult(aggregate.status, CURRENT_SCHEMA_VERSION)
                )
            if not self._conflict_owner_is_current(write_set):
                return self._abort_dispatch_outcome(
                    RecordLoadResult(
                        ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
                        CURRENT_SCHEMA_VERSION,
                    )
                )
            resolution = self.dispatch_resolutions.record(write_set.resolution)
            if resolution.status is not ExecutionPersistenceResultStatus.CREATED:
                return self._abort_dispatch_outcome(resolution)
            self._transaction.execute("RELEASE SAVEPOINT dispatch_outcome")
            return resolution
        except Exception:
            self._transaction.execute("ROLLBACK TO SAVEPOINT dispatch_outcome")
            self._transaction.execute("RELEASE SAVEPOINT dispatch_outcome")
            raise

    def _authoritative_outcome_start_is_valid(
        self, write_set: DispatchOutcomeWriteSet
    ) -> bool:
        row = self._transaction.execute(
            """
            SELECT c.claim_token
            FROM execution_dispatch_claims AS c
            JOIN execution_commands AS m ON m.command_id = c.command_id
            JOIN execution_idempotency AS i ON i.idempotency_key = c.idempotency_key
            JOIN execution_approvals AS p
              ON p.approval_fingerprint = c.approval_fingerprint
            JOIN execution_aggregates AS a ON a.aggregate_id = c.aggregate_id
            JOIN execution_dispatch_authorizations AS z
              ON z.claim_token = c.claim_token
            JOIN execution_dispatch_controls AS d
              ON d.control_id = 'PAPER_DISPATCH'
            LEFT JOIN execution_dispatch_resolutions AS r
              ON r.claim_token = c.claim_token
            WHERE c.claim_token = ?
              AND m.aggregate_id = c.aggregate_id
              AND m.correlation_id = c.correlation_id
              AND m.idempotency_key = c.idempotency_key
              AND m.record_fingerprint = c.command_record_fingerprint
              AND m.canonical_payload_fingerprint = c.canonical_payload_fingerprint
              AND m.canonical_command_json = c.canonical_order_json
              AND m.approval_fingerprint = c.approval_fingerprint
              AND m.policy_fingerprint = c.policy_fingerprint
              AND m.mode = 'PAPER'
              AND i.command_id = c.command_id AND i.aggregate_id = c.aggregate_id
              AND p.bound_fingerprint = c.canonical_payload_fingerprint
              AND p.mode = 'PAPER' AND p.revocation_reference IS NULL
              AND (p.expires_at IS NULL OR p.expires_at >= ?)
              AND z.control_generation = c.control_generation
              AND d.generation = c.control_generation
              AND d.enabled = 1 AND d.emergency_stop_active = 0
              AND d.legacy_authority_active = 0
              AND a.execution_revision = ?
              AND a.lifecycle_state = ?
              AND a.lifecycle_state = 'DISPATCH_PENDING'
              AND r.claim_token IS NULL
            """,
            (
                write_set.claim.claim_token,
                write_set.resolution.resolved_at.isoformat(
                    timespec="microseconds"
                ).replace("+00:00", "Z"),
                int(write_set.expected_revision),
                write_set.transitions[0].source_state.value,
            ),
        ).fetchone()
        if row is None:
            return False
        if (
            write_set.resolution.status
            is DispatchResolutionStatus.BROKER_REFERENCE_CONFLICT
        ):
            return self._conflict_owner_is_current(write_set)
        return True

    def _conflict_owner_is_current(self, write_set: DispatchOutcomeWriteSet) -> bool:
        resolution = write_set.resolution
        if resolution.status is not DispatchResolutionStatus.BROKER_REFERENCE_CONFLICT:
            return True
        observed = resolution.broker_reference
        if observed is None:
            return False
        owner = self._transaction.execute(
            """
            SELECT aggregate_id, command_id, record_fingerprint
            FROM execution_broker_references
            WHERE broker_reference = ?
            """,
            (observed,),
        ).fetchone()
        return bool(
            owner is not None
            and owner["aggregate_id"] == str(resolution.conflicting_owner_aggregate_id)
            and owner["command_id"] == str(resolution.conflicting_owner_command_id)
            and owner["record_fingerprint"]
            == resolution.conflicting_owner_record_fingerprint
            and owner["aggregate_id"] != str(write_set.claim.aggregate_id)
            and owner["command_id"] != str(write_set.claim.command_id)
        )

    def _abort_dispatch_outcome(self, result: RecordLoadResult) -> RecordLoadResult:
        self._transaction.execute("ROLLBACK TO SAVEPOINT dispatch_outcome")
        self._transaction.execute("RELEASE SAVEPOINT dispatch_outcome")
        return result


def _dispatch_client_order_id(claim: ExecutionDispatchClaim) -> str:
    from volcanoes.application.execution.fingerprints import fingerprint_payload

    digest = fingerprint_payload(
        "pci",
        {
            "domain": "paper-client-order-v1",
            "inputs": {
                "canonical_payload_fingerprint": claim.canonical_payload_fingerprint,
                "command_id": claim.command_id,
                "idempotency_key": claim.idempotency_key,
                "submission_id": claim.submission_id,
            },
        },
    ).rsplit("-", 1)[-1]
    return "paper-" + digest[:42]


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

    def acquire_and_authorize_dispatch(
        self,
        attempt: ExecutionDispatchClaimAttempt,
        *,
        claimed_at: datetime,
        authorized_at: datetime,
    ) -> DispatchClaimResult:
        with self.unit_of_work() as first:
            result = first.dispatch_claims.acquire(attempt, claimed_at=claimed_at)
            grant = first.dispatch_claims._take_winner_grant()
            if result.status is not DispatchClaimStatus.ACQUIRED:
                first.rollback()
                return result
            if grant is None or not first.commit().committed or result.claim is None:
                return DispatchClaimResult(
                    DispatchClaimStatus.BLOCKED,
                    None,
                    CURRENT_SCHEMA_VERSION,
                    "CLAIM_COMMIT_FAILED",
                )
        with self.unit_of_work() as second:
            authorization = second.dispatch_claims._authorize_private(
                result.claim, grant, authorized_at=authorized_at
            )
            aggregate = second.aggregates.load_record(result.claim.aggregate_id)
            if (
                authorization is None
                or aggregate is None
                or not second.commit().committed
            ):
                return DispatchClaimResult(
                    DispatchClaimStatus.BLOCKED,
                    result.claim,
                    CURRENT_SCHEMA_VERSION,
                    "FINAL_GUARD_BLOCKED",
                )
            return replace(
                result,
                reason_code="AUTHORIZED_WINNER",
                authorized=True,
                authorization=authorization,
                aggregate=aggregate,
            )


__all__ = [
    "SqliteExecutionPersistence",
    "SqliteExecutionUnitOfWork",
]
