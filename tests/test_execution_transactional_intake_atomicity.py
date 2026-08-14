from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor

import pytest

from volcanoes.application.execution import (
    AggregateSaveResult,
    ExecutionRestartDiscoveryQuery,
    PaperExecutionLifecycleState,
    PaperExecutionRevision,
    PaperExecutionCommandId,
    TransactionalExecutionIntakeService,
    TransactionalIntakeStatus,
    TransitionAppendResult,
)
from volcanoes.application.execution.persistence.enums import (
    ExecutionPersistenceResultStatus,
)
from volcanoes.infrastructure.execution_persistence.sqlite.unit_of_work import (
    SqliteExecutionPersistence,
)
from volcanoes.infrastructure.execution_persistence.sqlite.connection import (
    open_sqlite_execution_connection,
)

from test_execution_transactional_intake_service import SCHEMA_VERSION, _request
from test_sqlite_execution_persistence_repositories import _connection

TABLES = (
    "execution_commands",
    "execution_idempotency",
    "execution_approvals",
    "execution_aggregates",
    "execution_transitions",
)


def _counts(connection):
    return tuple(
        connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in TABLES
    )


def _with_command(request, command_id):
    return replace(
        request,
        command=replace(request.command, command_id=command_id),
        idempotency=replace(request.idempotency, command_id=command_id),
        aggregate=replace(request.aggregate, last_command_id=command_id),
        transitions=tuple(
            replace(transition, command_id=command_id)
            for transition in request.transitions
        ),
    )


def test_sqlite_intake_commits_one_atomic_restart_discoverable_handoff(
    tmp_path,
) -> None:
    connection = _connection(tmp_path)
    persistence = SqliteExecutionPersistence(connection)

    result = TransactionalExecutionIntakeService(persistence).intake(_request())

    assert result.status is TransactionalIntakeStatus.ACCEPTED_FOR_DISPATCH
    assert _counts(connection) == (1, 1, 1, 1, 5)
    with persistence.unit_of_work() as unit:
        discovered = unit.restart_discovery.discover(
            ExecutionRestartDiscoveryQuery(
                lifecycle_states=(PaperExecutionLifecycleState.DISPATCH_PENDING,),
                schema_version=SCHEMA_VERSION,
            )
        )
        unit.rollback()
    assert len(discovered.aggregates) == 1
    connection.close()


def test_sqlite_exact_replay_is_a_non_mutating_loser(tmp_path) -> None:
    connection = _connection(tmp_path)
    service = TransactionalExecutionIntakeService(
        SqliteExecutionPersistence(connection)
    )
    request = _request()
    first = service.intake(request)
    before = _counts(connection)

    loser = service.intake(request)

    assert first.status is TransactionalIntakeStatus.ACCEPTED_FOR_DISPATCH
    assert loser.status is TransactionalIntakeStatus.EXACT_REPLAY
    assert _counts(connection) == before
    connection.close()


def test_sqlite_command_conflict_rolls_back_without_partial_mutation(tmp_path) -> None:
    connection = _connection(tmp_path)
    service = TransactionalExecutionIntakeService(
        SqliteExecutionPersistence(connection)
    )
    service.intake(_request())
    before = _counts(connection)

    result = service.intake(_request(payload_seed="MSFT"))

    assert result.status is TransactionalIntakeStatus.COMMAND_CONFLICT
    assert _counts(connection) == before
    connection.close()


def test_sqlite_idempotency_conflict_rolls_back_new_command(tmp_path) -> None:
    connection = _connection(tmp_path)
    service = TransactionalExecutionIntakeService(
        SqliteExecutionPersistence(connection)
    )
    original = _request()
    service.intake(original)
    before = _counts(connection)
    command_id = PaperExecutionCommandId.from_seed("command", "conflicting-retry")
    conflict = _with_command(_request(payload_seed="MSFT"), command_id)

    result = service.intake(conflict)

    assert result.status is TransactionalIntakeStatus.IDEMPOTENCY_CONFLICT
    assert _counts(connection) == before
    connection.close()


def test_sqlite_logical_replay_rolls_back_new_command(tmp_path) -> None:
    connection = _connection(tmp_path)
    service = TransactionalExecutionIntakeService(
        SqliteExecutionPersistence(connection)
    )
    original = _request()
    service.intake(original)
    before = _counts(connection)
    replay = _with_command(
        original, PaperExecutionCommandId.from_seed("command", "logical-retry")
    )

    result = service.intake(replay)

    assert result.status is TransactionalIntakeStatus.LOGICAL_REPLAY
    assert _counts(connection) == before
    connection.close()


def test_sqlite_approval_conflict_rolls_back_all_new_intake_records(tmp_path) -> None:
    connection = _connection(tmp_path)
    service = TransactionalExecutionIntakeService(
        SqliteExecutionPersistence(connection)
    )
    original = _request()
    service.intake(original)
    before = _counts(connection)
    conflicting = _request("MSFT", payload_seed="AAPL")
    conflicting = replace(
        conflicting,
        command=replace(
            conflicting.command,
            approval_fingerprint=original.approval.approval_fingerprint,
        ),
        approval=replace(
            original.approval,
            approver_safe_reference="conflicting-operator",
        ),
    )

    result = service.intake(conflicting)

    assert result.status is TransactionalIntakeStatus.COMMAND_CONFLICT
    assert _counts(connection) == before
    connection.close()


class _FailBeforeCommitUnit:
    def __init__(self, unit):
        self._unit = unit

    def __enter__(self):
        self._unit.__enter__()
        return self

    def __exit__(self, exc_type, exc, traceback):
        return self._unit.__exit__(exc_type, exc, traceback)

    def __getattr__(self, name):
        return getattr(self._unit, name)

    def commit(self):
        raise RuntimeError("injected failure before commit")


class _FailBeforeCommitPersistence:
    def __init__(self, persistence):
        self._persistence = persistence

    def unit_of_work(self):
        return _FailBeforeCommitUnit(self._persistence.unit_of_work())


def test_sqlite_injected_failure_before_commit_rolls_back_everything(tmp_path) -> None:
    connection = _connection(tmp_path)
    provider = _FailBeforeCommitPersistence(SqliteExecutionPersistence(connection))

    with pytest.raises(RuntimeError, match="injected failure"):
        TransactionalExecutionIntakeService(provider).intake(_request())

    assert _counts(connection) == (0, 0, 0, 0, 0)
    connection.close()


class _ConflictTransitions:
    def __init__(self, transitions):
        self._transitions = transitions
        self._calls = 0

    def append(self, transition):
        self._calls += 1
        if self._calls == 3:
            return TransitionAppendResult(
                status=ExecutionPersistenceResultStatus.STALE_REVISION,
                aggregate_id=transition.aggregate_id,
                previous_revision=transition.previous_revision,
                next_revision=None,
                schema_version=SCHEMA_VERSION,
            )
        return self._transitions.append(transition)


class _ConflictAggregates:
    def __init__(self, aggregates):
        self._aggregates = aggregates
        self._saves = 0

    def get(self, aggregate_id):
        return self._aggregates.get(aggregate_id)

    def save(self, aggregate, *, expected_revision):
        self._saves += 1
        if self._saves == 3:
            return AggregateSaveResult(
                status=ExecutionPersistenceResultStatus.STALE_REVISION,
                aggregate_id=aggregate.aggregate_id,
                expected_revision=expected_revision,
                current_revision=PaperExecutionRevision(1),
                schema_version=SCHEMA_VERSION,
            )
        return self._aggregates.save(aggregate, expected_revision=expected_revision)


class _RepositoryConflictUnit(_FailBeforeCommitUnit):
    def __init__(self, unit, *, transition_conflict=False, cas_conflict=False):
        super().__init__(unit)
        if transition_conflict:
            self.transitions = _ConflictTransitions(unit.transitions)
        if cas_conflict:
            self.aggregates = _ConflictAggregates(unit.aggregates)

    def commit(self):
        return self._unit.commit()


class _RepositoryConflictPersistence:
    def __init__(self, persistence, *, transition_conflict=False, cas_conflict=False):
        self._persistence = persistence
        self._transition_conflict = transition_conflict
        self._cas_conflict = cas_conflict

    def unit_of_work(self):
        return _RepositoryConflictUnit(
            self._persistence.unit_of_work(),
            transition_conflict=self._transition_conflict,
            cas_conflict=self._cas_conflict,
        )


@pytest.mark.parametrize(
    "provider_options, expected_status",
    (
        ({"transition_conflict": True}, TransactionalIntakeStatus.TRANSACTION_ABORTED),
        ({"cas_conflict": True}, TransactionalIntakeStatus.STALE_REVISION),
    ),
)
def test_sqlite_late_transition_or_cas_conflict_rolls_back_earlier_writes(
    tmp_path, provider_options, expected_status
) -> None:
    connection = _connection(tmp_path)
    provider = _RepositoryConflictPersistence(
        SqliteExecutionPersistence(connection), **provider_options
    )

    result = TransactionalExecutionIntakeService(provider).intake(_request())

    assert result.status is expected_status
    assert _counts(connection) == (0, 0, 0, 0, 0)
    connection.close()


def test_competing_sqlite_intakes_have_one_deterministic_non_mutating_loser(
    tmp_path,
) -> None:
    initialized = _connection(tmp_path)
    database_path = tmp_path / "execution.sqlite"
    initialized.close()

    def intake_once():
        connection = open_sqlite_execution_connection(database_path)
        try:
            return TransactionalExecutionIntakeService(
                SqliteExecutionPersistence(connection)
            ).intake(_request())
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: intake_once(), range(2)))

    assert {result.status for result in results} == {
        TransactionalIntakeStatus.ACCEPTED_FOR_DISPATCH,
        TransactionalIntakeStatus.EXACT_REPLAY,
    }
    verified = open_sqlite_execution_connection(database_path)
    assert _counts(verified) == (1, 1, 1, 1, 5)
    verified.close()
