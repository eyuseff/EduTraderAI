from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from volcanoes.application.execution import (
    ExecutionApprovalRecord,
    ExecutionBrokerReferenceRecord,
    ExecutionBrokerReferenceStatus,
    ExecutionAggregateRecord,
    ExecutionCommandProcessingOutcome,
    ExecutionCommandRecord,
    ExecutionFailureRecord,
    ExecutionIdempotencyRecord,
    ExecutionIdempotencyReservationStatus,
    ExecutionPersistenceResultStatus,
    ExecutionPersistenceConflictKind,
    ExecutionReceiptRecord,
    ExecutionReconciliationRecord,
    ExecutionReconciliationResultClassification,
    ExecutionReplayKind,
    ExecutionRestartDiscoveryQuery,
    ExecutionTransitionRecord,
    PaperBrokerOrderReference,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionFailure,
    PaperExecutionFailureKind,
    PaperExecutionFailureSeverity,
    PaperExecutionIdempotencyKey,
    PaperExecutionLifecycleState,
    PaperExecutionLifecycleEvidenceIntentKind,
    PaperExecutionLifecycleInputType,
    PaperExecutionLifecycleSideEffectIntentKind,
    PaperExecutionMode,
    PaperExecutionOperation,
    PaperExecutionReceipt,
    PaperExecutionReceiptKind,
    PaperExecutionRevision,
    PaperExecutionStatus,
)
from volcanoes.application.execution.fingerprints import fingerprint_payload
from volcanoes.infrastructure.execution_persistence.sqlite import (
    KNOWN_MIGRATIONS,
    apply_pending_migrations,
    open_sqlite_execution_connection,
)
from volcanoes.infrastructure.execution_persistence.sqlite.repositories import (
    SqliteExecutionApprovalRepository,
    SqliteExecutionAggregateRepository,
    SqliteExecutionBrokerReferenceRepository,
    SqliteExecutionCommandRepository,
    SqliteExecutionFailureRepository,
    SqliteExecutionIdempotencyRepository,
    SqliteExecutionReceiptRepository,
    SqliteExecutionReconciliationRepository,
    SqliteExecutionRestartDiscoveryRepository,
    SqliteExecutionTransitionJournal,
)
from volcanoes.infrastructure.execution_persistence.sqlite.unit_of_work import (
    _SqliteExecutionTransaction,
)

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def _aggregate(symbol: str = "AAPL", **overrides: object) -> ExecutionAggregateRecord:
    values: dict[str, object] = {
        "aggregate_id": PaperExecutionAggregateId.from_seed("aggregate", symbol),
        "correlation_id": PaperExecutionCorrelationId.from_seed("correlation", symbol),
        "lifecycle_state": PaperExecutionLifecycleState.CREATED,
        "execution_revision": PaperExecutionRevision.initial(),
        "cumulative_filled_quantity": Decimal("0"),
        "requested_quantity": Decimal("1"),
        "outcome_unknown": False,
        "reconciliation_required": False,
        "command_terminal": False,
        "aggregate_terminal": False,
        "last_transition_id": f"transition-{symbol}-0",
        "created_at": NOW,
        "updated_at": NOW,
        "schema_version": 3,
        "mode": PaperExecutionMode.PAPER,
    }
    values.update(overrides)
    return ExecutionAggregateRecord(**values)


def _command(symbol: str = "AAPL", **overrides: object) -> ExecutionCommandRecord:
    values: dict[str, object] = {
        "command_id": PaperExecutionCommandId.from_seed("command", symbol),
        "aggregate_id": PaperExecutionAggregateId.from_seed("aggregate", symbol),
        "correlation_id": PaperExecutionCorrelationId.from_seed("correlation", symbol),
        "idempotency_key": PaperExecutionIdempotencyKey.from_seed(
            "idempotency", symbol
        ),
        "operation": PaperExecutionOperation.SUBMIT,
        "expected_execution_revision": PaperExecutionRevision.initial(),
        "canonical_payload_fingerprint": fingerprint_payload(
            "pcf", ("payload", symbol)
        ),
        "canonical_command_json": '{"operation":"SUBMIT"}',
        "approval_fingerprint": fingerprint_payload("pap", ("approval", symbol)),
        "policy_fingerprint": fingerprint_payload("pps", ("policy", symbol)),
        "received_at": NOW,
        "processing_outcome": ExecutionCommandProcessingOutcome.ACCEPTED,
        "schema_version": 3,
    }
    values.update(overrides)
    return ExecutionCommandRecord(**values)


def _idempotency(
    symbol: str = "AAPL", **overrides: object
) -> ExecutionIdempotencyRecord:
    values: dict[str, object] = {
        "idempotency_key": PaperExecutionIdempotencyKey.from_seed(
            "idempotency", symbol
        ),
        "logical_operation_fingerprint": fingerprint_payload(
            "plo", ("operation", symbol)
        ),
        "command_id": PaperExecutionCommandId.from_seed("command", symbol),
        "aggregate_id": PaperExecutionAggregateId.from_seed("aggregate", symbol),
        "reservation_status": ExecutionIdempotencyReservationStatus.RESERVED,
        "created_at": NOW,
        "schema_version": 3,
    }
    values.update(overrides)
    return ExecutionIdempotencyRecord(**values)


def _connection(tmp_path):
    connection = open_sqlite_execution_connection(tmp_path / "execution.sqlite")
    apply_pending_migrations(
        connection,
        KNOWN_MIGRATIONS,
        applied_at=NOW,
        application_version="test",
    )
    return connection


def _seed_dependencies(transaction, symbol: str = "AAPL") -> None:
    SqliteExecutionAggregateRepository(transaction).save(
        _aggregate(symbol), expected_revision=PaperExecutionRevision.initial()
    )
    SqliteExecutionCommandRepository(transaction).register(_command(symbol))
    SqliteExecutionIdempotencyRepository(transaction).reserve(_idempotency(symbol))


def _transition(symbol: str = "AAPL", **overrides: object) -> ExecutionTransitionRecord:
    values: dict[str, object] = {
        "transition_record_id": f"record-{symbol}-1",
        "aggregate_id": PaperExecutionAggregateId.from_seed("aggregate", symbol),
        "transition_id": f"transition-{symbol}-1",
        "source_state": PaperExecutionLifecycleState.CREATED,
        "destination_state": PaperExecutionLifecycleState.ELIGIBILITY_EVALUATED,
        "previous_revision": PaperExecutionRevision(0),
        "next_revision": PaperExecutionRevision(1),
        "lifecycle_input_kind": PaperExecutionLifecycleInputType.RECORD_ELIGIBILITY,
        "input_identity": f"input-{symbol}",
        "command_id": PaperExecutionCommandId.from_seed("command", symbol),
        "correlation_id": PaperExecutionCorrelationId.from_seed("correlation", symbol),
        "idempotency_key": PaperExecutionIdempotencyKey.from_seed(
            "idempotency", symbol
        ),
        "replay_indicator": ExecutionReplayKind.NONE,
        "side_effect_intent_kinds": (PaperExecutionLifecycleSideEffectIntentKind.NONE,),
        "evidence_intent_kinds": (
            PaperExecutionLifecycleEvidenceIntentKind.LIFECYCLE_TRANSITION_ACCEPTED,
        ),
        "safe_reason_code": "ELIGIBLE",
        "recorded_at": NOW,
        "schema_version": 3,
    }
    values.update(overrides)
    return ExecutionTransitionRecord(**values)


def test_aggregate_round_trip_uses_canonical_v003_values(tmp_path) -> None:
    connection = _connection(tmp_path)
    aggregate = _aggregate()

    with _SqliteExecutionTransaction(connection) as transaction:
        result = SqliteExecutionAggregateRepository(transaction).save(
            aggregate,
            expected_revision=PaperExecutionRevision.initial(),
        )
        assert result.status is ExecutionPersistenceResultStatus.CREATED
        assert transaction.commit().committed is True

    with _SqliteExecutionTransaction(connection) as transaction:
        loaded = SqliteExecutionAggregateRepository(transaction).load_record(
            aggregate.aggregate_id
        )
        assert loaded == aggregate
        transaction.rollback()
    connection.close()


def test_command_exact_replay_and_conflict_are_non_mutating(tmp_path) -> None:
    connection = _connection(tmp_path)
    aggregate = _aggregate()
    command = _command()

    with _SqliteExecutionTransaction(connection) as transaction:
        aggregates = SqliteExecutionAggregateRepository(transaction)
        commands = SqliteExecutionCommandRepository(transaction)
        aggregates.save(aggregate, expected_revision=PaperExecutionRevision.initial())
        assert (
            commands.register(command).status
            is ExecutionPersistenceResultStatus.CREATED
        )
        assert transaction.commit().committed is True

    with _SqliteExecutionTransaction(connection) as transaction:
        commands = SqliteExecutionCommandRepository(transaction)
        assert (
            commands.register(command).status
            is ExecutionPersistenceResultStatus.EXACT_REPLAY
        )
        assert transaction.commit().committed is True

    conflicting = _command(
        canonical_payload_fingerprint=fingerprint_payload("pcf", ("payload", "MSFT"))
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        result = SqliteExecutionCommandRepository(transaction).register(conflicting)
        assert result.status is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
        assert transaction.commit().committed is False
        assert transaction._rolled_back is True
    assert (
        connection.execute("SELECT count(*) FROM execution_commands").fetchone()[0] == 1
    )
    connection.close()


def test_idempotency_replay_and_conflict_are_revision_neutral(tmp_path) -> None:
    connection = _connection(tmp_path)
    aggregate = _aggregate()
    command = _command()
    reservation = _idempotency()

    with _SqliteExecutionTransaction(connection) as transaction:
        SqliteExecutionAggregateRepository(transaction).save(
            aggregate, expected_revision=PaperExecutionRevision.initial()
        )
        SqliteExecutionCommandRepository(transaction).register(command)
        assert (
            SqliteExecutionIdempotencyRepository(transaction)
            .reserve(reservation)
            .status
            is ExecutionPersistenceResultStatus.CREATED
        )
        assert transaction.commit().committed is True

    with _SqliteExecutionTransaction(connection) as transaction:
        result = SqliteExecutionIdempotencyRepository(transaction).reserve(reservation)
        assert result.status is ExecutionPersistenceResultStatus.LOGICAL_REPLAY
        assert transaction.commit().committed is True

    conflicting = _idempotency(
        logical_operation_fingerprint=fingerprint_payload("plo", ("operation", "MSFT"))
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        result = SqliteExecutionIdempotencyRepository(transaction).reserve(conflicting)
        assert result.status is ExecutionPersistenceResultStatus.IDEMPOTENCY_CONFLICT
        assert transaction.commit().committed is False
    assert (
        connection.execute("SELECT count(*) FROM execution_idempotency").fetchone()[0]
        == 1
    )
    connection.close()


def test_aggregate_cas_rejects_stale_update_without_mutation(tmp_path) -> None:
    connection = _connection(tmp_path)
    original = _aggregate()
    revised = _aggregate(
        lifecycle_state=PaperExecutionLifecycleState.ELIGIBILITY_EVALUATED,
        execution_revision=PaperExecutionRevision(1),
        last_transition_id="transition-AAPL-1",
        updated_at=NOW + timedelta(seconds=1),
    )

    with _SqliteExecutionTransaction(connection) as transaction:
        SqliteExecutionAggregateRepository(transaction).save(
            original, expected_revision=PaperExecutionRevision.initial()
        )
        transaction.commit()

    with _SqliteExecutionTransaction(connection) as transaction:
        result = SqliteExecutionAggregateRepository(transaction).save(
            revised,
            expected_revision=PaperExecutionRevision(1),
        )
        assert result.status is ExecutionPersistenceResultStatus.STALE_REVISION
        assert transaction.commit().committed is False

    with _SqliteExecutionTransaction(connection) as transaction:
        assert (
            SqliteExecutionAggregateRepository(transaction).load_record(
                original.aggregate_id
            )
            == original
        )
        transaction.rollback()
    connection.close()


def test_transition_round_trip_exact_replay_and_append_only_conflict(tmp_path) -> None:
    connection = _connection(tmp_path)
    transition = _transition()
    with _SqliteExecutionTransaction(connection) as transaction:
        _seed_dependencies(transaction)
        journal = SqliteExecutionTransitionJournal(transaction)
        assert (
            journal.append(transition).status
            is ExecutionPersistenceResultStatus.APPENDED
        )
        assert transaction.commit().committed is True
    with _SqliteExecutionTransaction(connection) as transaction:
        journal = SqliteExecutionTransitionJournal(transaction)
        assert journal.load_record(transition.transition_record_id) == transition
        assert (
            journal.append(transition).status
            is ExecutionPersistenceResultStatus.EXACT_REPLAY
        )
        transaction.commit()
    conflicting = _transition(safe_reason_code="DIFFERENT")
    with _SqliteExecutionTransaction(connection) as transaction:
        result = SqliteExecutionTransitionJournal(transaction).append(conflicting)
        assert result.status is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
        assert result.conflict is not None
        assert (
            result.conflict.kind
            is ExecutionPersistenceConflictKind.TRANSITION_REVISION_CONFLICT
        )
        assert result.conflict.code == "TRANSITION_RECORD_CONFLICT"
        assert (
            result.conflict.safe_message
            == "Transition record identity already exists with different content."
        )
        assert result.conflict.expected_revision == transition.previous_revision
        assert result.conflict.actual_revision == transition.next_revision
        assert result.conflict.aggregate_id == transition.aggregate_id
        assert result.conflict.command_id == transition.command_id
        assert transaction.commit().committed is False
    assert (
        connection.execute("SELECT count(*) FROM execution_transitions").fetchone()[0]
        == 1
    )
    connection.close()


def test_transition_revision_and_transition_identity_conflicts_are_exact(
    tmp_path,
) -> None:
    connection = _connection(tmp_path)
    original = _transition()
    with _SqliteExecutionTransaction(connection) as transaction:
        _seed_dependencies(transaction)
        SqliteExecutionTransitionJournal(transaction).append(original)
        transaction.commit()

    revision_conflict = _transition(
        transition_record_id="record-AAPL-other",
        transition_id="transition-AAPL-other",
        safe_reason_code="OTHER",
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        result = SqliteExecutionTransitionJournal(transaction).append(revision_conflict)
        assert result.status is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
        assert result.conflict is not None
        assert result.conflict.code == "TRANSITION_REVISION_CONFLICT"
        assert (
            result.conflict.safe_message
            == "Transition revision is already owned by another record."
        )
        assert result.conflict.actual_revision == original.next_revision
        assert transaction.commit().committed is False

    identity_conflict = _transition(
        transition_record_id="record-AAPL-two",
        previous_revision=PaperExecutionRevision(1),
        next_revision=PaperExecutionRevision(2),
        safe_reason_code="OTHER",
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        result = SqliteExecutionTransitionJournal(transaction).append(identity_conflict)
        assert result.status is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
        assert result.conflict is not None
        assert result.conflict.code == "TRANSITION_ID_CONFLICT"
        assert (
            result.conflict.safe_message
            == "Transition identity is already owned by another record."
        )
        assert result.conflict.actual_revision == original.next_revision
        assert transaction.commit().committed is False
    connection.close()


def test_broker_reference_round_trip_identity_conflict_and_active_uniqueness(
    tmp_path,
) -> None:
    connection = _connection(tmp_path)
    reference = ExecutionBrokerReferenceRecord(
        broker_reference=PaperBrokerOrderReference.from_seed("reference", "one"),
        aggregate_id=_aggregate().aggregate_id,
        command_id=_command().command_id,
        adapter_identity="paper-adapter",
        reference_status=ExecutionBrokerReferenceStatus.ACTIVE,
        first_seen_at=NOW,
        last_seen_at=NOW,
        active=True,
        schema_version=3,
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        _seed_dependencies(transaction)
        repository = SqliteExecutionBrokerReferenceRepository(transaction)
        assert (
            repository.register(reference).status
            is ExecutionPersistenceResultStatus.CREATED
        )
        transaction.commit()
    with _SqliteExecutionTransaction(connection) as transaction:
        repository = SqliteExecutionBrokerReferenceRepository(transaction)
        assert repository.load_record(reference.broker_reference) == reference
        assert (
            repository.register(reference).status
            is ExecutionPersistenceResultStatus.EXACT_REPLAY
        )
        transaction.commit()
    second = ExecutionBrokerReferenceRecord(
        broker_reference=PaperBrokerOrderReference.from_seed("reference", "two"),
        aggregate_id=reference.aggregate_id,
        command_id=reference.command_id,
        adapter_identity="paper-adapter",
        reference_status=ExecutionBrokerReferenceStatus.ACTIVE,
        first_seen_at=NOW,
        last_seen_at=NOW,
        active=True,
        schema_version=3,
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        result = SqliteExecutionBrokerReferenceRepository(transaction).register(second)
        assert (
            result.status is ExecutionPersistenceResultStatus.DUPLICATE_BROKER_REFERENCE
        )
        assert result.conflict is not None
        assert result.conflict.code == "ACTIVE_BROKER_REFERENCE_CONFLICT"
        assert result.conflict.aggregate_id == second.aggregate_id
        assert result.conflict.command_id == second.command_id
        assert transaction.commit().committed is False
    assert (
        connection.execute(
            "SELECT count(*) FROM execution_broker_references"
        ).fetchone()[0]
        == 1
    )
    connection.close()


def test_broker_identity_precedes_active_owner_and_inactive_references_coexist(
    tmp_path,
) -> None:
    connection = _connection(tmp_path)
    original = ExecutionBrokerReferenceRecord(
        broker_reference=PaperBrokerOrderReference.from_seed("reference", "one"),
        aggregate_id=_aggregate().aggregate_id,
        command_id=_command().command_id,
        adapter_identity="paper-adapter",
        reference_status=ExecutionBrokerReferenceStatus.ACTIVE,
        first_seen_at=NOW,
        last_seen_at=NOW,
        active=True,
        schema_version=3,
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        _seed_dependencies(transaction)
        SqliteExecutionBrokerReferenceRepository(transaction).register(original)
        transaction.commit()
    changed = ExecutionBrokerReferenceRecord(
        broker_reference=original.broker_reference,
        aggregate_id=original.aggregate_id,
        command_id=original.command_id,
        adapter_identity="other-adapter",
        reference_status=original.reference_status,
        first_seen_at=NOW,
        last_seen_at=NOW,
        active=True,
        schema_version=3,
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        result = SqliteExecutionBrokerReferenceRepository(transaction).register(changed)
        assert result.conflict is not None
        assert result.conflict.code == "BROKER_REFERENCE_CONFLICT"
        transaction.commit()
    with _SqliteExecutionTransaction(connection) as transaction:
        repository = SqliteExecutionBrokerReferenceRepository(transaction)
        for seed in ("inactive-one", "inactive-two"):
            result = repository.register(
                ExecutionBrokerReferenceRecord(
                    broker_reference=PaperBrokerOrderReference.from_seed(
                        "reference", seed
                    ),
                    aggregate_id=original.aggregate_id,
                    command_id=original.command_id,
                    adapter_identity="paper-adapter",
                    reference_status=ExecutionBrokerReferenceStatus.TERMINAL,
                    first_seen_at=NOW,
                    last_seen_at=NOW,
                    active=False,
                    schema_version=3,
                )
            )
            assert result.status is ExecutionPersistenceResultStatus.CREATED
        assert transaction.commit().committed is True
    connection.close()


def test_receipt_failure_approval_and_reconciliation_canonical_round_trips(
    tmp_path,
) -> None:
    connection = _connection(tmp_path)
    receipt = ExecutionReceiptRecord(
        receipt=PaperExecutionReceipt(
            command_id=_command().command_id,
            aggregate_id=_aggregate().aggregate_id,
            correlation_id=_aggregate().correlation_id,
            operation=PaperExecutionOperation.SUBMIT,
            receipt_kind=PaperExecutionReceiptKind.COMMAND_ACCEPTED_LOCALLY,
            status=PaperExecutionStatus.CREATED,
            observed_execution_revision=PaperExecutionRevision(0),
            observed_at=NOW,
            message_code="ACCEPTED_LOCAL",
        ),
        recorded_at=NOW,
        schema_version=3,
    )
    failure = ExecutionFailureRecord(
        failure=PaperExecutionFailure(
            failure_kind=PaperExecutionFailureKind.CONTRACT_VALIDATION,
            severity=PaperExecutionFailureSeverity.ERROR,
            code="INVALID",
            safe_message="Invalid request.",
            retryable=False,
            reconciliation_required=False,
            operator_action_required=False,
            terminal=True,
            authority_impacting=False,
        ),
        recorded_at=NOW,
        schema_version=3,
    )
    approval = ExecutionApprovalRecord(
        approval_fingerprint=fingerprint_payload("pap", ("approval", "record")),
        bound_fingerprint="bound-reference",
        approval_kind="OPERATOR",
        approver_safe_reference="operator-1",
        approved_at=NOW,
        recorded_at=NOW,
        schema_version=3,
    )
    reconciliation = ExecutionReconciliationRecord(
        reconciliation_id="reconciliation-1",
        aggregate_id=_aggregate().aggregate_id,
        starting_local_revision=PaperExecutionRevision(0),
        starting_lifecycle_state=PaperExecutionLifecycleState.CREATED,
        broker_observation_references=("observation-1",),
        result_classification=ExecutionReconciliationResultClassification.CONSISTENT,
        operator_action_required=False,
        unresolved=False,
        safe_reason_code="CONSISTENT",
        recorded_at=NOW,
        schema_version=3,
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        _seed_dependencies(transaction)
        assert (
            SqliteExecutionReceiptRepository(transaction).record(receipt).status
            is ExecutionPersistenceResultStatus.CREATED
        )
        assert (
            SqliteExecutionFailureRepository(transaction).record(failure).status
            is ExecutionPersistenceResultStatus.CREATED
        )
        assert (
            SqliteExecutionApprovalRepository(transaction).record(approval).status
            is ExecutionPersistenceResultStatus.CREATED
        )
        assert (
            SqliteExecutionReconciliationRepository(transaction)
            .record(reconciliation)
            .status
            is ExecutionPersistenceResultStatus.CREATED
        )
        transaction.commit()
    with _SqliteExecutionTransaction(connection) as transaction:
        assert (
            SqliteExecutionReceiptRepository(transaction).load_record(
                receipt.receipt.receipt_fingerprint
            )
            == receipt
        )
        assert (
            SqliteExecutionFailureRepository(transaction).load_record(
                failure.failure.failure_fingerprint
            )
            == failure
        )
        assert (
            SqliteExecutionApprovalRepository(transaction).load_record(
                approval.approval_fingerprint
            )
            == approval
        )
        assert (
            SqliteExecutionReconciliationRepository(transaction).load_record(
                reconciliation.reconciliation_id
            )
            == reconciliation
        )
        transaction.rollback()
    connection.close()


def test_receipt_and_failure_embedded_identity_conflicts_are_blocking(tmp_path) -> None:
    connection = _connection(tmp_path)
    receipt_record = ExecutionReceiptRecord(
        receipt=PaperExecutionReceipt(
            command_id=_command().command_id,
            aggregate_id=_aggregate().aggregate_id,
            correlation_id=_aggregate().correlation_id,
            operation=PaperExecutionOperation.SUBMIT,
            receipt_kind=PaperExecutionReceiptKind.COMMAND_ACCEPTED_LOCALLY,
            status=PaperExecutionStatus.CREATED,
            observed_execution_revision=PaperExecutionRevision(0),
            observed_at=NOW,
            message_code="ACCEPTED_LOCAL",
        ),
        recorded_at=NOW,
        schema_version=3,
    )
    failure_record = ExecutionFailureRecord(
        failure=PaperExecutionFailure(
            failure_kind=PaperExecutionFailureKind.CONTRACT_VALIDATION,
            severity=PaperExecutionFailureSeverity.ERROR,
            code="INVALID",
            safe_message="Invalid request.",
            retryable=False,
            reconciliation_required=False,
            operator_action_required=False,
            terminal=True,
            authority_impacting=False,
            aggregate_id=_aggregate().aggregate_id,
            command_id=_command().command_id,
            correlation_id=_aggregate().correlation_id,
        ),
        recorded_at=NOW,
        schema_version=3,
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        _seed_dependencies(transaction)
        SqliteExecutionReceiptRepository(transaction).record(receipt_record)
        SqliteExecutionFailureRepository(transaction).record(failure_record)
        transaction.commit()

    cases = (
        (
            SqliteExecutionReceiptRepository,
            ExecutionReceiptRecord(
                receipt=receipt_record.receipt,
                recorded_at=NOW + timedelta(seconds=1),
                schema_version=3,
            ),
            "RECEIPT_CONFLICT",
            "Receipt record fingerprint conflict.",
        ),
        (
            SqliteExecutionFailureRepository,
            ExecutionFailureRecord(
                failure=failure_record.failure,
                recorded_at=NOW + timedelta(seconds=1),
                schema_version=3,
            ),
            "FAILURE_CONFLICT",
            "Failure record fingerprint conflict.",
        ),
    )
    for repository_type, conflicting, code, message in cases:
        with _SqliteExecutionTransaction(connection) as transaction:
            result = repository_type(transaction).record(conflicting)
            assert result.status is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
            assert result.conflict is not None
            assert (
                result.conflict.kind
                is ExecutionPersistenceConflictKind.RECORD_VERSION_CONFLICT
            )
            assert result.conflict.code == code
            assert result.conflict.safe_message == message
            assert result.conflict.aggregate_id == _aggregate().aggregate_id
            assert result.conflict.command_id == _command().command_id
            assert transaction.commit().committed is False
    connection.close()


def test_approval_and_reconciliation_conflicts_have_exact_metadata(tmp_path) -> None:
    connection = _connection(tmp_path)
    approval = ExecutionApprovalRecord(
        approval_fingerprint=fingerprint_payload("pap", ("approval", "exact")),
        bound_fingerprint="bound-one",
        approval_kind="OPERATOR",
        approver_safe_reference="operator-1",
        approved_at=NOW,
        recorded_at=NOW,
        schema_version=3,
    )
    reconciliation = ExecutionReconciliationRecord(
        reconciliation_id="reconciliation-exact",
        aggregate_id=_aggregate().aggregate_id,
        starting_local_revision=PaperExecutionRevision(0),
        starting_lifecycle_state=PaperExecutionLifecycleState.CREATED,
        broker_observation_references=("observation-1",),
        result_classification=ExecutionReconciliationResultClassification.CONSISTENT,
        operator_action_required=False,
        unresolved=False,
        safe_reason_code="CONSISTENT",
        recorded_at=NOW,
        schema_version=3,
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        _seed_dependencies(transaction)
        SqliteExecutionApprovalRepository(transaction).record(approval)
        SqliteExecutionReconciliationRepository(transaction).record(reconciliation)
        transaction.commit()
    cases = (
        (
            SqliteExecutionApprovalRepository,
            ExecutionApprovalRecord(
                approval_fingerprint=approval.approval_fingerprint,
                bound_fingerprint="bound-two",
                approval_kind=approval.approval_kind,
                approver_safe_reference=approval.approver_safe_reference,
                approved_at=NOW,
                recorded_at=NOW,
                schema_version=3,
            ),
            "APPROVAL_CONFLICT",
            None,
        ),
        (
            SqliteExecutionReconciliationRepository,
            ExecutionReconciliationRecord(
                reconciliation_id=reconciliation.reconciliation_id,
                aggregate_id=reconciliation.aggregate_id,
                starting_local_revision=reconciliation.starting_local_revision,
                starting_lifecycle_state=reconciliation.starting_lifecycle_state,
                broker_observation_references=reconciliation.broker_observation_references,
                result_classification=reconciliation.result_classification,
                operator_action_required=False,
                unresolved=False,
                safe_reason_code="DIFFERENT",
                recorded_at=NOW,
                schema_version=3,
            ),
            "RECONCILIATION_CONFLICT",
            reconciliation.aggregate_id,
        ),
    )
    for repository_type, conflicting, code, aggregate in cases:
        with _SqliteExecutionTransaction(connection) as transaction:
            result = repository_type(transaction).record(conflicting)
            assert result.status is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
            assert result.conflict is not None
            assert result.conflict.code == code
            assert result.conflict.aggregate_id == aggregate
            assert transaction.commit().committed is False
    connection.close()


def test_slice2_optional_fields_round_trip_losslessly(tmp_path) -> None:
    connection = _connection(tmp_path)
    receipt_fingerprint = fingerprint_payload("prc", ("receipt", "optional"))
    failure_fingerprint = fingerprint_payload("pfl", ("failure", "optional"))
    replacement = PaperBrokerOrderReference.from_seed("reference", "replacement")
    transition = _transition(
        broker_observation_identity="observation-optional",
        receipt_fingerprint=receipt_fingerprint,
        failure_fingerprint=failure_fingerprint,
    )
    broker_record = ExecutionBrokerReferenceRecord(
        broker_reference=PaperBrokerOrderReference.from_seed("reference", "optional"),
        aggregate_id=_aggregate().aggregate_id,
        command_id=_command().command_id,
        adapter_identity="paper-adapter",
        reference_status=ExecutionBrokerReferenceStatus.REPLACED,
        first_seen_at=NOW,
        last_seen_at=NOW + timedelta(seconds=1),
        active=False,
        replaced_by_reference=replacement,
        schema_version=3,
    )
    receipt_record = ExecutionReceiptRecord(
        receipt=PaperExecutionReceipt(
            command_id=_command().command_id,
            aggregate_id=_aggregate().aggregate_id,
            correlation_id=_aggregate().correlation_id,
            operation=PaperExecutionOperation.SUBMIT,
            receipt_kind=PaperExecutionReceiptKind.BROKER_ACKNOWLEDGED,
            status=PaperExecutionStatus.ACKNOWLEDGED,
            observed_execution_revision=PaperExecutionRevision(1),
            observed_at=NOW,
            message_code="ACKNOWLEDGED",
            broker_order_reference=broker_record.broker_reference,
        ),
        recorded_at=NOW + timedelta(seconds=2),
        schema_version=3,
    )
    approval = ExecutionApprovalRecord(
        approval_fingerprint=fingerprint_payload("pap", ("approval", "optional")),
        bound_fingerprint="bound-optional",
        approval_kind="OPERATOR",
        approver_safe_reference="operator-optional",
        approved_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        revocation_reference="revocation-optional",
        recorded_at=NOW + timedelta(seconds=3),
        schema_version=3,
    )
    reconciliation = ExecutionReconciliationRecord(
        reconciliation_id="reconciliation-optional",
        aggregate_id=_aggregate().aggregate_id,
        starting_local_revision=PaperExecutionRevision(0),
        starting_lifecycle_state=PaperExecutionLifecycleState.CREATED,
        broker_observation_references=("observation-1", "observation-2"),
        result_classification=ExecutionReconciliationResultClassification.CONSISTENT,
        operator_action_required=False,
        unresolved=False,
        safe_reason_code="CONSISTENT",
        resulting_transition_id=transition.transition_id,
        resulting_revision=transition.next_revision,
        recorded_at=NOW + timedelta(seconds=4),
        schema_version=3,
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        _seed_dependencies(transaction)
        SqliteExecutionTransitionJournal(transaction).append(transition)
        SqliteExecutionBrokerReferenceRepository(transaction).register(broker_record)
        SqliteExecutionReceiptRepository(transaction).record(receipt_record)
        SqliteExecutionApprovalRepository(transaction).record(approval)
        SqliteExecutionReconciliationRepository(transaction).record(reconciliation)
        transaction.commit()
    with _SqliteExecutionTransaction(connection) as transaction:
        assert (
            SqliteExecutionTransitionJournal(transaction).load_record(
                transition.transition_record_id
            )
            == transition
        )
        assert (
            SqliteExecutionBrokerReferenceRepository(transaction).load_record(
                broker_record.broker_reference
            )
            == broker_record
        )
        assert (
            SqliteExecutionReceiptRepository(transaction).load_record(
                receipt_record.receipt.receipt_fingerprint
            )
            == receipt_record
        )
        assert (
            SqliteExecutionApprovalRepository(transaction).load_record(
                approval.approval_fingerprint
            )
            == approval
        )
        assert (
            SqliteExecutionReconciliationRepository(transaction).load_record(
                reconciliation.reconciliation_id
            )
            == reconciliation
        )
        transaction.rollback()
    connection.close()


def test_restart_discovery_filters_orders_and_paginates_by_stable_cursor(
    tmp_path,
) -> None:
    connection = _connection(tmp_path)
    records = (
        _aggregate("C", outcome_unknown=True, reconciliation_required=True),
        _aggregate("A", reconciliation_required=True),
        _aggregate(
            "B",
            lifecycle_state=PaperExecutionLifecycleState.FILLED,
            aggregate_terminal=True,
        ),
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        repository = SqliteExecutionAggregateRepository(transaction)
        for record in records:
            repository.save(record, expected_revision=PaperExecutionRevision.initial())
        transaction.commit()
    query = ExecutionRestartDiscoveryQuery(
        lifecycle_states=(PaperExecutionLifecycleState.CREATED,),
        limit=1,
        schema_version=3,
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        discovery = SqliteExecutionRestartDiscoveryRepository(transaction)
        first = discovery.discover(query)
        second = discovery.discover(
            ExecutionRestartDiscoveryQuery(
                lifecycle_states=query.lifecycle_states,
                limit=1,
                cursor=first.next_cursor,
                schema_version=3,
            )
        )
        assert first.complete is False and second.complete is True
        assert [
            str(item.aggregate_id) for item in first.aggregates + second.aggregates
        ] == sorted(str(item.aggregate_id) for item in (records[0], records[1]))
        excluded = discovery.discover(
            ExecutionRestartDiscoveryQuery(
                lifecycle_states=query.lifecycle_states,
                include_outcome_unknown=False,
                include_reconciliation_required=False,
                schema_version=3,
            )
        )
        assert excluded.aggregates == ()
        transaction.rollback()
    connection.close()


def test_restart_discovery_cursor_validation_boundaries_and_terminal_page(
    tmp_path,
) -> None:
    connection = _connection(tmp_path)
    records = tuple(
        _aggregate(symbol, updated_at=NOW + timedelta(minutes=index))
        for index, symbol in enumerate(("A", "B", "C"))
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        repository = SqliteExecutionAggregateRepository(transaction)
        for record in records:
            repository.save(record, expected_revision=PaperExecutionRevision.initial())
        transaction.commit()
    states = (PaperExecutionLifecycleState.CREATED,)
    base = ExecutionRestartDiscoveryQuery(
        lifecycle_states=states,
        minimum_updated_at=NOW,
        maximum_updated_at=NOW + timedelta(minutes=2),
        limit=1,
        schema_version=3,
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        repository = SqliteExecutionRestartDiscoveryRepository(transaction)
        first = repository.discover(base)
        malformed = repository.discover(
            ExecutionRestartDiscoveryQuery(
                lifecycle_states=states,
                minimum_updated_at=base.minimum_updated_at,
                maximum_updated_at=base.maximum_updated_at,
                cursor="malformed-cursor",
                limit=1,
                schema_version=3,
            )
        )
        unknown = repository.discover(
            ExecutionRestartDiscoveryQuery(
                lifecycle_states=states,
                minimum_updated_at=base.minimum_updated_at,
                maximum_updated_at=base.maximum_updated_at,
                cursor=first.next_cursor.rsplit("-", 1)[0] + "-999",
                limit=1,
                schema_version=3,
            )
        )
        cross_filter = repository.discover(
            ExecutionRestartDiscoveryQuery(
                lifecycle_states=states,
                minimum_updated_at=NOW + timedelta(minutes=1),
                maximum_updated_at=base.maximum_updated_at,
                cursor=first.next_cursor,
                limit=1,
                schema_version=3,
            )
        )
        terminal = repository.discover(
            ExecutionRestartDiscoveryQuery(
                lifecycle_states=states,
                minimum_updated_at=base.minimum_updated_at,
                maximum_updated_at=base.maximum_updated_at,
                cursor=first.next_cursor.rsplit("-", 1)[0] + "-3",
                limit=1,
                schema_version=3,
            )
        )

        assert malformed.aggregates == first.aggregates
        assert unknown.aggregates == first.aggregates
        assert cross_filter.aggregates[0].updated_at >= NOW + timedelta(minutes=1)
        assert terminal.aggregates == ()
        assert terminal.complete is True
        assert terminal.next_cursor is None
        transaction.rollback()
    connection.close()


def test_blocking_slice2_conflict_rolls_back_prior_writes_in_transaction(
    tmp_path,
) -> None:
    connection = _connection(tmp_path)
    approval = ExecutionApprovalRecord(
        approval_fingerprint=fingerprint_payload("pap", ("approval", "rollback")),
        bound_fingerprint="bound-one",
        approval_kind="OPERATOR",
        approver_safe_reference="operator-1",
        approved_at=NOW,
        recorded_at=NOW,
        schema_version=3,
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        SqliteExecutionApprovalRepository(transaction).record(approval)
        transaction.commit()
    conflicting = ExecutionApprovalRecord(
        approval_fingerprint=approval.approval_fingerprint,
        bound_fingerprint="bound-two",
        approval_kind="OPERATOR",
        approver_safe_reference="operator-1",
        approved_at=NOW,
        recorded_at=NOW,
        schema_version=3,
    )
    with _SqliteExecutionTransaction(connection) as transaction:
        SqliteExecutionFailureRepository(transaction).record(
            ExecutionFailureRecord(
                failure=PaperExecutionFailure(
                    failure_kind=PaperExecutionFailureKind.INTERNAL_INVARIANT,
                    severity=PaperExecutionFailureSeverity.ERROR,
                    code="ROLLBACK",
                    safe_message="Rollback test.",
                    retryable=False,
                    reconciliation_required=False,
                    operator_action_required=False,
                    terminal=True,
                    authority_impacting=False,
                ),
                recorded_at=NOW,
                schema_version=3,
            )
        )
        assert (
            SqliteExecutionApprovalRepository(transaction).record(conflicting).conflict
            is not None
        )
        assert transaction.commit().committed is False
    assert (
        connection.execute("SELECT count(*) FROM execution_failures").fetchone()[0] == 0
    )
    connection.close()
