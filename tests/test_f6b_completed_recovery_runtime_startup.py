from __future__ import annotations

from adapters.paper_execution_persistence_runtime import PaperExecutionPersistenceRuntime
from test_f6b_paper_e2e_acceptance import _intake_request
from test_f6b_paper_e2e_restart_recovery_acceptance import (
    test_approved_recovery_completes_after_outcome_unknown_restart as run_restart_recovery,
)
from volcanoes.application.execution.identities import PaperExecutionRevision
from volcanoes.application.execution.lifecycle import PaperExecutionLifecycleState
from volcanoes.application.platform.configuration import (
    PaperExecutionPersistenceRuntimeConfiguration,
)


def test_completed_recovery_survives_fail_closed_runtime_startup(tmp_path) -> None:
    run_restart_recovery(tmp_path)

    database_path = (tmp_path / "paper-e2e-restart-recovery.sqlite").resolve()
    request = _intake_request()
    runtime = PaperExecutionPersistenceRuntime(
        PaperExecutionPersistenceRuntimeConfiguration(
            database_path=database_path,
            application_version="f6b-completed-recovery-runtime-startup",
            busy_timeout_ms=5_000,
        )
    ).start()
    try:
        with runtime.unit_of_work() as unit:
            final = unit.aggregates.load_record(request.aggregate.aggregate_id)
            unit.rollback()

        assert final is not None
        assert final.lifecycle_state is PaperExecutionLifecycleState.FILLED
        assert final.execution_revision == PaperExecutionRevision(9)
        assert final.reconciliation_required is False
        assert final.aggregate_terminal is True
    finally:
        runtime.close()
