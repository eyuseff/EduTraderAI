from __future__ import annotations

from datetime import timedelta

from test_f6b_paper_e2e_acceptance import NOW, SCHEMA_VERSION, _intake_request
from volcanoes.application.execution.intake import (
    TransactionalExecutionIntakeService,
    TransactionalIntakeStatus,
)
from volcanoes.application.execution.lifecycle import PaperExecutionLifecycleState
from volcanoes.application.execution.persistence.contracts import (
    ExecutionDispatchControlRecord,
    ExecutionRestartDiscoveryQuery,
)
from volcanoes.application.execution.persistence.enums import (
    ExecutionPersistenceResultStatus,
)
from volcanoes.application.execution.submission import (
    ControlledPaperSubmissionService,
    ControlledSubmissionRequest,
    ControlledSubmissionStatus,
)
from volcanoes.infrastructure.execution_persistence.sqlite import (
    KNOWN_MIGRATIONS,
    SqliteExecutionPersistence,
    apply_pending_migrations,
    open_sqlite_execution_connection,
)


def test_outcome_unknown_survives_restart_without_redispatch(tmp_path) -> None:
    database_path = tmp_path / "paper-e2e-restart.sqlite"
    connection = open_sqlite_execution_connection(database_path)
    apply_pending_migrations(
        connection,
        KNOWN_MIGRATIONS,
        applied_at=NOW,
        application_version="f6b-paper-e2e-restart-acceptance",
    )
    persistence = SqliteExecutionPersistence(connection)
    request = _intake_request()

    intake = TransactionalExecutionIntakeService(persistence)
    accepted = intake.intake(request)
    assert accepted.status is TransactionalIntakeStatus.ACCEPTED_FOR_DISPATCH
    assert accepted.committed is True

    with persistence.unit_of_work() as unit:
        control = unit.dispatch_control.get()
        enabled = ExecutionDispatchControlRecord(
            enabled=True,
            emergency_stop_active=False,
            legacy_authority_active=False,
            generation=control.generation + 1,
            updated_at=NOW + timedelta(minutes=1),
            schema_version=SCHEMA_VERSION,
        )
        assert (
            unit.dispatch_control.save(
                enabled,
                expected_generation=control.generation,
            ).status
            is ExecutionPersistenceResultStatus.SAVED
        )
        assert unit.commit().committed is True

    dispatched = []

    def synthetic_uncertain_dispatch(order):
        dispatched.append(order)
        raise RuntimeError("synthetic possible post-effect uncertainty")

    submission = ControlledSubmissionRequest(
        "f6b-paper-e2e-restart-submission",
        request.command.command_id,
        request.idempotency.idempotency_key,
    )
    service = ControlledPaperSubmissionService(
        persistence,
        synthetic_uncertain_dispatch,
        clock=lambda: NOW + timedelta(minutes=2),
    )
    first = service.apply_once(submission)
    assert first.status is ControlledSubmissionStatus.OUTCOME_UNKNOWN
    assert first.reconciliation_required is True
    assert len(dispatched) == 1
    connection.close()

    reopened = open_sqlite_execution_connection(database_path)
    restarted_persistence = SqliteExecutionPersistence(reopened)
    try:
        changes_before_discovery = reopened.total_changes
        with restarted_persistence.unit_of_work() as unit:
            discovered = unit.restart_discovery.discover(
                ExecutionRestartDiscoveryQuery(
                    lifecycle_states=(PaperExecutionLifecycleState.OUTCOME_UNKNOWN,),
                    schema_version=SCHEMA_VERSION,
                )
            )
            unit.rollback()
        assert reopened.total_changes == changes_before_discovery
        assert len(discovered.aggregates) == 1
        durable = discovered.aggregates[0]
        assert durable.aggregate_id == request.aggregate.aggregate_id
        assert durable.lifecycle_state is PaperExecutionLifecycleState.OUTCOME_UNKNOWN
        assert int(durable.execution_revision) == 7
        assert durable.outcome_unknown is True
        assert durable.reconciliation_required is True

        redispatched = []

        def forbidden_redispatch(order):
            redispatched.append(order)
            raise AssertionError("restart replay must not cross dispatch boundary")

        restarted_service = ControlledPaperSubmissionService(
            restarted_persistence,
            forbidden_redispatch,
            clock=lambda: NOW + timedelta(minutes=3),
        )
        replay = restarted_service.apply_once(submission)
        assert replay.status is ControlledSubmissionStatus.OUTCOME_UNKNOWN
        assert replay.reconciliation_required is True
        assert redispatched == []
        assert reopened.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        reopened.close()
