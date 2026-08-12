from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from volcanoes.application.execution import (
    AggregateSaveResult,
    CommandRegistrationResult,
    ExecutionPersistenceConflict,
    ExecutionPersistenceConflictKind,
    ExecutionPersistenceConflictSeverity,
    ExecutionPersistenceResultStatus,
    ExecutionReplayKind,
    IdempotencyReservationResult,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionIdempotencyKey,
    PaperExecutionRevision,
    RecordLoadResult,
    ReplayLookupResult,
    TransitionAppendResult,
    UnitOfWorkCommitResult,
)
from volcanoes.application.execution.persistence.errors import (
    ExecutionPersistenceInvariantError,
)

SCHEMA_VERSION = 1


def aggregate_id() -> PaperExecutionAggregateId:
    return PaperExecutionAggregateId.from_seed("aggregate", "AAPL")


def command_id() -> PaperExecutionCommandId:
    return PaperExecutionCommandId.from_seed("command", "AAPL")


def idempotency_key() -> PaperExecutionIdempotencyKey:
    return PaperExecutionIdempotencyKey.from_seed("idempotency", "AAPL")


def conflict(
    kind: ExecutionPersistenceConflictKind = (
        ExecutionPersistenceConflictKind.STALE_REVISION
    ),
) -> ExecutionPersistenceConflict:
    return ExecutionPersistenceConflict(
        kind=kind,
        severity=ExecutionPersistenceConflictSeverity.ERROR,
        code=kind.value,
        safe_message="The requested state change cannot be recorded.",
        schema_version=SCHEMA_VERSION,
        aggregate_id=aggregate_id(),
        command_id=command_id(),
        idempotency_key=idempotency_key(),
        expected_revision=PaperExecutionRevision(1),
        actual_revision=PaperExecutionRevision(2),
    )


@pytest.mark.parametrize(
    "result",
    [
        RecordLoadResult(
            status=ExecutionPersistenceResultStatus.LOADED,
            record_fingerprint="par-123",
            schema_version=SCHEMA_VERSION,
        ),
        AggregateSaveResult(
            status=ExecutionPersistenceResultStatus.SAVED,
            aggregate_id=aggregate_id(),
            expected_revision=PaperExecutionRevision(1),
            current_revision=PaperExecutionRevision(2),
            aggregate_fingerprint="par-123",
            schema_version=SCHEMA_VERSION,
        ),
        CommandRegistrationResult(
            status=ExecutionPersistenceResultStatus.CREATED,
            command_id=command_id(),
            command_fingerprint="pcm-123",
            schema_version=SCHEMA_VERSION,
        ),
        IdempotencyReservationResult(
            status=ExecutionPersistenceResultStatus.CREATED,
            idempotency_key=idempotency_key(),
            reservation_fingerprint="pir-123",
            schema_version=SCHEMA_VERSION,
        ),
        TransitionAppendResult(
            status=ExecutionPersistenceResultStatus.APPENDED,
            aggregate_id=aggregate_id(),
            previous_revision=PaperExecutionRevision(1),
            next_revision=PaperExecutionRevision(2),
            transition_fingerprint="ptr-123",
            schema_version=SCHEMA_VERSION,
        ),
        ReplayLookupResult(
            status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
            replay_kind=ExecutionReplayKind.EXACT_COMMAND,
            original_command_id=command_id(),
            original_result_fingerprint="puw-123",
            schema_version=SCHEMA_VERSION,
        ),
        UnitOfWorkCommitResult(
            status=ExecutionPersistenceResultStatus.SAVED,
            committed=True,
            schema_version=SCHEMA_VERSION,
        ),
    ],
)
def test_result_contracts_are_immutable_and_fingerprinted(result) -> None:
    with pytest.raises(FrozenInstanceError):
        result.schema_version = 2

    assert result.result_fingerprint
    assert result.to_primitive()["schema_version"] == SCHEMA_VERSION


@pytest.mark.parametrize(
    "status",
    [
        ExecutionPersistenceResultStatus.EXACT_REPLAY,
        ExecutionPersistenceResultStatus.LOGICAL_REPLAY,
        ExecutionPersistenceResultStatus.STALE_REVISION,
        ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
        ExecutionPersistenceResultStatus.IDEMPOTENCY_CONFLICT,
        ExecutionPersistenceResultStatus.NOT_FOUND,
        ExecutionPersistenceResultStatus.TRANSACTION_ABORTED,
        ExecutionPersistenceResultStatus.ALREADY_TERMINAL,
        ExecutionPersistenceResultStatus.RECONCILIATION_REQUIRED,
    ],
)
def test_record_load_result_distinguishes_expected_statuses(
    status: ExecutionPersistenceResultStatus,
) -> None:
    result = RecordLoadResult(
        status=status,
        schema_version=SCHEMA_VERSION,
        conflict=(
            conflict()
            if status
            in {
                ExecutionPersistenceResultStatus.STALE_REVISION,
                ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
                ExecutionPersistenceResultStatus.IDEMPOTENCY_CONFLICT,
                ExecutionPersistenceResultStatus.TRANSACTION_ABORTED,
            }
            else None
        ),
    )

    assert result.status is status


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (
            ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
            ExecutionPersistenceConflictKind.COMMAND_PAYLOAD_CONFLICT,
        ),
        (
            ExecutionPersistenceResultStatus.IDEMPOTENCY_CONFLICT,
            ExecutionPersistenceConflictKind.IDEMPOTENCY_PAYLOAD_CONFLICT,
        ),
        (
            ExecutionPersistenceResultStatus.STALE_REVISION,
            ExecutionPersistenceConflictKind.STALE_REVISION,
        ),
    ],
)
def test_conflict_results_are_data_not_exceptions(
    status: ExecutionPersistenceResultStatus,
    kind: ExecutionPersistenceConflictKind,
) -> None:
    result = RecordLoadResult(
        status=status,
        conflict=conflict(kind),
        schema_version=SCHEMA_VERSION,
    )

    assert result.conflict is not None
    assert result.conflict.kind is kind
    assert result.conflict.conflict_fingerprint.startswith("pco-")


def test_conflict_rejects_sensitive_message() -> None:
    with pytest.raises(ExecutionPersistenceInvariantError):
        ExecutionPersistenceConflict(
            kind=ExecutionPersistenceConflictKind.RECORD_VERSION_CONFLICT,
            severity=ExecutionPersistenceConflictSeverity.CRITICAL,
            code="RECORD_VERSION_CONFLICT",
            safe_message="secret leaked",
            schema_version=SCHEMA_VERSION,
        )


def test_aggregate_save_result_requires_expected_revision() -> None:
    result = AggregateSaveResult(
        status=ExecutionPersistenceResultStatus.STALE_REVISION,
        aggregate_id=aggregate_id(),
        expected_revision=PaperExecutionRevision(3),
        current_revision=PaperExecutionRevision(4),
        conflict=conflict(),
        schema_version=SCHEMA_VERSION,
    )

    assert result.expected_revision == PaperExecutionRevision(3)
    assert result.current_revision == PaperExecutionRevision(4)


def test_replay_lookup_separates_exact_and_logical_replay() -> None:
    exact = ReplayLookupResult(
        status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
        replay_kind=ExecutionReplayKind.EXACT_COMMAND,
        original_command_id=command_id(),
        original_result_fingerprint="puw-123",
        schema_version=SCHEMA_VERSION,
    )
    logical = ReplayLookupResult(
        status=ExecutionPersistenceResultStatus.LOGICAL_REPLAY,
        replay_kind=ExecutionReplayKind.LOGICAL_IDEMPOTENCY,
        original_command_id=command_id(),
        original_result_fingerprint="puw-123",
        schema_version=SCHEMA_VERSION,
    )

    assert exact.replay_kind is ExecutionReplayKind.EXACT_COMMAND
    assert logical.replay_kind is ExecutionReplayKind.LOGICAL_IDEMPOTENCY


def test_unit_of_work_commit_result_has_explicit_commit_flag() -> None:
    committed = UnitOfWorkCommitResult(
        status=ExecutionPersistenceResultStatus.SAVED,
        committed=True,
        schema_version=SCHEMA_VERSION,
    )
    aborted = UnitOfWorkCommitResult(
        status=ExecutionPersistenceResultStatus.TRANSACTION_ABORTED,
        committed=False,
        conflict=conflict(),
        schema_version=SCHEMA_VERSION,
    )

    assert committed.committed is True
    assert aborted.committed is False


@pytest.mark.parametrize(
    "factory",
    [
        lambda: RecordLoadResult("LOADED", SCHEMA_VERSION),
        lambda: UnitOfWorkCommitResult(
            status=ExecutionPersistenceResultStatus.SAVED,
            committed="yes",
            schema_version=SCHEMA_VERSION,
        ),
        lambda: ReplayLookupResult(
            status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
            replay_kind="EXACT_COMMAND",
            schema_version=SCHEMA_VERSION,
        ),
    ],
)
def test_result_contracts_reject_invalid_structure(factory) -> None:
    with pytest.raises(ExecutionPersistenceInvariantError):
        factory()
