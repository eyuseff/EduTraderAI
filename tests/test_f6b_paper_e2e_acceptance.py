from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from volcanoes.application.execution._canonical import canonical_json_text
from volcanoes.application.execution.enums import PaperExecutionOperation
from volcanoes.application.execution.fingerprints import (
    approval_fingerprint,
    command_payload_fingerprint,
    fingerprint_payload,
    policy_fingerprint,
)
from volcanoes.application.execution.identities import (
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionIdempotencyKey,
    PaperExecutionRevision,
)
from volcanoes.application.execution.intake import (
    TransactionalExecutionIntakeService,
    TransactionalIntakeRequest,
    TransactionalIntakeStatus,
)
from volcanoes.application.execution.lifecycle import (
    PaperExecutionLifecycle,
    PaperExecutionLifecycleEvidenceIntentKind,
    PaperExecutionLifecycleInput,
    PaperExecutionLifecycleInputType,
    PaperExecutionLifecycleSideEffectIntentKind,
    PaperExecutionLifecycleState,
    PaperExecutionReconciliationOutcome,
    PaperExecutionTransitionContext,
    transition,
)
from volcanoes.application.execution.persistence.contracts import (
    ExecutionAggregateRecord,
    ExecutionApprovalRecord,
    ExecutionCommandRecord,
    ExecutionDispatchControlRecord,
    ExecutionIdempotencyRecord,
    ExecutionTransitionRecord,
)
from volcanoes.application.execution.persistence.enums import (
    ExecutionCommandProcessingOutcome,
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

NOW = datetime(2026, 8, 16, 1, 30, tzinfo=UTC)
SCHEMA_VERSION = 4


def _intake_request() -> TransactionalIntakeRequest:
    aggregate_id = PaperExecutionAggregateId.from_seed("f6b-e2e", "aggregate")
    command_id = PaperExecutionCommandId.from_seed("f6b-e2e", "submit")
    correlation_id = PaperExecutionCorrelationId.from_seed("f6b-e2e", "correlation")
    idempotency_key = PaperExecutionIdempotencyKey.from_seed("f6b-e2e", "submit")
    payload = {
        "asset_class": "equity",
        "currency": "USD",
        "mode": "PAPER",
        "operation": "SUBMIT",
        "order_type": "MARKET",
        "quantity": "1",
        "side": "BUY",
        "symbol": "AAPL",
        "time_in_force": "DAY",
    }
    command = ExecutionCommandRecord(
        command_id=command_id,
        aggregate_id=aggregate_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        operation=PaperExecutionOperation.SUBMIT,
        expected_execution_revision=PaperExecutionRevision.initial(),
        canonical_payload_fingerprint=command_payload_fingerprint(payload),
        canonical_command_json=canonical_json_text(payload),
        approval_fingerprint=approval_fingerprint(("approval", "f6b-paper-e2e")),
        policy_fingerprint=policy_fingerprint(("policy", "f6b-paper-e2e")),
        received_at=NOW,
        processing_outcome=ExecutionCommandProcessingOutcome.PENDING,
        schema_version=SCHEMA_VERSION,
    )
    reservation = ExecutionIdempotencyRecord(
        idempotency_key=idempotency_key,
        logical_operation_fingerprint=fingerprint_payload("plo", payload),
        command_id=command_id,
        aggregate_id=aggregate_id,
        reservation_status=ExecutionIdempotencyReservationStatus.RESERVED,
        created_at=NOW,
        schema_version=SCHEMA_VERSION,
    )
    approval = ExecutionApprovalRecord(
        approval_fingerprint=command.approval_fingerprint,
        bound_fingerprint=command.canonical_payload_fingerprint,
        approval_kind="OPERATOR_CONFIRMED",
        approver_safe_reference="operator-f6b-paper-e2e",
        approved_at=NOW,
        recorded_at=NOW,
        schema_version=SCHEMA_VERSION,
    )
    states = (
        (
            "PX-TRN-002",
            PaperExecutionLifecycleState.CREATED,
            PaperExecutionLifecycleState.ELIGIBILITY_EVALUATED,
            PaperExecutionLifecycleInputType.RECORD_ELIGIBILITY,
        ),
        (
            "PX-TRN-005",
            PaperExecutionLifecycleState.ELIGIBILITY_EVALUATED,
            PaperExecutionLifecycleState.APPROVAL_CONFIRMED,
            PaperExecutionLifecycleInputType.RECORD_APPROVAL,
        ),
        (
            "PX-TRN-006",
            PaperExecutionLifecycleState.APPROVAL_CONFIRMED,
            PaperExecutionLifecycleState.IDEMPOTENCY_RESERVED,
            PaperExecutionLifecycleInputType.RECORD_IDEMPOTENCY_RESERVATION,
        ),
        (
            "PX-TRN-007",
            PaperExecutionLifecycleState.IDEMPOTENCY_RESERVED,
            PaperExecutionLifecycleState.READY_FOR_DISPATCH,
            PaperExecutionLifecycleInputType.PREPARE_DISPATCH,
        ),
        (
            "PX-TRN-008",
            PaperExecutionLifecycleState.READY_FOR_DISPATCH,
            PaperExecutionLifecycleState.DISPATCH_PENDING,
            PaperExecutionLifecycleInputType.RECORD_DISPATCH_PENDING,
        ),
    )
    transitions = tuple(
        ExecutionTransitionRecord(
            transition_record_id=f"f6b-paper-e2e-intake-{number}",
            aggregate_id=aggregate_id,
            transition_id=transition_id,
            source_state=source,
            destination_state=destination,
            previous_revision=PaperExecutionRevision(number - 1),
            next_revision=PaperExecutionRevision(number),
            lifecycle_input_kind=input_kind,
            input_identity=f"f6b-paper-e2e-input-{number}",
            command_id=command_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            replay_indicator=ExecutionReplayKind.NONE,
            side_effect_intent_kinds=(
                (
                    PaperExecutionLifecycleSideEffectIntentKind.WOULD_DISPATCH
                    if destination is PaperExecutionLifecycleState.DISPATCH_PENDING
                    else PaperExecutionLifecycleSideEffectIntentKind.NONE
                ),
            ),
            evidence_intent_kinds=(
                PaperExecutionLifecycleEvidenceIntentKind.LIFECYCLE_TRANSITION_ACCEPTED,
            ),
            safe_reason_code=input_kind.value,
            recorded_at=NOW + timedelta(seconds=number),
            schema_version=SCHEMA_VERSION,
        )
        for number, (transition_id, source, destination, input_kind) in enumerate(
            states, 1
        )
    )
    aggregate = ExecutionAggregateRecord(
        aggregate_id=aggregate_id,
        correlation_id=correlation_id,
        lifecycle_state=PaperExecutionLifecycleState.DISPATCH_PENDING,
        execution_revision=PaperExecutionRevision(5),
        cumulative_filled_quantity=Decimal("0"),
        requested_quantity=Decimal("1"),
        outcome_unknown=False,
        reconciliation_required=False,
        command_terminal=False,
        aggregate_terminal=False,
        last_transition_id="PX-TRN-008",
        last_command_id=command_id,
        last_idempotency_key=idempotency_key,
        created_at=NOW,
        updated_at=NOW + timedelta(seconds=5),
        schema_version=SCHEMA_VERSION,
    )
    return TransactionalIntakeRequest(
        command=command,
        idempotency=reservation,
        approval=approval,
        aggregate=aggregate,
        transitions=transitions,
        expected_revision=PaperExecutionRevision.initial(),
    )


def _persist_reconciliation_required(
    persistence: SqliteExecutionPersistence,
    aggregate: ExecutionAggregateRecord,
    request: TransactionalIntakeRequest,
) -> ExecutionAggregateRecord:
    current = PaperExecutionLifecycle(
        aggregate_id=aggregate.aggregate_id,
        state=aggregate.lifecycle_state,
        revision=aggregate.execution_revision,
        correlation_id=aggregate.correlation_id,
        last_command_id=request.command.command_id,
        broker_order_reference=aggregate.active_broker_reference,
        requested_quantity=aggregate.requested_quantity,
        cumulative_filled_quantity=aggregate.cumulative_filled_quantity,
        reconciliation_required=aggregate.reconciliation_required,
        outcome_unknown=aggregate.outcome_unknown,
        last_transition_id=aggregate.last_transition_id,
        last_receipt_fingerprint=aggregate.last_receipt_fingerprint,
    )
    event = PaperExecutionLifecycleInput(
        input_type=PaperExecutionLifecycleInputType.REQUIRE_RECONCILIATION,
        command_id=request.command.command_id,
        aggregate_id=aggregate.aggregate_id,
        correlation_id=aggregate.correlation_id,
        idempotency_key=request.idempotency.idempotency_key,
    )
    decision = transition(
        current,
        event,
        PaperExecutionTransitionContext(expected_revision=current.revision),
    )
    assert decision.accepted is True
    assert decision.next_state is PaperExecutionLifecycleState.RECONCILIATION_REQUIRED

    record = ExecutionTransitionRecord(
        transition_record_id="f6b-paper-e2e-reconciliation-required",
        aggregate_id=aggregate.aggregate_id,
        transition_id=decision.transition_id,
        source_state=decision.previous_state,
        destination_state=decision.next_state,
        previous_revision=decision.previous_revision,
        next_revision=decision.next_revision,
        lifecycle_input_kind=event.input_type,
        input_identity="f6b-paper-e2e-read-first-boundary",
        command_id=request.command.command_id,
        correlation_id=aggregate.correlation_id,
        idempotency_key=request.idempotency.idempotency_key,
        replay_indicator=ExecutionReplayKind.NONE,
        side_effect_intent_kinds=tuple(item.kind for item in decision.side_effect_intents),
        evidence_intent_kinds=tuple(item.kind for item in decision.evidence_intents),
        safe_reason_code=decision.reason_code,
        recorded_at=NOW + timedelta(minutes=3),
        schema_version=SCHEMA_VERSION,
    )
    updated = replace(
        aggregate,
        lifecycle_state=decision.next_state,
        execution_revision=decision.next_revision,
        outcome_unknown=decision.outcome_unknown,
        reconciliation_required=decision.reconciliation_required,
        command_terminal=decision.command_terminal,
        aggregate_terminal=decision.aggregate_terminal,
        last_transition_id=decision.transition_id,
        updated_at=NOW + timedelta(minutes=3),
    )
    with persistence.unit_of_work() as unit:
        assert (
            unit.transitions.append(record).status
            is ExecutionPersistenceResultStatus.APPENDED
        )
        assert (
            unit.aggregates.save(
                updated, expected_revision=decision.previous_revision
            ).status
            is ExecutionPersistenceResultStatus.SAVED
        )
        assert unit.commit().committed is True
    return updated


def test_offline_paper_e2e_unknown_reconcile_and_approved_recovery(tmp_path) -> None:
    connection = open_sqlite_execution_connection(tmp_path / "paper-e2e.sqlite")
    apply_pending_migrations(
        connection,
        KNOWN_MIGRATIONS,
        applied_at=NOW,
        application_version="f6b-paper-e2e-acceptance",
    )
    persistence = SqliteExecutionPersistence(connection)
    request = _intake_request()

    try:
        intake = TransactionalExecutionIntakeService(persistence)
        accepted = intake.intake(request)
        replay = intake.intake(request)
        assert accepted.status is TransactionalIntakeStatus.ACCEPTED_FOR_DISPATCH
        assert accepted.committed is True
        assert replay.status is TransactionalIntakeStatus.EXACT_REPLAY
        assert replay.committed is False
        assert connection.execute("SELECT count(*) FROM execution_transitions").fetchone()[0] == 5

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
                    enabled, expected_generation=control.generation
                ).status
                is ExecutionPersistenceResultStatus.SAVED
            )
            assert unit.commit().committed is True

        dispatched = []

        def synthetic_uncertain_dispatch(order):
            dispatched.append(order)
            raise RuntimeError("synthetic possible post-effect uncertainty")

        submission = ControlledSubmissionRequest(
            "f6b-paper-e2e-submission",
            request.command.command_id,
            request.idempotency.idempotency_key,
        )
        service = ControlledPaperSubmissionService(
            persistence,
            synthetic_uncertain_dispatch,
            clock=lambda: NOW + timedelta(minutes=2),
        )
        first = service.apply_once(submission)
        second = service.apply_once(submission)
        assert first.status is ControlledSubmissionStatus.OUTCOME_UNKNOWN
        assert first.reconciliation_required is True
        assert second.status is ControlledSubmissionStatus.OUTCOME_UNKNOWN
        assert len(dispatched) == 1

        changes_before_read = connection.total_changes
        with persistence.unit_of_work() as unit:
            unknown = unit.aggregates.load_record(request.aggregate.aggregate_id)
            unit.rollback()
        assert connection.total_changes == changes_before_read
        assert unknown is not None
        assert unknown.lifecycle_state is PaperExecutionLifecycleState.OUTCOME_UNKNOWN
        assert unknown.execution_revision == PaperExecutionRevision(7)
        assert unknown.outcome_unknown is True
        assert unknown.reconciliation_required is True

        reconciliation_required = _persist_reconciliation_required(
            persistence, unknown, request
        )
        assert reconciliation_required.execution_revision == PaperExecutionRevision(8)

        changes_before_reconciliation_read = connection.total_changes
        with persistence.unit_of_work() as unit:
            local = unit.aggregates.load_record(request.aggregate.aggregate_id)
            unit.rollback()
        assert connection.total_changes == changes_before_reconciliation_read
        assert local is not None

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
            recorded_at=NOW + timedelta(minutes=4),
            schema_version=SCHEMA_VERSION,
        )
        with persistence.unit_of_work() as unit:
            assert (
                unit.reconciliations.record(history).status
                is ExecutionPersistenceResultStatus.CREATED
            )
            assert unit.commit().committed is True

        recovery_approval_fingerprint = fingerprint_payload(
            "pap", {"operator": "f6b-paper-e2e-approved"}
        )
        recovery_policy_fingerprint = fingerprint_payload(
            "pps", {"policy": "f6b-paper-e2e-recovery"}
        )
        recovery = build_operator_recovery_command_record(
            reconciliation=history,
            destination=PaperExecutionLifecycleState.FILLED,
            command_id=PaperExecutionCommandId.from_seed("f6b-e2e", "recovery"),
            correlation_id=local.correlation_id,
            idempotency_key=PaperExecutionIdempotencyKey.from_seed(
                "f6b-e2e", "recovery"
            ),
            approval_fingerprint=recovery_approval_fingerprint,
            policy_fingerprint=recovery_policy_fingerprint,
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
            approver_safe_reference="operator-f6b-paper-e2e",
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
                reconciliation_outcome=PaperExecutionReconciliationOutcome.OPERATOR_ACTION_REQUIRED,
                reconciliation_destination=PaperExecutionLifecycleState.FILLED,
            ),
        )
        assert recovery_decision.accepted is True
        assert recovery_decision.next_state is PaperExecutionLifecycleState.FILLED
        assert recovery_decision.next_revision == PaperExecutionRevision(9)

        recovery_transition = ExecutionTransitionRecord(
            transition_record_id="f6b-paper-e2e-approved-recovery",
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

        with persistence.unit_of_work() as unit:
            final = unit.aggregates.load_record(request.aggregate.aggregate_id)
            unit.rollback()
        assert final is not None
        assert final.lifecycle_state is PaperExecutionLifecycleState.FILLED
        assert final.execution_revision == PaperExecutionRevision(9)
        assert final.reconciliation_required is False
        assert connection.execute("SELECT count(*) FROM execution_commands").fetchone()[0] == 2
        assert connection.execute("SELECT count(*) FROM execution_transitions").fetchone()[0] == 9
        assert connection.execute("SELECT count(*) FROM execution_reconciliations").fetchone()[0] == 1
        assert connection.execute(
            "SELECT operation FROM execution_commands WHERE command_id=?",
            (str(recovery.command_id),),
        ).fetchone()[0] == "RECONCILE"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()
