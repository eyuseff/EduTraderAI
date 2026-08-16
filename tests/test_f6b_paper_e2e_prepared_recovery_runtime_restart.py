from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from adapters.paper_execution_persistence_runtime import PaperExecutionPersistenceRuntime
from test_f6b_paper_e2e_acceptance import NOW, SCHEMA_VERSION, _intake_request
from test_f6b_paper_e2e_operator_action_runtime_restart import (
    test_operator_action_history_survives_full_runtime_restart as run_operator_action_runtime_restart,
)
from volcanoes.application.execution.fingerprints import fingerprint_payload
from volcanoes.application.execution.identities import (
    PaperExecutionCommandId,
    PaperExecutionIdempotencyKey,
    PaperExecutionRevision,
)
from volcanoes.application.execution.lifecycle import (
    PaperExecutionLifecycleState,
    PaperExecutionReconciliationOutcome,
)
from volcanoes.application.execution.persistence.contracts import (
    ExecutionApprovalRecord,
    ExecutionIdempotencyRecord,
    ExecutionRestartDiscoveryQuery,
)
from volcanoes.application.execution.persistence.enums import (
    ExecutionIdempotencyReservationStatus,
    ExecutionPersistenceResultStatus,
)
from volcanoes.application.execution.reconciliation import (
    ReconciliationFacts,
    build_operator_recovery_command_record,
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


def test_prepared_recovery_survives_runtime_restart_without_auto_execution(tmp_path) -> None:
    run_operator_action_runtime_restart(tmp_path)

    database_path = (tmp_path / "paper-e2e-restart.sqlite").resolve()
    request = _intake_request()
    connection = open_sqlite_execution_connection(database_path)
    persistence = SqliteExecutionPersistence(connection)
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
        recovery = build_operator_recovery_command_record(
            reconciliation=history,
            destination=PaperExecutionLifecycleState.FILLED,
            command_id=PaperExecutionCommandId.from_seed(
                "f6b-e2e", "prepared-runtime-restart-recovery"
            ),
            correlation_id=local.correlation_id,
            idempotency_key=PaperExecutionIdempotencyKey.from_seed(
                "f6b-e2e", "prepared-runtime-restart-recovery"
            ),
            approval_fingerprint=fingerprint_payload(
                "pap", {"operator": "f6b-prepared-runtime-restart-approved"}
            ),
            policy_fingerprint=fingerprint_payload(
                "pps", {"policy": "f6b-prepared-runtime-restart"}
            ),
            received_at=NOW + timedelta(minutes=6),
            schema_version=SCHEMA_VERSION,
        )
        recovery_idempotency = ExecutionIdempotencyRecord(
            idempotency_key=recovery.idempotency_key,
            logical_operation_fingerprint=fingerprint_payload(
                "plo",
                {
                    "destination": "FILLED",
                    "reconciliation_id": history.reconciliation_id,
                },
            ),
            command_id=recovery.command_id,
            aggregate_id=recovery.aggregate_id,
            reservation_status=ExecutionIdempotencyReservationStatus.RESERVED,
            created_at=NOW + timedelta(minutes=6),
            schema_version=SCHEMA_VERSION,
        )
        recovery_approval = ExecutionApprovalRecord(
            approval_fingerprint=recovery.approval_fingerprint,
            bound_fingerprint=recovery.canonical_payload_fingerprint,
            approval_kind="OPERATOR_CONFIRMED",
            approver_safe_reference="operator-f6b-prepared-runtime-restart",
            approved_at=NOW + timedelta(minutes=6),
            recorded_at=NOW + timedelta(minutes=6),
            schema_version=SCHEMA_VERSION,
        )

        with persistence.unit_of_work() as unit:
            assert (
                unit.commands.register(recovery).status
                is ExecutionPersistenceResultStatus.CREATED
            )
            assert (
                unit.idempotency.reserve(recovery_idempotency).status
                is ExecutionPersistenceResultStatus.CREATED
            )
            assert (
                unit.approvals.record(recovery_approval).status
                is ExecutionPersistenceResultStatus.CREATED
            )
            assert unit.commit().committed is True
    finally:
        connection.close()

    runtime = PaperExecutionPersistenceRuntime(
        PaperExecutionPersistenceRuntimeConfiguration(
            database_path=database_path,
            application_version="f6b-prepared-recovery-runtime-restart",
            busy_timeout_ms=5_000,
        )
    ).start()
    try:
        changes_before = runtime._connection.total_changes
        with runtime.unit_of_work() as unit:
            durable = unit.aggregates.load_record(request.aggregate.aggregate_id)
            command_replay = unit.commands.register(recovery)
            idempotency_replay = unit.idempotency.reserve(recovery_idempotency)
            approval_replay = unit.approvals.record(recovery_approval)
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
        assert command_replay.status is ExecutionPersistenceResultStatus.EXACT_REPLAY
        assert idempotency_replay.status is ExecutionPersistenceResultStatus.EXACT_REPLAY
        assert approval_replay.status is ExecutionPersistenceResultStatus.EXACT_REPLAY
        assert discovered.aggregates == (durable,)
        assert discovered.complete is True
        assert runtime._connection.total_changes == changes_before

        command_row = runtime._connection.execute(
            "SELECT operation, record_fingerprint FROM execution_commands WHERE command_id=?",
            (str(recovery.command_id),),
        ).fetchone()
        assert command_row is not None
        assert command_row["operation"] == "RECONCILE"
        assert command_row["record_fingerprint"] == recovery.record_fingerprint

        idempotency_row = runtime._connection.execute(
            "SELECT command_id, record_fingerprint FROM execution_idempotency WHERE idempotency_key=?",
            (str(recovery.idempotency_key),),
        ).fetchone()
        assert idempotency_row is not None
        assert idempotency_row["command_id"] == str(recovery.command_id)
        assert idempotency_row["record_fingerprint"] == recovery_idempotency.record_fingerprint

        approval_row = runtime._connection.execute(
            "SELECT bound_fingerprint, record_fingerprint FROM execution_approvals WHERE approval_fingerprint=?",
            (recovery.approval_fingerprint,),
        ).fetchone()
        assert approval_row is not None
        assert approval_row["bound_fingerprint"] == recovery.canonical_payload_fingerprint
        assert approval_row["record_fingerprint"] == recovery_approval.record_fingerprint

        assert runtime._connection.execute(
            "SELECT count(*) FROM execution_transitions WHERE command_id=?",
            (str(recovery.command_id),),
        ).fetchone()[0] == 0
        assert runtime._connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        runtime.close()
