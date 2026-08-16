from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from test_f6b_paper_e2e_acceptance import (
    NOW,
    SCHEMA_VERSION,
    _intake_request,
    _persist_reconciliation_required,
)
from volcanoes.application.execution.fingerprints import fingerprint_payload
from volcanoes.application.execution.identities import (
    PaperExecutionCommandId,
    PaperExecutionIdempotencyKey,
    PaperExecutionRevision,
)
from volcanoes.application.execution.intake import (
    TransactionalExecutionIntakeService,
    TransactionalIntakeStatus,
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
    ExecutionDispatchControlRecord,
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


def test_approved_recovery_completes_after_outcome_unknown_restart(tmp_path) -> None:
    database_path = tmp_path / "paper-e2e-restart-recovery.sqlite"
    connection = open_sqlite_execution_connection(database_path)
    apply_pending_migrations(
        connection,
        KNOWN_MIGRATIONS,
        applied_at=NOW,
        application_version="f6b-paper-e2e-restart-recovery",
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
        "f6b-paper-e2e-restart-recovery-submission",
        request.command.command_id,
        request.idempotency.idempotency_key,
    )
    service = ControlledPaperSubmissionService(
        persistence,
        synthetic_uncertain_dispatch,
        clock=lambda: NOW + timedelta(minutes=2),
    )
    result = service.apply_once(submission)
    assert result.status is ControlledSubmissionStatus.OUTCOME_UNKNOWN
    assert result.reconciliation_required is True
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
        unknown = discovered.aggregates[0]
        assert unknown.aggregate_id == request.aggregate.aggregate_id
        assert unknown.lifecycle_state is PaperExecutionLifecycleState.OUTCOME_UNKNOWN
        assert unknown.execution_revision == PaperExecutionRevision(7)
        assert unknown.outcome_unknown is True
        assert unknown.reconciliation_required is True

        reconciliation_required = _persist_reconciliation_required(
            restarted_persistence,
            unknown,
            request,
        )
        assert (
            reconciliation_required.lifecycle_state
            is PaperExecutionLifecycleState.RECONCILIATION_REQUIRED
        )
        assert reconciliation_required.execution_revision == PaperExecutionRevision(8)

        changes_before_read = reopened.total_changes
        with restarted_persistence.unit_of_work() as unit:
            local = unit.aggregates.load_record(request.aggregate.aggregate_id)
            unit.rollback()
        assert reopened.total_changes == changes_before_read
        assert local is not None
        assert local.lifecycle_state is PaperExecutionLifecycleState.RECONCILIATION_REQUIRED

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
            recorded_at=NOW + timedelta(minutes=4),
            schema_version=SCHEMA_VERSION,
        )
        with restarted_persistence.unit_of_work() as unit:
            assert (
                unit.reconciliations.record(history).status
                is ExecutionPersistenceResultStatus.CREATED
            )
            assert unit.commit().committed is True

        recovery = build_operator_recovery_command_record(
            reconciliation=history,
            destination=PaperExecutionLifecycleState.FILLED,
            command_id=PaperExecutionCommandId.from_seed(
                "f6b-e2e", "restart-recovery"
            ),
            correlation_id=local.correlation_id,
            idempotency_key=PaperExecutionIdempotencyKey.from_seed(
                "f6b-e2e", "restart-recovery"
            ),
            approval_fingerprint=fingerprint_payload(
                "pap", {"operator": "f6b-paper-e2e-restart-approved"}
            ),
            policy_fingerprint=fingerprint_payload(
                "pps", {"policy": "f6b-paper-e2e-restart-recovery"}
            ),
            received_at=NOW + timedelta(minutes=5),
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
            created_at=NOW + timedelta(minutes=5),
            schema_version=SCHEMA_VERSION,
        )
        recovery_approval = ExecutionApprovalRecord(
            approval_fingerprint=recovery.approval_fingerprint,
            bound_fingerprint=recovery.canonical_payload_fingerprint,
            approval_kind="OPERATOR_CONFIRMED",
            approver_safe_reference="operator-f6b-paper-e2e-restart",
            approved_at=NOW + timedelta(minutes=5),
            recorded_at=NOW + timedelta(minutes=5),
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
            transition_record_id="f6b-paper-e2e-restart-approved-recovery",
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
            recorded_at=NOW + timedelta(minutes=6),
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
            updated_at=NOW + timedelta(minutes=6),
        )
        with restarted_persistence.unit_of_work() as unit:
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

        with restarted_persistence.unit_of_work() as unit:
            final = unit.aggregates.load_record(request.aggregate.aggregate_id)
            unit.rollback()
        assert final is not None
        assert final.lifecycle_state is PaperExecutionLifecycleState.FILLED
        assert final.execution_revision == PaperExecutionRevision(9)
        assert final.reconciliation_required is False
        assert reopened.execute("SELECT count(*) FROM execution_commands").fetchone()[0] == 2
        assert reopened.execute("SELECT count(*) FROM execution_transitions").fetchone()[0] == 9
        assert reopened.execute(
            "SELECT count(*) FROM execution_reconciliations"
        ).fetchone()[0] == 1
        assert reopened.execute(
            "SELECT operation FROM execution_commands WHERE command_id=?",
            (str(recovery.command_id),),
        ).fetchone()[0] == "RECONCILE"
        assert reopened.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        reopened.close()
