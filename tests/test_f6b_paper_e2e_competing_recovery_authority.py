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


def test_competing_recovery_authority_cannot_survive_losing_terminal_race(tmp_path) -> None:
    run_prepared_recovery_runtime_restart(tmp_path)

    database_path = (tmp_path / "paper-e2e-restart.sqlite").resolve()
    request = _intake_request()
    configuration = PaperExecutionPersistenceRuntimeConfiguration(
        database_path=database_path,
        application_version="f6b-competing-recovery-authority",
        busy_timeout_ms=5_000,
    )
    winner = PaperExecutionPersistenceRuntime(configuration).start()
    loser = PaperExecutionPersistenceRuntime(configuration).start()
    try:
        with winner.unit_of_work() as unit:
            local = unit.aggregates.load_record(request.aggregate.aggregate_id)
            unit.rollback()
        assert local is not None
        assert local.lifecycle_state is PaperExecutionLifecycleState.RECONCILIATION_REQUIRED
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
        assert comparison.outcome is PaperExecutionReconciliationOutcome.OPERATOR_ACTION_REQUIRED
        history = build_reconciliation_history_record(
            aggregate_id=local.aggregate_id,
            starting_revision=local.execution_revision,
            starting_state=local.lifecycle_state,
            facts=facts,
            decision=comparison,
            recorded_at=NOW + timedelta(minutes=5),
            schema_version=SCHEMA_VERSION,
        )

        winner_recovery = build_operator_recovery_command_record(
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
        winner_idempotency = ExecutionIdempotencyRecord(
            idempotency_key=winner_recovery.idempotency_key,
            logical_operation_fingerprint=fingerprint_payload(
                "plo",
                {
                    "destination": "FILLED",
                    "reconciliation_id": history.reconciliation_id,
                },
            ),
            command_id=winner_recovery.command_id,
            aggregate_id=winner_recovery.aggregate_id,
            reservation_status=ExecutionIdempotencyReservationStatus.RESERVED,
            created_at=NOW + timedelta(minutes=6),
            schema_version=SCHEMA_VERSION,
        )
        winner_approval = ExecutionApprovalRecord(
            approval_fingerprint=winner_recovery.approval_fingerprint,
            bound_fingerprint=winner_recovery.canonical_payload_fingerprint,
            approval_kind="OPERATOR_CONFIRMED",
            approver_safe_reference="operator-f6b-prepared-runtime-restart",
            approved_at=NOW + timedelta(minutes=6),
            recorded_at=NOW + timedelta(minutes=6),
            schema_version=SCHEMA_VERSION,
        )

        loser_recovery = build_operator_recovery_command_record(
            reconciliation=history,
            destination=PaperExecutionLifecycleState.FILLED,
            command_id=PaperExecutionCommandId.from_seed(
                "f6b-e2e", "competing-recovery-authority"
            ),
            correlation_id=local.correlation_id,
            idempotency_key=PaperExecutionIdempotencyKey.from_seed(
                "f6b-e2e", "competing-recovery-authority"
            ),
            approval_fingerprint=fingerprint_payload(
                "pap", {"operator": "f6b-competing-recovery-approved"}
            ),
            policy_fingerprint=fingerprint_payload(
                "pps", {"policy": "f6b-competing-recovery"}
            ),
            received_at=NOW + timedelta(minutes=6, seconds=1),
            schema_version=SCHEMA_VERSION,
        )
        loser_idempotency = ExecutionIdempotencyRecord(
            idempotency_key=loser_recovery.idempotency_key,
            logical_operation_fingerprint=fingerprint_payload(
                "plo",
                {
                    "destination": "FILLED",
                    "reconciliation_id": history.reconciliation_id,
                    "authority": "competing",
                },
            ),
            command_id=loser_recovery.command_id,
            aggregate_id=loser_recovery.aggregate_id,
            reservation_status=ExecutionIdempotencyReservationStatus.RESERVED,
            created_at=NOW + timedelta(minutes=6, seconds=1),
            schema_version=SCHEMA_VERSION,
        )
        loser_approval = ExecutionApprovalRecord(
            approval_fingerprint=loser_recovery.approval_fingerprint,
            bound_fingerprint=loser_recovery.canonical_payload_fingerprint,
            approval_kind="OPERATOR_CONFIRMED",
            approver_safe_reference="operator-f6b-competing-recovery",
            approved_at=NOW + timedelta(minutes=6, seconds=1),
            recorded_at=NOW + timedelta(minutes=6, seconds=1),
            schema_version=SCHEMA_VERSION,
        )

        current = PaperExecutionLifecycle(
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
        context = PaperExecutionTransitionContext(
            expected_revision=local.execution_revision,
            approval_binding_valid=True,
            approval_time_valid=True,
            policy_compatible=True,
            reconciliation_outcome=PaperExecutionReconciliationOutcome.OPERATOR_ACTION_REQUIRED,
            reconciliation_destination=PaperExecutionLifecycleState.FILLED,
        )

        def decision_for(recovery):
            event = PaperExecutionLifecycleInput(
                input_type=PaperExecutionLifecycleInputType.RECORD_RECONCILIATION_RESULT,
                command_id=recovery.command_id,
                aggregate_id=recovery.aggregate_id,
                correlation_id=recovery.correlation_id,
                idempotency_key=recovery.idempotency_key,
                command_payload_fingerprint=recovery.canonical_payload_fingerprint,
                idempotency_payload_fingerprint=recovery.canonical_payload_fingerprint,
            )
            decision = transition(current, event, context)
            assert decision.accepted is True
            assert decision.next_revision == PaperExecutionRevision(9)
            return event, decision

        winner_event, winner_decision = decision_for(winner_recovery)
        loser_event, loser_decision = decision_for(loser_recovery)
        assert winner_decision.transition_id != loser_decision.transition_id

        def transition_record(recovery, event, decision, record_id):
            return ExecutionTransitionRecord(
                transition_record_id=record_id,
                aggregate_id=local.aggregate_id,
                transition_id=decision.transition_id,
                source_state=decision.previous_state,
                destination_state=decision.next_state,
                previous_revision=decision.previous_revision,
                next_revision=decision.next_revision,
                lifecycle_input_kind=event.input_type,
                input_identity=history.record_fingerprint,
                command_id=recovery.command_id,
                correlation_id=recovery.correlation_id,
                idempotency_key=recovery.idempotency_key,
                replay_indicator=ExecutionReplayKind.NONE,
                side_effect_intent_kinds=tuple(
                    item.kind for item in decision.side_effect_intents
                ),
                evidence_intent_kinds=tuple(
                    item.kind for item in decision.evidence_intents
                ),
                safe_reason_code=decision.reason_code,
                recorded_at=NOW + timedelta(minutes=7),
                schema_version=SCHEMA_VERSION,
            )

        winner_transition = transition_record(
            winner_recovery,
            winner_event,
            winner_decision,
            "f6b-competing-recovery-winner",
        )
        loser_transition = transition_record(
            loser_recovery,
            loser_event,
            loser_decision,
            "f6b-competing-recovery-loser",
        )

        winner_final = replace(
            local,
            lifecycle_state=winner_decision.next_state,
            execution_revision=winner_decision.next_revision,
            outcome_unknown=winner_decision.outcome_unknown,
            reconciliation_required=winner_decision.reconciliation_required,
            command_terminal=winner_decision.command_terminal,
            aggregate_terminal=winner_decision.aggregate_terminal,
            last_transition_id=winner_decision.transition_id,
            last_command_id=winner_recovery.command_id,
            last_idempotency_key=winner_recovery.idempotency_key,
            updated_at=NOW + timedelta(minutes=7),
        )
        loser_final = replace(
            local,
            lifecycle_state=loser_decision.next_state,
            execution_revision=loser_decision.next_revision,
            outcome_unknown=loser_decision.outcome_unknown,
            reconciliation_required=loser_decision.reconciliation_required,
            command_terminal=loser_decision.command_terminal,
            aggregate_terminal=loser_decision.aggregate_terminal,
            last_transition_id=loser_decision.transition_id,
            last_command_id=loser_recovery.command_id,
            last_idempotency_key=loser_recovery.idempotency_key,
            updated_at=NOW + timedelta(minutes=7, seconds=1),
        )

        with winner.unit_of_work() as unit:
            assert unit.commands.register(winner_recovery).status is ExecutionPersistenceResultStatus.EXACT_REPLAY
            assert unit.idempotency.reserve(winner_idempotency).status is ExecutionPersistenceResultStatus.LOGICAL_REPLAY
            assert unit.approvals.record(winner_approval).status is ExecutionPersistenceResultStatus.EXACT_REPLAY
            assert unit.transitions.append(winner_transition).status is ExecutionPersistenceResultStatus.APPENDED
            assert unit.aggregates.save(
                winner_final,
                expected_revision=local.execution_revision,
            ).status is ExecutionPersistenceResultStatus.SAVED
            assert unit.commit().committed is True

        with loser.unit_of_work() as unit:
            assert unit.commands.register(loser_recovery).status is ExecutionPersistenceResultStatus.CREATED
            assert unit.idempotency.reserve(loser_idempotency).status is ExecutionPersistenceResultStatus.CREATED
            assert unit.approvals.record(loser_approval).status is ExecutionPersistenceResultStatus.CREATED
            assert unit.transitions.append(loser_transition).status is ExecutionPersistenceResultStatus.APPENDED
            losing_save = unit.aggregates.save(
                loser_final,
                expected_revision=local.execution_revision,
            )
            assert losing_save.status is ExecutionPersistenceResultStatus.ALREADY_TERMINAL
            unit.rollback()

        with winner.unit_of_work() as unit:
            durable = unit.aggregates.load_record(request.aggregate.aggregate_id)
            unit.rollback()
        assert durable is not None
        assert durable.lifecycle_state is PaperExecutionLifecycleState.FILLED
        assert durable.execution_revision == PaperExecutionRevision(9)
        assert durable.last_command_id == winner_recovery.command_id
        assert durable.last_transition_id == winner_decision.transition_id

        assert winner._connection.execute(
            "SELECT count(*) FROM execution_commands WHERE command_id=?",
            (str(loser_recovery.command_id),),
        ).fetchone()[0] == 0
        assert winner._connection.execute(
            "SELECT count(*) FROM execution_idempotency WHERE idempotency_key=?",
            (str(loser_recovery.idempotency_key),),
        ).fetchone()[0] == 0
        assert winner._connection.execute(
            "SELECT count(*) FROM execution_approvals WHERE approval_fingerprint=?",
            (loser_recovery.approval_fingerprint,),
        ).fetchone()[0] == 0
        assert winner._connection.execute(
            "SELECT count(*) FROM execution_transitions WHERE command_id=?",
            (str(loser_recovery.command_id),),
        ).fetchone()[0] == 0
        assert winner._connection.execute(
            "SELECT count(*) FROM execution_transitions WHERE command_id=?",
            (str(winner_recovery.command_id),),
        ).fetchone()[0] == 1
        assert winner._connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        loser.close()
        winner.close()
