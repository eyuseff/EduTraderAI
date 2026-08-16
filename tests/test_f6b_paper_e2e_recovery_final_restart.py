from __future__ import annotations

from test_f6b_paper_e2e_acceptance import SCHEMA_VERSION, _intake_request
from test_f6b_paper_e2e_restart_recovery_acceptance import (
    test_approved_recovery_completes_after_outcome_unknown_restart as run_restart_recovery,
)
from volcanoes.application.execution.identities import PaperExecutionRevision
from volcanoes.application.execution.lifecycle import PaperExecutionLifecycleState
from volcanoes.application.execution.persistence.contracts import (
    ExecutionRestartDiscoveryQuery,
)
from volcanoes.infrastructure.execution_persistence.sqlite import (
    SqliteExecutionPersistence,
    open_sqlite_execution_connection,
)


def test_completed_recovery_survives_second_restart_and_leaves_restart_queue_empty(
    tmp_path,
) -> None:
    run_restart_recovery(tmp_path)

    database_path = tmp_path / "paper-e2e-restart-recovery.sqlite"
    reopened = open_sqlite_execution_connection(database_path)
    persistence = SqliteExecutionPersistence(reopened)
    request = _intake_request()
    try:
        changes_before = reopened.total_changes
        with persistence.unit_of_work() as unit:
            final = unit.aggregates.load_record(request.aggregate.aggregate_id)
            discovered = unit.restart_discovery.discover(
                ExecutionRestartDiscoveryQuery(
                    lifecycle_states=(
                        PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
                        PaperExecutionLifecycleState.RECONCILIATION_REQUIRED,
                    ),
                    schema_version=SCHEMA_VERSION,
                )
            )
            unit.rollback()

        assert reopened.total_changes == changes_before
        assert final is not None
        assert final.lifecycle_state is PaperExecutionLifecycleState.FILLED
        assert final.execution_revision == PaperExecutionRevision(9)
        assert final.outcome_unknown is False
        assert final.reconciliation_required is False
        assert final.aggregate_terminal is True
        assert discovered.aggregates == ()
        assert discovered.complete is True
        assert reopened.execute("SELECT count(*) FROM execution_commands").fetchone()[0] == 2
        assert reopened.execute("SELECT count(*) FROM execution_transitions").fetchone()[0] == 9
        assert reopened.execute(
            "SELECT count(*) FROM execution_reconciliations"
        ).fetchone()[0] == 1
        assert reopened.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        reopened.close()
