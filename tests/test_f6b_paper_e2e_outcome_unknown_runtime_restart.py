from __future__ import annotations

from adapters.paper_execution_persistence_runtime import PaperExecutionPersistenceRuntime
from test_f6b_paper_e2e_acceptance import SCHEMA_VERSION, _intake_request
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


def test_outcome_unknown_passes_full_runtime_restart_validation(tmp_path) -> None:
    run_outcome_unknown_restart(tmp_path)

    database_path = (tmp_path / "paper-e2e-restart.sqlite").resolve()
    runtime = PaperExecutionPersistenceRuntime(
        PaperExecutionPersistenceRuntimeConfiguration(
            database_path=database_path,
            application_version="f6b-outcome-unknown-runtime-restart",
            busy_timeout_ms=5_000,
        )
    ).start()
    request = _intake_request()
    try:
        with runtime.unit_of_work() as unit:
            durable = unit.aggregates.load_record(request.aggregate.aggregate_id)
            unit.rollback()

        discovered = runtime.discover_restart_candidates(
            ExecutionRestartDiscoveryQuery(
                lifecycle_states=(PaperExecutionLifecycleState.OUTCOME_UNKNOWN,),
                schema_version=SCHEMA_VERSION,
            )
        )

        assert durable is not None
        assert durable.lifecycle_state is PaperExecutionLifecycleState.OUTCOME_UNKNOWN
        assert durable.execution_revision == PaperExecutionRevision(7)
        assert durable.outcome_unknown is True
        assert durable.reconciliation_required is True
        assert durable.aggregate_terminal is False
        assert discovered.aggregates == (durable,)
        assert discovered.complete is True
    finally:
        runtime.close()
