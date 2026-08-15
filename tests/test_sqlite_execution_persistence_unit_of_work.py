from __future__ import annotations

import sqlite3
from threading import Barrier, Lock, Thread
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from volcanoes.application.execution.persistence.ports import (
    ExecutionAggregateRepository,
    ExecutionApprovalRepository,
    ExecutionBrokerReferenceRepository,
    ExecutionCommandRepository,
    ExecutionFailureRepository,
    ExecutionIdempotencyRepository,
    ExecutionReceiptRepository,
    ExecutionReconciliationRepository,
    ExecutionRestartDiscoveryRepository,
    ExecutionTransitionJournal,
)
from volcanoes.application.execution.persistence.unit_of_work import (
    ExecutionPersistenceSession,
    ExecutionUnitOfWork,
)
from volcanoes.application.execution.persistence.enums import (
    ExecutionPersistenceResultStatus,
)
from volcanoes.application.execution import (
    ExecutionAggregateRecord,
    ExecutionApprovalRecord,
    ExecutionBrokerReferenceRecord,
    ExecutionBrokerReferenceStatus,
    ExecutionCommandProcessingOutcome,
    ExecutionCommandRecord,
    ExecutionIdempotencyRecord,
    ExecutionIdempotencyReservationStatus,
    PaperBrokerOrderReference,
    PaperExecutionAggregateId,
    PaperExecutionApprovalKind,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionFailureKind,
    PaperExecutionIdempotencyKey,
    PaperExecutionLifecycleState,
    PaperExecutionMode,
    PaperExecutionOperation,
    PaperExecutionRevision,
)
from volcanoes.application.execution.persistence import ExecutionDispatchControlRecord
from volcanoes.application.execution._canonical import canonical_json_text
from volcanoes.application.execution.fingerprints import (
    command_payload_fingerprint,
    fingerprint_payload,
)
from volcanoes.application.execution.submission import (
    ControlledPaperSubmissionService,
    ControlledSubmissionRequest,
    ControlledSubmissionStatus,
    DispatchFailurePhase,
    PaperDispatchFailure,
    PaperDispatchObservation,
)
from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionConfigurationError,
    SqliteExecutionSchemaError,
    SqliteExecutionTransactionError,
)
from volcanoes.infrastructure.execution_persistence.sqlite.unit_of_work import (
    SqliteExecutionPersistence,
    SqliteExecutionUnitOfWork,
    _SqliteExecutionTransaction,
)
from test_execution_persistence_in_memory_repositories import (
    failure_record,
    receipt_record,
)
from test_sqlite_execution_persistence_repositories import (
    _aggregate,
    _command,
    _connection,
    _idempotency,
    _transition,
)

DISPATCH_NOW = datetime(2026, 8, 14, tzinfo=UTC)


def _seed_dispatch_authority(
    persistence: SqliteExecutionPersistence,
) -> ControlledSubmissionRequest:
    command_id = PaperExecutionCommandId("pec-" + "1" * 64)
    aggregate_id = PaperExecutionAggregateId("pea-" + "2" * 64)
    correlation_id = PaperExecutionCorrelationId("pcr-" + "3" * 64)
    idempotency_key = PaperExecutionIdempotencyKey("pik-" + "4" * 64)
    payload = {
        "asset_class": "equity",
        "currency": "USD",
        "mode": "PAPER",
        "operation": "SUBMIT",
        "order_type": "MARKET",
        "quantity": "1",
        "side": "BUY",
        "symbol": "AAPL",
        "time_in_force": "DAY",
    }
    payload_fingerprint = command_payload_fingerprint(payload)
    approval_fingerprint = fingerprint_payload("pap", ("dispatch-approval",))
    policy_fingerprint = fingerprint_payload("pps", ("dispatch-policy",))
    aggregate = ExecutionAggregateRecord(
        aggregate_id,
        correlation_id,
        PaperExecutionLifecycleState.DISPATCH_PENDING,
        PaperExecutionRevision.initial(),
        Decimal("0"),
        False,
        False,
        False,
        False,
        "PX-TRN-008",
        DISPATCH_NOW,
        DISPATCH_NOW,
        4,
        requested_quantity=Decimal("1"),
        last_command_id=command_id,
        last_idempotency_key=idempotency_key,
    )
    command = ExecutionCommandRecord(
        command_id,
        aggregate_id,
        correlation_id,
        idempotency_key,
        PaperExecutionOperation.SUBMIT,
        PaperExecutionRevision.initial(),
        payload_fingerprint,
        canonical_json_text(payload),
        approval_fingerprint,
        policy_fingerprint,
        DISPATCH_NOW,
        ExecutionCommandProcessingOutcome.ACCEPTED,
        4,
    )
    reservation = ExecutionIdempotencyRecord(
        idempotency_key,
        fingerprint_payload("plo", ("dispatch",)),
        command_id,
        aggregate_id,
        ExecutionIdempotencyReservationStatus.RESERVED,
        DISPATCH_NOW,
        4,
    )
    approval = ExecutionApprovalRecord(
        approval_fingerprint,
        payload_fingerprint,
        PaperExecutionApprovalKind.OPERATOR.value,
        "operator.local",
        DISPATCH_NOW,
        DISPATCH_NOW,
        4,
        expires_at=DISPATCH_NOW + timedelta(hours=1),
    )
    control = ExecutionDispatchControlRecord(
        True, False, False, 2, DISPATCH_NOW, 4, PaperExecutionMode.PAPER
    )
    with persistence.unit_of_work() as unit:
        unit.aggregates.save(
            aggregate, expected_revision=PaperExecutionRevision.initial()
        )
        unit.commands.register(command)
        unit.idempotency.reserve(reservation)
        unit.approvals.record(approval)
        unit.dispatch_control.save(control, expected_generation=1)
        assert unit.commit().committed
    return ControlledSubmissionRequest("submission-1", command_id, idempotency_key)


@pytest.mark.parametrize("outcome", ("ack", "reject", "pre", "unknown"))
def test_real_sqlite_submission_outcomes_reopen_cleanly(tmp_path, outcome) -> None:
    connection = _connection(tmp_path)
    persistence = SqliteExecutionPersistence(connection)
    request = _seed_dispatch_authority(persistence)
    reference = PaperBrokerOrderReference("pbr-" + "5" * 64)
    values = {
        "ack": PaperDispatchObservation(request.submission_id, reference, True, "ACK"),
        "reject": PaperDispatchObservation(
            request.submission_id, reference, False, "REJECT"
        ),
        "pre": PaperDispatchFailure(
            request.submission_id,
            DispatchFailurePhase.PRE_DISPATCH,
            "MARKET_CLOSED",
            "Market is closed.",
            PaperExecutionFailureKind.MARKET_CLOSED,
        ),
        "unknown": PaperDispatchFailure(
            request.submission_id,
            DispatchFailurePhase.POSSIBLE_POST_DISPATCH,
            "TRANSPORT_TIMEOUT",
            "Outcome is unknown.",
            PaperExecutionFailureKind.TRANSPORT_TIMEOUT,
        ),
    }
    result = ControlledPaperSubmissionService(
        persistence, lambda order: values[outcome], clock=lambda: DISPATCH_NOW
    ).apply_once(request)
    assert result.claim_token is not None, result.reason_code
    assert (
        result.status
        is {
            "ack": ControlledSubmissionStatus.ACKNOWLEDGED,
            "reject": ControlledSubmissionStatus.BROKER_REJECTED,
            "pre": ControlledSubmissionStatus.PRE_DISPATCH_FAILURE,
            "unknown": ControlledSubmissionStatus.OUTCOME_UNKNOWN,
        }[outcome]
    ), result.reason_code
    connection.close()
    reopened = _connection(tmp_path)
    SqliteExecutionPersistence(reopened)
    replay = ControlledPaperSubmissionService(
        SqliteExecutionPersistence(reopened),
        lambda order: pytest.fail("replay invoked effect"),
        clock=lambda: DISPATCH_NOW,
    ).apply_once(request)
    assert replay.claim_token == result.claim_token
    reopened.close()


def test_two_fresh_sqlite_services_race_one_effect_and_replay_is_inert(
    tmp_path,
) -> None:
    seed_connection = _connection(tmp_path)
    request = _seed_dispatch_authority(SqliteExecutionPersistence(seed_connection))
    seed_connection.close()
    barrier = Barrier(2)
    counter_lock = Lock()
    effects = 0
    results = []
    errors = []

    def compete() -> None:
        nonlocal effects
        connection = _connection(tmp_path)
        try:
            provider = SqliteExecutionPersistence(connection)

            def effect(order):
                nonlocal effects
                with counter_lock:
                    effects += 1
                return PaperDispatchObservation(
                    request.submission_id,
                    PaperBrokerOrderReference("pbr-" + "5" * 64),
                    True,
                    "ACK",
                )

            barrier.wait()
            results.append(
                ControlledPaperSubmissionService(
                    provider, effect, clock=lambda: DISPATCH_NOW
                ).apply_once(request)
            )
        except BaseException as exc:
            errors.append(exc)
        finally:
            connection.close()

    threads = (Thread(target=compete), Thread(target=compete))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert effects == 1
    assert len(results) == 2
    assert all(
        result.status
        in {
            ControlledSubmissionStatus.ACKNOWLEDGED,
            ControlledSubmissionStatus.BLOCKED,
            ControlledSubmissionStatus.IDENTITY_CONFLICT,
        }
        for result in results
    )
    assert any(
        result.status is ControlledSubmissionStatus.ACKNOWLEDGED for result in results
    )
    reopened = _connection(tmp_path)
    rows = {
        table: reopened.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        for table in (
            "execution_dispatch_claims",
            "execution_dispatch_authorizations",
            "execution_receipts",
            "execution_dispatch_resolutions",
        )
    }
    assert rows == {
        "execution_dispatch_claims": 1,
        "execution_dispatch_authorizations": 1,
        "execution_receipts": 1,
        "execution_dispatch_resolutions": 1,
    }
    assert (
        reopened.execute("SELECT count(*) FROM execution_transitions").fetchone()[0]
        == 2
    )
    replay = ControlledPaperSubmissionService(
        SqliteExecutionPersistence(reopened),
        lambda order: pytest.fail("replay invoked effect"),
        clock=lambda: DISPATCH_NOW,
    ).apply_once(request)
    assert replay.status is ControlledSubmissionStatus.ACKNOWLEDGED
    reopened.close()


@pytest.mark.parametrize(
    ("enabled", "stop", "legacy"),
    ((False, False, False), (True, True, False), (True, False, True)),
)
def test_concurrent_control_mutation_blocks_outcome_without_partial_state(
    tmp_path, enabled, stop, legacy
) -> None:
    connection = _connection(tmp_path)
    persistence = SqliteExecutionPersistence(connection)
    request = _seed_dispatch_authority(persistence)

    def effect(order):
        competing_connection = _connection(tmp_path)
        competing = SqliteExecutionPersistence(competing_connection)
        with competing.unit_of_work() as unit:
            saved = unit.dispatch_control.save(
                ExecutionDispatchControlRecord(
                    enabled, stop, legacy, 3, DISPATCH_NOW, 4
                ),
                expected_generation=2,
            )
            assert saved.status is ExecutionPersistenceResultStatus.SAVED
            assert unit.commit().committed
        competing_connection.close()
        return PaperDispatchObservation(
            request.submission_id,
            PaperBrokerOrderReference("pbr-" + "5" * 64),
            True,
            "ACK",
        )

    result = ControlledPaperSubmissionService(
        persistence, effect, clock=lambda: DISPATCH_NOW
    ).apply_once(request)
    assert result.status is ControlledSubmissionStatus.OUTCOME_UNKNOWN
    assert result.reason_code == "DURABLE_RECORDING_FAILED"
    assert (
        connection.execute(
            "SELECT generation FROM execution_dispatch_controls"
        ).fetchone()[0]
        == 3
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


def test_real_broker_ownership_conflict_is_durable_and_replay_inert(tmp_path) -> None:
    connection = _connection(tmp_path)
    persistence = SqliteExecutionPersistence(connection)
    request = _seed_dispatch_authority(persistence)
    reference = PaperBrokerOrderReference("pbr-" + "5" * 64)
    other_aggregate = _aggregate("MSFT")
    other_command = _command("MSFT")
    owner = ExecutionBrokerReferenceRecord(
        reference,
        other_aggregate.aggregate_id,
        other_command.command_id,
        "pre-existing-owner",
        ExecutionBrokerReferenceStatus.ACTIVE,
        DISPATCH_NOW,
        DISPATCH_NOW,
        True,
        4,
    )
    with persistence.unit_of_work() as unit:
        unit.aggregates.save(
            other_aggregate,
            expected_revision=PaperExecutionRevision.initial(),
        )
        unit.commands.register(other_command)
        assert (
            unit.broker_references.register(owner).status
            is ExecutionPersistenceResultStatus.CREATED
        )
        assert unit.commit().committed
    effects = 0

    def effect(order):
        nonlocal effects
        effects += 1
        return PaperDispatchObservation(request.submission_id, reference, True, "ACK")

    result = ControlledPaperSubmissionService(
        persistence, effect, clock=lambda: DISPATCH_NOW
    ).apply_once(request)
    assert result.status is ControlledSubmissionStatus.OUTCOME_UNKNOWN
    assert result.reason_code == "BROKER_REFERENCE_OWNERSHIP_CONFLICT", (
        result,
        connection.execute(
            "SELECT resolution_status FROM execution_dispatch_resolutions"
        ).fetchall(),
    )
    assert result.reconciliation_required and result.operator_action_required
    assert result.automatic_retry is False
    assert effects == 1
    stored_owner = connection.execute(
        "SELECT aggregate_id, command_id FROM execution_broker_references "
        "WHERE broker_reference = ?",
        (str(reference),),
    ).fetchone()
    assert tuple(stored_owner) == (
        str(other_aggregate.aggregate_id),
        str(other_command.command_id),
    )
    resolution = connection.execute(
        "SELECT resolution_status, conflicting_owner_aggregate_id, "
        "conflicting_owner_command_id, conflicting_owner_record_fingerprint "
        "FROM execution_dispatch_resolutions"
    ).fetchone()
    assert tuple(resolution) == (
        "BROKER_REFERENCE_CONFLICT",
        str(other_aggregate.aggregate_id),
        str(other_command.command_id),
        owner.record_fingerprint,
    )
    connection.close()
    reopened = _connection(tmp_path)
    replay = ControlledPaperSubmissionService(
        SqliteExecutionPersistence(reopened),
        lambda order: pytest.fail("conflict replay invoked effect"),
        clock=lambda: DISPATCH_NOW,
    ).apply_once(request)
    assert replay.status is ControlledSubmissionStatus.OUTCOME_UNKNOWN
    assert replay.reason_code == "BROKER_REFERENCE_OWNERSHIP_CONFLICT"
    assert replay.conflicting_owner_aggregate_id == other_aggregate.aggregate_id
    assert replay.conflicting_owner_command_id == other_command.command_id
    assert replay.conflicting_owner_record_fingerprint == owner.record_fingerprint
    reopened.close()


def test_context_exit_rolls_back_without_closing_caller_connection() -> None:
    connection = sqlite3.connect(":memory:", isolation_level=None)
    connection.execute("CREATE TABLE probe (value INTEGER)")

    with _SqliteExecutionTransaction(connection) as transaction:
        transaction.execute("INSERT INTO probe VALUES (1)")

    assert connection.execute("SELECT count(*) FROM probe").fetchone()[0] == 0
    assert connection.execute("SELECT 1").fetchone()[0] == 1
    connection.close()


def test_commit_is_explicit_and_repeated_commit_is_replay() -> None:
    connection = sqlite3.connect(":memory:", isolation_level=None)
    connection.execute("CREATE TABLE probe (value INTEGER)")

    with _SqliteExecutionTransaction(connection) as transaction:
        transaction.execute("INSERT INTO probe VALUES (1)")
        assert transaction.commit().status is ExecutionPersistenceResultStatus.SAVED
        assert (
            transaction.commit().status is ExecutionPersistenceResultStatus.EXACT_REPLAY
        )
        transaction.rollback()

    assert connection.execute("SELECT count(*) FROM probe").fetchone()[0] == 1
    connection.close()


def test_existing_transaction_and_nested_kernel_fail_closed() -> None:
    connection = sqlite3.connect(":memory:", isolation_level=None)
    connection.execute("BEGIN")
    with pytest.raises(SqliteExecutionTransactionError):
        _SqliteExecutionTransaction(connection).__enter__()
    connection.rollback()

    with _SqliteExecutionTransaction(connection):
        with pytest.raises(SqliteExecutionTransactionError):
            _SqliteExecutionTransaction(connection).__enter__()
    connection.close()


def test_public_unit_of_work_implements_both_protocols_and_all_ports(tmp_path) -> None:
    connection = _connection(tmp_path)
    persistence = SqliteExecutionPersistence(connection)
    first = persistence.unit_of_work()
    second = persistence.unit_of_work()

    assert first is not second
    assert isinstance(first, SqliteExecutionUnitOfWork)
    assert isinstance(first, ExecutionUnitOfWork)
    assert isinstance(first, ExecutionPersistenceSession)
    expected_ports = {
        "aggregates": ExecutionAggregateRepository,
        "commands": ExecutionCommandRepository,
        "idempotency": ExecutionIdempotencyRepository,
        "transitions": ExecutionTransitionJournal,
        "broker_references": ExecutionBrokerReferenceRepository,
        "receipts": ExecutionReceiptRepository,
        "failures": ExecutionFailureRepository,
        "approvals": ExecutionApprovalRepository,
        "reconciliations": ExecutionReconciliationRepository,
        "restart_discovery": ExecutionRestartDiscoveryRepository,
    }
    assert set(expected_ports) <= vars(first).keys()
    for name, protocol in expected_ports.items():
        assert isinstance(getattr(first, name), protocol)
    connection.close()


def test_seven_session_methods_delegate_exact_repository_results(tmp_path) -> None:
    connection = _connection(tmp_path)
    aggregate = _aggregate()
    command = _command()
    reservation = _idempotency()
    transition = _transition()
    receipt = receipt_record()
    failure = failure_record()

    with SqliteExecutionPersistence(connection).unit_of_work() as unit:
        aggregate_result = unit.save_aggregate(
            aggregate, expected_revision=aggregate.execution_revision
        )
        command_result = unit.register_command(command)
        idempotency_result = unit.reserve_idempotency(reservation)
        load_result = unit.load_aggregate(aggregate)
        transition_result = unit.append_transition(transition)
        receipt_result = unit.record_receipt(receipt)
        failure_result = unit.record_failure(failure)
        assert (
            aggregate_result.status,
            aggregate_result.aggregate_fingerprint,
        ) == (ExecutionPersistenceResultStatus.CREATED, aggregate.record_fingerprint)
        assert (command_result.status, command_result.command_fingerprint) == (
            ExecutionPersistenceResultStatus.CREATED,
            command.record_fingerprint,
        )
        assert (
            idempotency_result.status,
            idempotency_result.reservation_fingerprint,
        ) == (
            ExecutionPersistenceResultStatus.CREATED,
            reservation.record_fingerprint,
        )
        assert (load_result.status, load_result.record_fingerprint) == (
            ExecutionPersistenceResultStatus.LOADED,
            aggregate.record_fingerprint,
        )
        assert (
            transition_result.status,
            transition_result.transition_fingerprint,
        ) == (
            ExecutionPersistenceResultStatus.APPENDED,
            transition.record_fingerprint,
        )
        assert (receipt_result.status, receipt_result.record_fingerprint) == (
            ExecutionPersistenceResultStatus.CREATED,
            receipt.record_fingerprint,
        )
        assert (failure_result.status, failure_result.record_fingerprint) == (
            ExecutionPersistenceResultStatus.CREATED,
            failure.record_fingerprint,
        )
        assert unit.commit().committed is True

    assert (
        connection.execute("SELECT count(*) FROM execution_commands").fetchone()[0] == 1
    )
    assert (
        connection.execute("SELECT count(*) FROM execution_idempotency").fetchone()[0]
        == 1
    )
    assert (
        connection.execute("SELECT count(*) FROM execution_aggregates").fetchone()[0]
        == 1
    )
    assert (
        connection.execute("SELECT count(*) FROM execution_transitions").fetchone()[0]
        == 1
    )
    assert (
        connection.execute("SELECT count(*) FROM execution_receipts").fetchone()[0] == 1
    )
    assert (
        connection.execute("SELECT count(*) FROM execution_failures").fetchone()[0] == 1
    )
    connection.close()


def test_public_lifecycle_rolls_back_and_fails_closed(tmp_path) -> None:
    connection = _connection(tmp_path)
    persistence = SqliteExecutionPersistence(connection)
    with persistence.unit_of_work() as unit:
        unit.save_aggregate(
            _aggregate(), expected_revision=_aggregate().execution_revision
        )
    assert (
        connection.execute("SELECT count(*) FROM execution_aggregates").fetchone()[0]
        == 0
    )

    with pytest.raises(RuntimeError):
        with persistence.unit_of_work() as unit:
            unit.save_aggregate(
                _aggregate(), expected_revision=_aggregate().execution_revision
            )
            raise RuntimeError("exceptional exit")
    assert (
        connection.execute("SELECT count(*) FROM execution_aggregates").fetchone()[0]
        == 0
    )

    unit = persistence.unit_of_work()
    with unit:
        unit.rollback()
        unit.rollback()
        with pytest.raises(SqliteExecutionTransactionError):
            unit.load_aggregate(_aggregate())
        with pytest.raises(SqliteExecutionTransactionError):
            unit.commit()
    connection.close()


def test_factory_rejects_configuration_and_schema_without_ownership(tmp_path) -> None:
    unconfigured = sqlite3.connect(":memory:", isolation_level=None)
    with pytest.raises(SqliteExecutionConfigurationError):
        SqliteExecutionPersistence(unconfigured)
    assert unconfigured.execute("SELECT 1").fetchone()[0] == 1
    unconfigured.close()

    connection = _connection(tmp_path)
    with pytest.raises(SqliteExecutionConfigurationError):
        SqliteExecutionPersistence(connection, busy_timeout_ms=60_001)
    assert connection.execute("SELECT 1").fetchone()[0] == 1

    connection.execute("DROP INDEX idx_execution_commands_idempotency_key")
    with pytest.raises(SqliteExecutionSchemaError):
        SqliteExecutionPersistence(connection)
    assert connection.execute("SELECT 1").fetchone()[0] == 1
    connection.close()
