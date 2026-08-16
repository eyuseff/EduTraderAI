from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from adapters.paper_execution_persistence_runtime import PaperExecutionPersistenceRuntime
from test_f6b_paper_e2e_acceptance import NOW, SCHEMA_VERSION, _intake_request
from test_f6b_paper_e2e_reconciliation_required_runtime_restart import (
    test_reconciliation_required_passes_full_runtime_restart_validation as run_reconciliation_required_runtime_restart,
)
from volcanoes.application.execution.identities import PaperExecutionRevision
from volcanoes.application.execution.lifecycle import (
    PaperExecutionLifecycleState,
    PaperExecutionReconciliationOutcome,
)
from volcanoes.application.execution.persistence.contracts import (
    ExecutionRestartDiscoveryQuery,
)
from volcanoes.application.execution.persistence.enums import (
    ExecutionPersistenceResultStatus,
)
from volcanoes.application.execution.reconciliation import (
    ReconciliationFacts,
    build_reconciliation_history_record,
    compare_reconciliation_facts,
)
from volcanoes.application.platform.configuration import (
    PaperExecutionPersistenceRuntimeConfiguration,
)
from volcanoes.infrastructure.execution_persistence.sqlite import (
    SqliteExecutionPersistence,
    open_sqlite_execution_connection,
)


def test_operator_action_history_survives_full_runtime_restart(tmp_path) -> None:
    run_reconciliation_required_runtime_restart(tmp_path)

    database_path = (tmp_path / "paper-e2e-restart.sqlite").resolve()
    connection = open_sqlite_execution_connection(database_path)
    persistence = SqliteExecutionPersistence(connection)
    request = _intake_request()
    try:
        with persistence.unit_of_work() as unit:
            local = unit.aggregates.load_record(request.aggregate.aggregate_id)
            unit.rollback()
        assert local is not None
        assert (
            local.lifecycle_state
            is PaperExecutionLifecycleState.RECONCILIATION_REQUIRED
        )
        assert local.execution_revision == PaperExecutionRevision(8)

        facts = ReconciliationFacts(
            local_present=True,
            broker_present=True,
            local_state=local.lifecycle_state,
            broker_state=PaperExecutionLifecycleState.FILLED,
            local_filled_quantity=local.cumulative_filled_quantity,
            broker_filled_quantity=Decimal("1"),
            observation_conflict=True,
        )
        comparison = compare_reconciliation_facts(facts)
        assert (
            comparison.outcome
            is PaperExecutionReconciliationOutcome.OPERATOR_ACTION_REQUIRED
        )
        history = build_reconciliation_history_record(
            aggregate_id=local.aggregate_id,
            starting_revision=local.execution_revision,
            starting_state=local.lifecycle_state,
            facts=facts,
            decision=comparison,
            recorded_at=NOW + timedelta(minutes=5),
            schema_version=SCHEMA_VERSION,
        )
        with persistence.unit_of_work() as unit:
            assert (
                unit.reconciliations.record(history).status
                is ExecutionPersistenceResultStatus.CREATED
            )
            assert unit.commit().committed is True
    finally:
        connection.close()

    runtime = PaperExecutionPersistenceRuntime(
        PaperExecutionPersistenceRuntimeConfiguration(
            database_path=database_path,
            application_version="f6b-operator-action-runtime-restart",
            busy_timeout_ms=5_000,
        )
    ).start()
    try:
        changes_before = runtime._connection.total_changes
        with runtime.unit_of_work() as unit:
            durable = unit.aggregates.load_record(request.aggregate.aggregate_id)
            durable_history = unit.reconciliations.load_record(history.reconciliation_id)
            replay = unit.reconciliations.record(history)
            unit.rollback()

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
        assert durable_history == history
        assert replay.status is ExecutionPersistenceResultStatus.EXACT_REPLAY
        assert discovered.aggregates == (durable,)
        assert discovered.complete is True
        assert runtime._connection.total_changes == changes_before
        assert runtime._connection.execute(
            "SELECT count(*) FROM execution_reconciliations"
        ).fetchone()[0] == 1
        assert runtime._connection.execute(
            "SELECT count(*) FROM execution_commands"
        ).fetchone()[0] == 1
        assert runtime._connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        runtime.close()
