"""SQLite repositories for the first, intentionally incomplete Phase 2 slice."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import sqlite3
from typing import TYPE_CHECKING

from volcanoes.application.execution.enums import (
    PaperExecutionMode,
    PaperExecutionOperation,
)
from volcanoes.application.execution.identities import (
    PaperBrokerOrderReference,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionIdempotencyKey,
    PaperExecutionRevision,
)
from volcanoes.application.execution.lifecycle import PaperExecutionLifecycleState
from volcanoes.application.execution.persistence.contracts import (
    AggregateSaveResult,
    CommandRegistrationResult,
    ExecutionAggregateRecord,
    ExecutionCommandRecord,
    ExecutionIdempotencyRecord,
    ExecutionPersistenceConflict,
    IdempotencyReservationResult,
    RecordLoadResult,
    ReplayLookupResult,
)
from volcanoes.application.execution.persistence.enums import (
    ExecutionCommandProcessingOutcome,
    ExecutionIdempotencyReservationStatus,
    ExecutionPersistenceConflictKind,
    ExecutionPersistenceConflictSeverity,
    ExecutionPersistenceResultStatus,
    ExecutionReplayKind,
)
from volcanoes.infrastructure.execution_persistence.sqlite.migration import (
    CURRENT_SCHEMA_VERSION,
)

if TYPE_CHECKING:
    from volcanoes.infrastructure.execution_persistence.sqlite.unit_of_work import (
        _SqliteExecutionTransaction,
    )


def _conflict(
    *,
    kind: ExecutionPersistenceConflictKind,
    code: str,
    safe_message: str,
    aggregate_id: PaperExecutionAggregateId | None = None,
    command_id: PaperExecutionCommandId | None = None,
    idempotency_key: PaperExecutionIdempotencyKey | None = None,
    expected_revision: PaperExecutionRevision | None = None,
    actual_revision: PaperExecutionRevision | None = None,
) -> ExecutionPersistenceConflict:
    return ExecutionPersistenceConflict(
        kind=kind,
        severity=ExecutionPersistenceConflictSeverity.ERROR,
        code=code,
        safe_message=safe_message,
        schema_version=CURRENT_SCHEMA_VERSION,
        aggregate_id=aggregate_id,
        command_id=command_id,
        idempotency_key=idempotency_key,
        expected_revision=expected_revision,
        actual_revision=actual_revision,
    )


class _RepositoryBase:
    def __init__(self, transaction: "_SqliteExecutionTransaction") -> None:
        self._transaction = transaction

    def _row(
        self, statement: str, parameters: tuple[object, ...]
    ) -> sqlite3.Row | None:
        return self._transaction.execute(statement, parameters).fetchone()


class SqliteExecutionAggregateRepository(_RepositoryBase):
    """SQLite implementation of aggregate load and exact-CAS save semantics."""

    def get(self, aggregate_id: PaperExecutionAggregateId) -> RecordLoadResult:
        record = self.load_record(aggregate_id)
        if record is None:
            return RecordLoadResult(
                status=ExecutionPersistenceResultStatus.NOT_FOUND,
                schema_version=CURRENT_SCHEMA_VERSION,
            )
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.LOADED,
            record_fingerprint=record.record_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )

    def load_record(
        self, aggregate_id: PaperExecutionAggregateId
    ) -> ExecutionAggregateRecord | None:
        row = self._row(
            "SELECT * FROM execution_aggregates WHERE aggregate_id = ?",
            (str(aggregate_id),),
        )
        return _aggregate_from_row(row) if row is not None else None

    def save(
        self,
        record: ExecutionAggregateRecord,
        *,
        expected_revision: PaperExecutionRevision,
    ) -> AggregateSaveResult:
        existing = self.load_record(record.aggregate_id)
        result = _aggregate_save_result(record, existing, expected_revision)
        if result.conflict is not None:
            self._transaction.mark_conflict(result.conflict)
            return result
        if result.status is ExecutionPersistenceResultStatus.CREATED:
            self._transaction.execute(_AGGREGATE_INSERT, _aggregate_values(record))
        elif result.status is ExecutionPersistenceResultStatus.SAVED:
            values = _aggregate_values(record)
            cursor = self._transaction.execute(
                _AGGREGATE_UPDATE,
                values[1:] + (values[0], int(expected_revision)),
            )
            if cursor.rowcount != 1:
                conflict = _conflict(
                    kind=ExecutionPersistenceConflictKind.STALE_REVISION,
                    code="STALE_AGGREGATE_REVISION",
                    safe_message="Aggregate revision changed before save.",
                    aggregate_id=record.aggregate_id,
                    expected_revision=expected_revision,
                )
                self._transaction.mark_conflict(conflict)
                return AggregateSaveResult(
                    status=ExecutionPersistenceResultStatus.STALE_REVISION,
                    aggregate_id=record.aggregate_id,
                    expected_revision=expected_revision,
                    current_revision=None,
                    conflict=conflict,
                    schema_version=CURRENT_SCHEMA_VERSION,
                )
        return result


class SqliteExecutionCommandRepository(_RepositoryBase):
    """SQLite implementation of immutable command registration and replay."""

    def get(self, command_id: PaperExecutionCommandId) -> RecordLoadResult:
        record = self.load_record(command_id)
        if record is None:
            return RecordLoadResult(
                status=ExecutionPersistenceResultStatus.NOT_FOUND,
                schema_version=CURRENT_SCHEMA_VERSION,
            )
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.LOADED,
            record_fingerprint=record.record_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )

    def load_record(
        self, command_id: PaperExecutionCommandId
    ) -> ExecutionCommandRecord | None:
        row = self._row(
            "SELECT * FROM execution_commands WHERE command_id = ?", (str(command_id),)
        )
        return _command_from_row(row) if row is not None else None

    def register(self, record: ExecutionCommandRecord) -> CommandRegistrationResult:
        existing = self.load_record(record.command_id)
        result = _command_result(record, existing)
        if result.conflict is not None:
            self._transaction.mark_conflict(result.conflict)
        elif result.status is ExecutionPersistenceResultStatus.CREATED:
            self._transaction.execute(_COMMAND_INSERT, _command_values(record))
        return result

    def lookup_replay(
        self, command_id: PaperExecutionCommandId, payload_fingerprint: str
    ) -> ReplayLookupResult:
        existing = self.load_record(command_id)
        if existing is None:
            return ReplayLookupResult(
                status=ExecutionPersistenceResultStatus.NOT_FOUND,
                replay_kind=ExecutionReplayKind.NONE,
                schema_version=CURRENT_SCHEMA_VERSION,
            )
        if existing.canonical_payload_fingerprint == payload_fingerprint:
            return ReplayLookupResult(
                status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
                replay_kind=ExecutionReplayKind.EXACT_COMMAND,
                original_command_id=existing.command_id,
                original_result_fingerprint=existing.record_fingerprint,
                schema_version=CURRENT_SCHEMA_VERSION,
            )
        conflict = _conflict(
            kind=ExecutionPersistenceConflictKind.COMMAND_PAYLOAD_CONFLICT,
            code="COMMAND_PAYLOAD_CONFLICT",
            safe_message="Command identity already exists with different payload.",
            aggregate_id=existing.aggregate_id,
            command_id=command_id,
        )
        return ReplayLookupResult(
            status=ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
            replay_kind=ExecutionReplayKind.NONE,
            conflict=conflict,
            schema_version=CURRENT_SCHEMA_VERSION,
        )


class SqliteExecutionIdempotencyRepository(_RepositoryBase):
    """SQLite implementation of permanent logical-operation reservations."""

    def get(self, key: PaperExecutionIdempotencyKey) -> RecordLoadResult:
        record = self.load_record(key)
        if record is None:
            return RecordLoadResult(
                status=ExecutionPersistenceResultStatus.NOT_FOUND,
                schema_version=CURRENT_SCHEMA_VERSION,
            )
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.LOADED,
            record_fingerprint=record.record_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )

    def load_record(
        self, key: PaperExecutionIdempotencyKey
    ) -> ExecutionIdempotencyRecord | None:
        row = self._row(
            "SELECT * FROM execution_idempotency WHERE idempotency_key = ?", (str(key),)
        )
        return _idempotency_from_row(row) if row is not None else None

    def reserve(
        self, record: ExecutionIdempotencyRecord
    ) -> IdempotencyReservationResult:
        existing = self.load_record(record.idempotency_key)
        result = _idempotency_result(record, existing)
        if result.conflict is not None:
            self._transaction.mark_conflict(result.conflict)
        elif result.status is ExecutionPersistenceResultStatus.CREATED:
            self._transaction.execute(_IDEMPOTENCY_INSERT, _idempotency_values(record))
        return result


def _aggregate_save_result(
    record: ExecutionAggregateRecord,
    existing: ExecutionAggregateRecord | None,
    expected_revision: PaperExecutionRevision,
) -> AggregateSaveResult:
    if existing is None:
        if int(expected_revision) != 0 or int(record.execution_revision) != 0:
            conflict = _conflict(
                kind=ExecutionPersistenceConflictKind.STALE_REVISION,
                code="AGGREGATE_NOT_FOUND_FOR_REVISION",
                safe_message="Aggregate does not exist at expected revision.",
                aggregate_id=record.aggregate_id,
                expected_revision=expected_revision,
            )
            return AggregateSaveResult(
                status=ExecutionPersistenceResultStatus.STALE_REVISION,
                aggregate_id=record.aggregate_id,
                expected_revision=expected_revision,
                current_revision=None,
                conflict=conflict,
                schema_version=CURRENT_SCHEMA_VERSION,
            )
        return AggregateSaveResult(
            status=ExecutionPersistenceResultStatus.CREATED,
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            current_revision=record.execution_revision,
            aggregate_fingerprint=record.record_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
    if existing.aggregate_terminal:
        conflict = _conflict(
            kind=ExecutionPersistenceConflictKind.TERMINAL_STATE_CONFLICT,
            code="AGGREGATE_TERMINAL",
            safe_message="Terminal aggregate cannot be updated.",
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            actual_revision=existing.execution_revision,
        )
        return AggregateSaveResult(
            status=ExecutionPersistenceResultStatus.ALREADY_TERMINAL,
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            current_revision=existing.execution_revision,
            conflict=conflict,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
    if existing.execution_revision != expected_revision:
        conflict = _conflict(
            kind=ExecutionPersistenceConflictKind.STALE_REVISION,
            code="STALE_AGGREGATE_REVISION",
            safe_message="Aggregate revision changed before save.",
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            actual_revision=existing.execution_revision,
        )
        return AggregateSaveResult(
            status=ExecutionPersistenceResultStatus.STALE_REVISION,
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            current_revision=existing.execution_revision,
            conflict=conflict,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
    if existing.record_fingerprint == record.record_fingerprint:
        return AggregateSaveResult(
            status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            current_revision=existing.execution_revision,
            aggregate_fingerprint=existing.record_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
    if int(record.execution_revision) != int(expected_revision) + 1:
        conflict = _conflict(
            kind=ExecutionPersistenceConflictKind.STALE_REVISION,
            code="NON_SEQUENTIAL_AGGREGATE_REVISION",
            safe_message="Aggregate revision must advance by exactly one.",
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            actual_revision=record.execution_revision,
        )
        return AggregateSaveResult(
            status=ExecutionPersistenceResultStatus.STALE_REVISION,
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            current_revision=existing.execution_revision,
            conflict=conflict,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
    return AggregateSaveResult(
        status=ExecutionPersistenceResultStatus.SAVED,
        aggregate_id=record.aggregate_id,
        expected_revision=expected_revision,
        current_revision=record.execution_revision,
        aggregate_fingerprint=record.record_fingerprint,
        schema_version=CURRENT_SCHEMA_VERSION,
    )


def _command_result(
    record: ExecutionCommandRecord, existing: ExecutionCommandRecord | None
) -> CommandRegistrationResult:
    if existing is None:
        return CommandRegistrationResult(
            status=ExecutionPersistenceResultStatus.CREATED,
            command_id=record.command_id,
            command_fingerprint=record.record_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
    if existing.canonical_payload_fingerprint == record.canonical_payload_fingerprint:
        return CommandRegistrationResult(
            status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
            command_id=record.command_id,
            command_fingerprint=existing.record_fingerprint,
            original_command_id=existing.command_id,
            original_result_fingerprint=existing.record_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
    conflict = _conflict(
        kind=ExecutionPersistenceConflictKind.COMMAND_PAYLOAD_CONFLICT,
        code="COMMAND_PAYLOAD_CONFLICT",
        safe_message="Command identity already exists with different payload.",
        aggregate_id=existing.aggregate_id,
        command_id=record.command_id,
    )
    return CommandRegistrationResult(
        status=ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
        command_id=record.command_id,
        conflict=conflict,
        schema_version=CURRENT_SCHEMA_VERSION,
    )


def _idempotency_result(
    record: ExecutionIdempotencyRecord, existing: ExecutionIdempotencyRecord | None
) -> IdempotencyReservationResult:
    if existing is None:
        return IdempotencyReservationResult(
            status=ExecutionPersistenceResultStatus.CREATED,
            idempotency_key=record.idempotency_key,
            reservation_fingerprint=record.record_fingerprint,
            original_command_id=record.command_id,
            original_result_fingerprint=record.original_result_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
    if existing.logical_operation_fingerprint == record.logical_operation_fingerprint:
        return IdempotencyReservationResult(
            status=ExecutionPersistenceResultStatus.LOGICAL_REPLAY,
            idempotency_key=record.idempotency_key,
            reservation_fingerprint=existing.record_fingerprint,
            original_command_id=existing.command_id,
            original_result_fingerprint=existing.original_result_fingerprint
            or existing.record_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
    conflict = _conflict(
        kind=ExecutionPersistenceConflictKind.IDEMPOTENCY_PAYLOAD_CONFLICT,
        code="IDEMPOTENCY_PAYLOAD_CONFLICT",
        safe_message="Idempotency key already refers to another operation.",
        aggregate_id=existing.aggregate_id,
        command_id=record.command_id,
        idempotency_key=record.idempotency_key,
    )
    return IdempotencyReservationResult(
        status=ExecutionPersistenceResultStatus.IDEMPOTENCY_CONFLICT,
        idempotency_key=record.idempotency_key,
        conflict=conflict,
        schema_version=CURRENT_SCHEMA_VERSION,
    )


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _aggregate_values(record: ExecutionAggregateRecord) -> tuple[object, ...]:
    return (
        str(record.aggregate_id),
        str(record.correlation_id),
        record.lifecycle_state.value,
        int(record.execution_revision),
        str(record.cumulative_filled_quantity),
        None if record.requested_quantity is None else str(record.requested_quantity),
        (
            None
            if record.active_broker_reference is None
            else str(record.active_broker_reference)
        ),
        int(record.outcome_unknown),
        int(record.reconciliation_required),
        int(record.command_terminal),
        int(record.aggregate_terminal),
        record.last_transition_id,
        None if record.last_command_id is None else str(record.last_command_id),
        (
            None
            if record.last_idempotency_key is None
            else str(record.last_idempotency_key)
        ),
        record.last_receipt_fingerprint,
        record.last_failure_fingerprint,
        record.mode.value,
        _timestamp(record.created_at),
        _timestamp(record.updated_at),
        str(record.schema_version),
        record.record_fingerprint,
    )


def _command_values(record: ExecutionCommandRecord) -> tuple[object, ...]:
    return (
        str(record.command_id),
        str(record.aggregate_id),
        str(record.correlation_id),
        str(record.idempotency_key),
        record.operation.value,
        int(record.expected_execution_revision),
        record.canonical_payload_fingerprint,
        record.canonical_command_json,
        record.approval_fingerprint,
        record.policy_fingerprint,
        _timestamp(record.received_at),
        record.processing_outcome.value,
        record.mode.value,
        str(record.schema_version),
        record.record_fingerprint,
    )


def _idempotency_values(record: ExecutionIdempotencyRecord) -> tuple[object, ...]:
    return (
        str(record.idempotency_key),
        record.logical_operation_fingerprint,
        str(record.command_id),
        str(record.aggregate_id),
        record.reservation_status.value,
        record.original_result_fingerprint,
        _timestamp(record.created_at),
        None if record.resolved_at is None else _timestamp(record.resolved_at),
        int(record.conflict),
        record.mode.value,
        str(record.schema_version),
        record.record_fingerprint,
    )


def _aggregate_from_row(row: sqlite3.Row) -> ExecutionAggregateRecord:
    return ExecutionAggregateRecord(
        aggregate_id=PaperExecutionAggregateId(str(row["aggregate_id"])),
        correlation_id=PaperExecutionCorrelationId(str(row["correlation_id"])),
        lifecycle_state=PaperExecutionLifecycleState(str(row["lifecycle_state"])),
        execution_revision=PaperExecutionRevision(int(row["execution_revision"])),
        cumulative_filled_quantity=Decimal(str(row["cumulative_filled_quantity"])),
        requested_quantity=(
            None
            if row["requested_quantity"] is None
            else Decimal(str(row["requested_quantity"]))
        ),
        active_broker_reference=(
            None
            if row["active_broker_reference"] is None
            else PaperBrokerOrderReference(str(row["active_broker_reference"]))
        ),
        outcome_unknown=bool(row["outcome_unknown"]),
        reconciliation_required=bool(row["reconciliation_required"]),
        command_terminal=bool(row["command_terminal"]),
        aggregate_terminal=bool(row["aggregate_terminal"]),
        last_transition_id=str(row["last_transition_id"]),
        created_at=_parse_timestamp(str(row["created_at"])),
        updated_at=_parse_timestamp(str(row["updated_at"])),
        schema_version=int(str(row["schema_version"])),
        last_command_id=(
            None
            if row["last_command_id"] is None
            else PaperExecutionCommandId(str(row["last_command_id"]))
        ),
        last_idempotency_key=(
            None
            if row["last_idempotency_key"] is None
            else PaperExecutionIdempotencyKey(str(row["last_idempotency_key"]))
        ),
        last_receipt_fingerprint=row["last_receipt_fingerprint"],
        last_failure_fingerprint=row["last_failure_fingerprint"],
        mode=PaperExecutionMode(str(row["mode"])),
    )


def _command_from_row(row: sqlite3.Row) -> ExecutionCommandRecord:
    return ExecutionCommandRecord(
        command_id=PaperExecutionCommandId(str(row["command_id"])),
        aggregate_id=PaperExecutionAggregateId(str(row["aggregate_id"])),
        correlation_id=PaperExecutionCorrelationId(str(row["correlation_id"])),
        idempotency_key=PaperExecutionIdempotencyKey(str(row["idempotency_key"])),
        operation=PaperExecutionOperation(str(row["operation"])),
        expected_execution_revision=PaperExecutionRevision(
            int(row["expected_execution_revision"])
        ),
        canonical_payload_fingerprint=str(row["canonical_payload_fingerprint"]),
        canonical_command_json=str(row["canonical_command_json"]),
        approval_fingerprint=str(row["approval_fingerprint"]),
        policy_fingerprint=str(row["policy_fingerprint"]),
        received_at=_parse_timestamp(str(row["received_at"])),
        processing_outcome=ExecutionCommandProcessingOutcome(
            str(row["processing_outcome"])
        ),
        schema_version=int(str(row["schema_version"])),
        mode=PaperExecutionMode(str(row["mode"])),
    )


def _idempotency_from_row(row: sqlite3.Row) -> ExecutionIdempotencyRecord:
    return ExecutionIdempotencyRecord(
        idempotency_key=PaperExecutionIdempotencyKey(str(row["idempotency_key"])),
        logical_operation_fingerprint=str(row["logical_operation_fingerprint"]),
        command_id=PaperExecutionCommandId(str(row["command_id"])),
        aggregate_id=PaperExecutionAggregateId(str(row["aggregate_id"])),
        reservation_status=ExecutionIdempotencyReservationStatus(
            str(row["reservation_status"])
        ),
        original_result_fingerprint=row["original_result_fingerprint"],
        created_at=_parse_timestamp(str(row["created_at"])),
        resolved_at=(
            None
            if row["resolved_at"] is None
            else _parse_timestamp(str(row["resolved_at"]))
        ),
        conflict=bool(row["conflict"]),
        schema_version=int(str(row["schema_version"])),
        mode=PaperExecutionMode(str(row["mode"])),
    )


_AGGREGATE_COLUMNS = "aggregate_id, correlation_id, lifecycle_state, execution_revision, cumulative_filled_quantity, requested_quantity, active_broker_reference, outcome_unknown, reconciliation_required, command_terminal, aggregate_terminal, last_transition_id, last_command_id, last_idempotency_key, last_receipt_fingerprint, last_failure_fingerprint, mode, created_at, updated_at, schema_version, record_fingerprint"
_AGGREGATE_INSERT = f"INSERT INTO execution_aggregates ({_AGGREGATE_COLUMNS}) VALUES ({', '.join('?' for _ in range(21))})"
_AGGREGATE_UPDATE = "UPDATE execution_aggregates SET correlation_id=?, lifecycle_state=?, execution_revision=?, cumulative_filled_quantity=?, requested_quantity=?, active_broker_reference=?, outcome_unknown=?, reconciliation_required=?, command_terminal=?, aggregate_terminal=?, last_transition_id=?, last_command_id=?, last_idempotency_key=?, last_receipt_fingerprint=?, last_failure_fingerprint=?, mode=?, created_at=?, updated_at=?, schema_version=?, record_fingerprint=? WHERE aggregate_id=? AND execution_revision=?"
_AGGREGATE_UPDATE = _AGGREGATE_UPDATE.replace(
    "WHERE aggregate_id=?", "WHERE aggregate_id=?", 1
)
_COMMAND_INSERT = (
    "INSERT INTO execution_commands (command_id, aggregate_id, correlation_id, idempotency_key, operation, expected_execution_revision, canonical_payload_fingerprint, canonical_command_json, approval_fingerprint, policy_fingerprint, received_at, processing_outcome, mode, schema_version, record_fingerprint) VALUES ("
    + ", ".join("?" for _ in range(15))
    + ")"
)
_IDEMPOTENCY_INSERT = (
    "INSERT INTO execution_idempotency (idempotency_key, logical_operation_fingerprint, command_id, aggregate_id, reservation_status, original_result_fingerprint, created_at, resolved_at, conflict, mode, schema_version, record_fingerprint) VALUES ("
    + ", ".join("?" for _ in range(12))
    + ")"
)
