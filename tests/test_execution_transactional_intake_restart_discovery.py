from volcanoes.application.execution import (
    ExecutionRestartDiscoveryQuery,
    InMemoryExecutionPersistence,
    PaperExecutionLifecycleState,
    TransactionalExecutionIntakeService,
)

from test_execution_transactional_intake_service import SCHEMA_VERSION, _request


def test_committed_handoff_is_restart_discoverable_without_action() -> None:
    persistence = InMemoryExecutionPersistence()
    TransactionalExecutionIntakeService(persistence).intake(_request())

    with persistence.unit_of_work() as unit:
        result = unit.restart_discovery.discover(
            ExecutionRestartDiscoveryQuery(
                lifecycle_states=(PaperExecutionLifecycleState.DISPATCH_PENDING,),
                schema_version=SCHEMA_VERSION,
            )
        )
        unit.rollback()

    assert len(result.aggregates) == 1
    assert (
        result.aggregates[0].lifecycle_state
        is PaperExecutionLifecycleState.DISPATCH_PENDING
    )
    assert not hasattr(result, "dispatch")
    assert not hasattr(result, "call_broker")
