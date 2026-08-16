from __future__ import annotations

from adapters.paper_execution_persistence_runtime import PaperExecutionPersistenceRuntime
from test_f6b_paper_e2e_acceptance import (
    SCHEMA_VERSION,
    _intake_request,
    _persist_reconciliation_required,
)
from test_f6b_paper_e2e_restart_acceptance import (
    test_outcome_unknown_survives_restart_without_redispatch as run_outcome_unknown_restart,
)
from volcanoes.application.execution.identities import PaperExecutionRevision
from volcanoes.application.execution.lifecycle import PaperExecutionLifecycleState
from volcanoes.application.execution.persistence.contracts import (
    ExecutionRestartDiscoveryQuery,
)
from volcanoes.application.platform.configuration import (
    PaperExecutionPersistenceRuntimeConfiguration,
)
from volcanoes.infrastructure.execution_persistence.sqlite import (
    SqliteExecutionPersistence,
    open_sqlite_execution_connection,
)


def test_reconciliation_required_passes_full_runtime_restart_validation(tmp_path) -> None:
    run_outcome_unknown_restart(tmp_path)

    database_path = (tmp_path / "paper-e2e-restart.sqlite").resolve()
    connection = open_sqlite_execution_connection(database_path)
    persistence = SqliteExecutionPersistence(connection)
    request = _intake_request()
    try:
        with persistence.unit_of_work() as unit:
            unknown = unit.aggregates.load_record(request.aggregate.aggregate_id)
            unit.rollback()
        assert unknown is not None
        assert unknown.lifecycle_state is PaperExecutionLifecycleState.OUTCOME_UNKNOWN
        assert unknown.execution_revision == PaperExecutionRevision(7)

        reconciliation_required = _persist_reconciliation_required(
            persistence,
            unknown,
            request,
        )
        assert (
            reconciliation_required.lifecycle_state
            is PaperExecutionLifecycleState.RECONCILIATION_REQUIRED
        )
        assert reconciliation_required.execution_revision == PaperExecutionRevision(8)
        assert reconciliation_required.reconciliation_required is True
    finally:
        connection.close()

    runtime = PaperExecutionPersistenceRuntime(
        PaperExecutionPersistenceRuntimeConfiguration(
            database_path=database_path,
            application_version="f6b-reconciliation-required-runtime-restart",
            busy_timeout_ms=5_000,
        )
    ).start()
    try:
        with runtime.unit_of_work() as unit:
            durable = unit.aggregates.load_record(request.aggregate.aggregate_id)
            unit.rollback()

        changes_before_discovery = runtime._connection.total_changes
        discovered = runtime.discover_restart_candidates(
            ExecutionRestartDiscoveryQuery(
                lifecycle_states=(
                    PaperExecutionLifecycleState.RECONCILIATION_REQUIRED,
                ),
                schema_version=SCHEMA_VERSION,
            )
        )

        assert durable is not None
        assert (
            durable.lifecycle_state
            is PaperExecutionLifecycleState.RECONCILIATION_REQUIRED
        )
        assert durable.execution_revision == PaperExecutionRevision(8)
        assert durable.reconciliation_required is True
        assert durable.aggregate_terminal is False
        assert discovered.aggregates == (durable,)
        assert discovered.complete is True
        assert runtime._connection.total_changes == changes_before_discovery
    finally:
        runtime.close()
