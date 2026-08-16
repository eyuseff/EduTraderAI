from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from adapters.paper_execution_persistence_runtime import PaperExecutionPersistenceRuntime
from test_f6b_paper_e2e_acceptance import NOW, SCHEMA_VERSION, _intake_request
from test_f6b_paper_e2e_prepared_recovery_runtime_restart import (
    test_prepared_recovery_survives_runtime_restart_without_auto_execution as run_prepared_recovery_runtime_restart,
)
from volcanoes.application.execution.fingerprints import fingerprint_payload
from volcanoes.application.execution.identities import (
    PaperExecutionCommandId,
    PaperExecutionIdempotencyKey,
    PaperExecutionRevision,
)
from volcanoes.application.execution.lifecycle import (
    PaperExecutionLifecycle,
    PaperExecutionLifecycleInput,
    PaperExecutionLifecycleInputType,
    PaperExecutionLifecycleState,
    PaperExecutionReconciliationOutcome,
    PaperExecutionTransitionContext,
    transition,
)
from volcanoes.application.execution.persistence.contracts import (
    ExecutionApprovalRecord,
    ExecutionIdempotencyRecord,
    ExecutionRestartDiscoveryQuery,
    ExecutionTransitionRecord,
)
from volcanoes.application.execution.persistence.enums import (
    ExecutionIdempotencyReservationStatus,
    ExecutionPersistenceResultStatus,
    ExecutionReplayKind,
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


def test_prepared_recovery_resumes_once_after_runtime_restart(tmp_path) -> None:
    run_prepared_recovery_runtime_restart(tmp_path)

    database_path = (tmp_path / "paper-e2e-restart.sqlite").resolve()
    request = _intake_request()
    configuration = PaperExecutionPersistenceRuntimeConfiguration(
        database_path=database_path,
        application_version="f6b-prepared-recovery-runtime-resume",
        busy_timeout_ms=5_000,
    )
    runtime = PaperExecutionPersistenceRuntime(configuration).start()
    try:
        with runtime.unit_of_work() as unit:
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
        recovery_event = PaperExecutionLifecycleInput(
            input_type=PaperExecutionLifecycleInputType.RECORD_RECONCILIATION_RESULT,
            command_id=recovery.command_id,
            aggregate_id=recovery.aggregate_id,
            correlation_id=recovery.correlation_id,
            idempotency_key=recovery.idempotency_key,
            command_payload_fingerprint=recovery.canonical_payload_fingerprint,
            idempotency_payload_fingerprint=recovery.canonical_payload_fingerprint,
        )
        recovery_current = PaperExecutionLifecycle(
            aggregate_id=local.aggregate_id,
            state=local.lifecycle_state,
            revision=local.execution_revision,
            correlation_id=local.correlation_id,
            requested_quantity=local.requested_quantity,
            cumulative_filled_quantity=local.cumulative_filled_quantity,
            reconciliation_required=True,
            last_transition_id=local.last_transition_id,
            last_receipt_fingerprint=local.last_receipt_fingerprint,
        )
        recovery_decision = transition(
            recovery_current,
            recovery_event,
            PaperExecutionTransitionContext(
                expected_revision=local.execution_revision,
                approval_binding_valid=True,
                approval_time_valid=True,
                policy_compatible=True,
                reconciliation_outcome=(
                    PaperExecutionReconciliationOutcome.OPERATOR_ACTION_REQUIRED
                ),
                reconciliation_destination=PaperExecutionLifecycleState.FILLED,
            ),
        )
        assert recovery_decision.accepted is True
        assert recovery_decision.next_state is PaperExecutionLifecycleState.FILLED
        assert recovery_decision.next_revision == PaperExecutionRevision(9)

        recovery_transition = ExecutionTransitionRecord(
            transition_record_id="f6b-paper-e2e-prepared-runtime-resumed-recovery",
            aggregate_id=local.aggregate_id,
            transition_id=recovery_decision.transition_id,
            source_state=recovery_decision.previous_state,
            destination_state=recovery_decision.next_state,
            previous_revision=recovery_decision.previous_revision,
            next_revision=recovery_decision.next_revision,
            lifecycle_input_kind=recovery_event.input_type,
            input_identity=history.record_fingerprint,
            command_id=recovery.command_id,
            correlation_id=recovery.correlation_id,
            idempotency_key=recovery.idempotency_key,
            replay_indicator=ExecutionReplayKind.NONE,
            side_effect_intent_kinds=tuple(
                item.kind for item in recovery_decision.side_effect_intents
            ),
            evidence_intent_kinds=tuple(
                item.kind for item in recovery_decision.evidence_intents
            ),
            safe_reason_code=recovery_decision.reason_code,
            recorded_at=NOW + timedelta(minutes=7),
            schema_version=SCHEMA_VERSION,
        )
        final_aggregate = replace(
            local,
            lifecycle_state=recovery_decision.next_state,
            execution_revision=recovery_decision.next_revision,
            outcome_unknown=recovery_decision.outcome_unknown,
            reconciliation_required=recovery_decision.reconciliation_required,
            command_terminal=recovery_decision.command_terminal,
            aggregate_terminal=recovery_decision.aggregate_terminal,
            last_transition_id=recovery_decision.transition_id,
            last_command_id=recovery.command_id,
            last_idempotency_key=recovery.idempotency_key,
            updated_at=NOW + timedelta(minutes=7),
        )

        with runtime.unit_of_work() as unit:
            assert (
                unit.commands.register(recovery).status
                is ExecutionPersistenceResultStatus.EXACT_REPLAY
            )
            assert (
                unit.idempotency.reserve(recovery_idempotency).status
                is ExecutionPersistenceResultStatus.LOGICAL_REPLAY
            )
            assert (
                unit.approvals.record(recovery_approval).status
                is ExecutionPersistenceResultStatus.EXACT_REPLAY
            )
            assert (
                unit.transitions.append(recovery_transition).status
                is ExecutionPersistenceResultStatus.APPENDED
            )
            assert (
                unit.aggregates.save(
                    final_aggregate,
                    expected_revision=recovery_decision.previous_revision,
                ).status
                is ExecutionPersistenceResultStatus.SAVED
            )
            assert unit.commit().committed is True

        with runtime.unit_of_work() as unit:
            final = unit.aggregates.load_record(request.aggregate.aggregate_id)
            transition_replay = unit.transitions.append(recovery_transition)
            unit.rollback()
        assert final is not None
        assert final.lifecycle_state is PaperExecutionLifecycleState.FILLED
        assert final.execution_revision == PaperExecutionRevision(9)
        assert final.reconciliation_required is False
        assert transition_replay.status is ExecutionPersistenceResultStatus.EXACT_REPLAY
        assert runtime._connection.execute(
            "SELECT count(*) FROM execution_commands WHERE command_id=?",
            (str(recovery.command_id),),
        ).fetchone()[0] == 1
        assert runtime._connection.execute(
            "SELECT count(*) FROM execution_idempotency WHERE idempotency_key=?",
            (str(recovery.idempotency_key),),
        ).fetchone()[0] == 1
        assert runtime._connection.execute(
            "SELECT count(*) FROM execution_approvals WHERE approval_fingerprint=?",
            (recovery.approval_fingerprint,),
        ).fetchone()[0] == 1
        assert runtime._connection.execute(
            "SELECT count(*) FROM execution_transitions WHERE command_id=?",
            (str(recovery.command_id),),
        ).fetchone()[0] == 1
        assert runtime._connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        runtime.close()

    restarted = PaperExecutionPersistenceRuntime(configuration).start()
    try:
        with restarted.unit_of_work() as unit:
            durable_final = unit.aggregates.load_record(request.aggregate.aggregate_id)
            unit.rollback()
        assert durable_final is not None
        assert durable_final.lifecycle_state is PaperExecutionLifecycleState.FILLED
        assert durable_final.execution_revision == PaperExecutionRevision(9)
        assert durable_final.reconciliation_required is False
        discovered = restarted.discover_restart_candidates(
            ExecutionRestartDiscoveryQuery(
                lifecycle_states=(
                    PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
                    PaperExecutionLifecycleState.RECONCILIATION_REQUIRED,
                ),
                schema_version=SCHEMA_VERSION,
            )
        )
        assert discovered.aggregates == ()
        assert discovered.complete is True
        assert restarted._connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        restarted.close()
