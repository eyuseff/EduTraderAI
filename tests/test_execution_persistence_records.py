from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from volcanoes.application.execution import (
    ExecutionAggregateRecord,
    ExecutionApprovalRecord,
    ExecutionBrokerReferenceRecord,
    ExecutionBrokerReferenceStatus,
    ExecutionCommandProcessingOutcome,
    ExecutionCommandRecord,
    ExecutionFailureRecord,
    ExecutionIdempotencyRecord,
    ExecutionIdempotencyReservationStatus,
    ExecutionReceiptRecord,
    ExecutionReconciliationRecord,
    ExecutionReconciliationResultClassification,
    ExecutionReplayKind,
    ExecutionTransitionRecord,
    PaperBrokerOrderReference,
    PaperExecutionAggregateId,
    PaperExecutionApprovalKind,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionFailure,
    PaperExecutionFailureKind,
    PaperExecutionFailureSeverity,
    PaperExecutionIdempotencyKey,
    PaperExecutionLifecycleEvidenceIntentKind,
    PaperExecutionLifecycleInputType,
    PaperExecutionLifecycleSideEffectIntentKind,
    PaperExecutionLifecycleState,
    PaperExecutionOperation,
    PaperExecutionReceipt,
    PaperExecutionReceiptKind,
    PaperExecutionRevision,
    PaperExecutionStatus,
)
from volcanoes.application.execution.fingerprints import (
    approval_fingerprint,
    command_payload_fingerprint,
    failure_fingerprint,
    fingerprint_payload,
    policy_fingerprint,
)
from volcanoes.application.execution.persistence.errors import (
    ExecutionPersistenceInvariantError,
)

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=1)
SCHEMA_VERSION = 1


def aggregate_id() -> PaperExecutionAggregateId:
    return PaperExecutionAggregateId.from_seed("aggregate", "AAPL")


def command_id() -> PaperExecutionCommandId:
    return PaperExecutionCommandId.from_seed("command", "AAPL")


def correlation_id() -> PaperExecutionCorrelationId:
    return PaperExecutionCorrelationId.from_seed("correlation", "AAPL")


def idempotency_key() -> PaperExecutionIdempotencyKey:
    return PaperExecutionIdempotencyKey.from_seed("idempotency", "AAPL")


def broker_reference() -> PaperBrokerOrderReference:
    return PaperBrokerOrderReference.from_seed("broker-reference", "AAPL")


def aggregate_record(**overrides: object) -> ExecutionAggregateRecord:
    values = {
        "aggregate_id": aggregate_id(),
        "correlation_id": correlation_id(),
        "lifecycle_state": PaperExecutionLifecycleState.CREATED,
        "execution_revision": PaperExecutionRevision.initial(),
        "cumulative_filled_quantity": Decimal("0"),
        "requested_quantity": Decimal("1"),
        "active_broker_reference": None,
        "outcome_unknown": False,
        "reconciliation_required": False,
        "command_terminal": False,
        "aggregate_terminal": False,
        "last_transition_id": "PX-TRN-001",
        "last_command_id": command_id(),
        "last_idempotency_key": idempotency_key(),
        "last_receipt_fingerprint": None,
        "last_failure_fingerprint": None,
        "created_at": NOW,
        "updated_at": LATER,
        "schema_version": SCHEMA_VERSION,
    }
    values.update(overrides)
    return ExecutionAggregateRecord(**values)


def command_record(**overrides: object) -> ExecutionCommandRecord:
    payload = {"symbol": "AAPL", "quantity": 1, "operation": "SUBMIT"}
    values = {
        "command_id": command_id(),
        "aggregate_id": aggregate_id(),
        "correlation_id": correlation_id(),
        "idempotency_key": idempotency_key(),
        "operation": PaperExecutionOperation.SUBMIT,
        "expected_execution_revision": PaperExecutionRevision.initial(),
        "canonical_payload_fingerprint": command_payload_fingerprint(payload),
        "canonical_command_json": '{"operation":"SUBMIT","quantity":1,"symbol":"AAPL"}',
        "approval_fingerprint": approval_fingerprint(("approval", "AAPL")),
        "policy_fingerprint": policy_fingerprint(("policy", "AAPL")),
        "received_at": NOW,
        "processing_outcome": ExecutionCommandProcessingOutcome.ACCEPTED,
        "schema_version": SCHEMA_VERSION,
    }
    values.update(overrides)
    return ExecutionCommandRecord(**values)


def idempotency_record(**overrides: object) -> ExecutionIdempotencyRecord:
    values = {
        "idempotency_key": idempotency_key(),
        "logical_operation_fingerprint": fingerprint_payload("plo", ("submit", "AAPL")),
        "command_id": command_id(),
        "aggregate_id": aggregate_id(),
        "reservation_status": ExecutionIdempotencyReservationStatus.RESERVED,
        "original_result_fingerprint": None,
        "created_at": NOW,
        "resolved_at": None,
        "conflict": False,
        "schema_version": SCHEMA_VERSION,
    }
    values.update(overrides)
    return ExecutionIdempotencyRecord(**values)


def receipt() -> PaperExecutionReceipt:
    return PaperExecutionReceipt(
        command_id=command_id(),
        aggregate_id=aggregate_id(),
        correlation_id=correlation_id(),
        operation=PaperExecutionOperation.SUBMIT,
        receipt_kind=PaperExecutionReceiptKind.COMMAND_ACCEPTED_LOCALLY,
        status=PaperExecutionStatus.CREATED,
        observed_execution_revision=PaperExecutionRevision.initial(),
        observed_at=NOW,
        message_code="COMMAND_ACCEPTED",
    )


def failure() -> PaperExecutionFailure:
    return PaperExecutionFailure(
        failure_kind=PaperExecutionFailureKind.STALE_REVISION,
        severity=PaperExecutionFailureSeverity.ERROR,
        code="STALE_REVISION",
        safe_message="State changed before this command.",
        retryable=False,
        reconciliation_required=False,
        operator_action_required=False,
        terminal=False,
        authority_impacting=False,
        command_id=command_id(),
        aggregate_id=aggregate_id(),
        correlation_id=correlation_id(),
    )


@pytest.mark.parametrize(
    "record_factory",
    [
        aggregate_record,
        command_record,
        idempotency_record,
        lambda: ExecutionTransitionRecord(
            transition_record_id="transition-record-1",
            aggregate_id=aggregate_id(),
            transition_id="PX-TRN-002",
            source_state=PaperExecutionLifecycleState.CREATED,
            destination_state=PaperExecutionLifecycleState.ELIGIBILITY_EVALUATED,
            previous_revision=PaperExecutionRevision(0),
            next_revision=PaperExecutionRevision(1),
            lifecycle_input_kind=PaperExecutionLifecycleInputType.RECORD_ELIGIBILITY,
            input_identity="input-1",
            command_id=command_id(),
            correlation_id=correlation_id(),
            idempotency_key=idempotency_key(),
            replay_indicator=ExecutionReplayKind.NONE,
            side_effect_intent_kinds=(
                PaperExecutionLifecycleSideEffectIntentKind.NONE,
            ),
            evidence_intent_kinds=(
                PaperExecutionLifecycleEvidenceIntentKind.LIFECYCLE_TRANSITION_ACCEPTED,
            ),
            safe_reason_code="ELIGIBILITY_RECORDED",
            recorded_at=NOW,
            schema_version=SCHEMA_VERSION,
        ),
        lambda: ExecutionBrokerReferenceRecord(
            broker_reference=broker_reference(),
            aggregate_id=aggregate_id(),
            command_id=command_id(),
            adapter_identity="alpaca.paper.adapter",
            reference_status=ExecutionBrokerReferenceStatus.ACTIVE,
            first_seen_at=NOW,
            last_seen_at=LATER,
            active=True,
            schema_version=SCHEMA_VERSION,
        ),
        lambda: ExecutionReceiptRecord(
            receipt=receipt(),
            recorded_at=NOW,
            schema_version=SCHEMA_VERSION,
        ),
        lambda: ExecutionFailureRecord(
            failure=failure(),
            recorded_at=NOW,
            schema_version=SCHEMA_VERSION,
        ),
        lambda: ExecutionApprovalRecord(
            approval_fingerprint=approval_fingerprint(("approval", "AAPL")),
            bound_fingerprint=command_payload_fingerprint(("intent", "AAPL")),
            approval_kind=PaperExecutionApprovalKind.OPERATOR.value,
            approver_safe_reference="operator.local",
            approved_at=NOW,
            recorded_at=LATER,
            schema_version=SCHEMA_VERSION,
        ),
        lambda: ExecutionReconciliationRecord(
            reconciliation_id="reconciliation-1",
            aggregate_id=aggregate_id(),
            starting_local_revision=PaperExecutionRevision(3),
            starting_lifecycle_state=PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
            broker_observation_references=("observation-1",),
            result_classification=(
                ExecutionReconciliationResultClassification.UNRESOLVED
            ),
            operator_action_required=True,
            unresolved=True,
            safe_reason_code="OUTCOME_UNKNOWN",
            recorded_at=NOW,
            schema_version=SCHEMA_VERSION,
        ),
    ],
)
def test_records_are_immutable_and_deterministic(record_factory) -> None:
    record = record_factory()

    with pytest.raises(FrozenInstanceError):
        record.schema_version = 2

    assert record.to_primitive() == record_factory().to_primitive()
    assert "password" not in repr(record).lower()


@pytest.mark.parametrize(
    ("factory", "prefix"),
    [
        (aggregate_record, "par-"),
        (command_record, "pcm-"),
        (idempotency_record, "pir-"),
        (
            lambda: ExecutionTransitionRecord(
                transition_record_id="transition-record-1",
                aggregate_id=aggregate_id(),
                transition_id="PX-TRN-002",
                source_state=PaperExecutionLifecycleState.CREATED,
                destination_state=(PaperExecutionLifecycleState.ELIGIBILITY_EVALUATED),
                previous_revision=PaperExecutionRevision(0),
                next_revision=PaperExecutionRevision(1),
                lifecycle_input_kind=PaperExecutionLifecycleInputType.RECORD_ELIGIBILITY,
                input_identity="input-1",
                command_id=command_id(),
                correlation_id=correlation_id(),
                idempotency_key=idempotency_key(),
                replay_indicator=ExecutionReplayKind.NONE,
                side_effect_intent_kinds=(),
                evidence_intent_kinds=(),
                safe_reason_code="OK",
                recorded_at=NOW,
                schema_version=SCHEMA_VERSION,
            ),
            "ptr-",
        ),
    ],
)
def test_record_fingerprint_prefixes(factory, prefix: str) -> None:
    assert factory().record_fingerprint.startswith(prefix)


def test_aggregate_preserves_execution_revision_and_excludes_other_versions() -> None:
    record = aggregate_record(execution_revision=PaperExecutionRevision(7))
    primitive = record.to_primitive()

    assert primitive["execution_revision"] == PaperExecutionRevision(7)
    assert "qualification_revision" not in primitive
    assert "broker_version" not in primitive


def test_aggregate_rejects_updated_before_created() -> None:
    with pytest.raises(ExecutionPersistenceInvariantError):
        aggregate_record(updated_at=NOW - timedelta(seconds=1))


def test_aggregate_enforces_paper_mode() -> None:
    with pytest.raises(ExecutionPersistenceInvariantError):
        aggregate_record(mode="PAPER")


def test_command_binds_payload_and_policy_fingerprints() -> None:
    record = command_record()

    assert record.canonical_payload_fingerprint.startswith("pcf-")
    assert record.approval_fingerprint.startswith("pap-")
    assert record.policy_fingerprint.startswith("pps-")
    assert record.operation is PaperExecutionOperation.SUBMIT


@pytest.mark.parametrize(
    "field",
    [
        "canonical_payload_fingerprint",
        "approval_fingerprint",
        "policy_fingerprint",
    ],
)
def test_command_rejects_invalid_fingerprint(field: str) -> None:
    with pytest.raises(Exception):
        command_record(**{field: "not-a-fingerprint"})


def test_command_rejects_sensitive_payload_text() -> None:
    with pytest.raises(ExecutionPersistenceInvariantError):
        command_record(canonical_command_json='{"api_key":"hidden"}')


@pytest.mark.parametrize(
    "status",
    tuple(ExecutionIdempotencyReservationStatus),
)
def test_idempotency_status_values_are_supported(
    status: ExecutionIdempotencyReservationStatus,
) -> None:
    record = idempotency_record(reservation_status=status)

    assert record.reservation_status is status


def test_idempotency_rejects_resolved_before_created() -> None:
    with pytest.raises(ExecutionPersistenceInvariantError):
        idempotency_record(resolved_at=NOW - timedelta(seconds=1))


def test_transition_requires_sequential_revision() -> None:
    with pytest.raises(ExecutionPersistenceInvariantError):
        ExecutionTransitionRecord(
            transition_record_id="transition-record-1",
            aggregate_id=aggregate_id(),
            transition_id="PX-TRN-002",
            source_state=PaperExecutionLifecycleState.CREATED,
            destination_state=PaperExecutionLifecycleState.ELIGIBILITY_EVALUATED,
            previous_revision=PaperExecutionRevision(0),
            next_revision=PaperExecutionRevision(2),
            lifecycle_input_kind=PaperExecutionLifecycleInputType.RECORD_ELIGIBILITY,
            input_identity="input-1",
            command_id=command_id(),
            correlation_id=correlation_id(),
            idempotency_key=idempotency_key(),
            replay_indicator=ExecutionReplayKind.NONE,
            side_effect_intent_kinds=(),
            evidence_intent_kinds=(),
            safe_reason_code="OK",
            recorded_at=NOW,
            schema_version=SCHEMA_VERSION,
        )


def test_transition_rejects_replay_indicator() -> None:
    with pytest.raises(ExecutionPersistenceInvariantError):
        ExecutionTransitionRecord(
            transition_record_id="transition-record-1",
            aggregate_id=aggregate_id(),
            transition_id="PX-TRN-002",
            source_state=PaperExecutionLifecycleState.CREATED,
            destination_state=PaperExecutionLifecycleState.ELIGIBILITY_EVALUATED,
            previous_revision=PaperExecutionRevision(0),
            next_revision=PaperExecutionRevision(1),
            lifecycle_input_kind=PaperExecutionLifecycleInputType.RECORD_ELIGIBILITY,
            input_identity="input-1",
            command_id=command_id(),
            correlation_id=correlation_id(),
            idempotency_key=idempotency_key(),
            replay_indicator=ExecutionReplayKind.EXACT_COMMAND,
            side_effect_intent_kinds=(),
            evidence_intent_kinds=(),
            safe_reason_code="OK",
            recorded_at=NOW,
            schema_version=SCHEMA_VERSION,
        )


def test_broker_reference_rejects_last_seen_before_first_seen() -> None:
    with pytest.raises(ExecutionPersistenceInvariantError):
        ExecutionBrokerReferenceRecord(
            broker_reference=broker_reference(),
            aggregate_id=aggregate_id(),
            command_id=command_id(),
            adapter_identity="alpaca.paper.adapter",
            reference_status=ExecutionBrokerReferenceStatus.ACTIVE,
            first_seen_at=LATER,
            last_seen_at=NOW,
            active=True,
            schema_version=SCHEMA_VERSION,
        )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ExecutionReceiptRecord("bad", NOW, SCHEMA_VERSION),
        lambda: ExecutionFailureRecord("bad", NOW, SCHEMA_VERSION),
    ],
)
def test_receipt_and_failure_records_require_normalized_contracts(factory) -> None:
    with pytest.raises(ExecutionPersistenceInvariantError):
        factory()


def test_approval_rejects_expiry_before_approval() -> None:
    with pytest.raises(ExecutionPersistenceInvariantError):
        ExecutionApprovalRecord(
            approval_fingerprint=approval_fingerprint(("approval", "AAPL")),
            bound_fingerprint=command_payload_fingerprint(("intent", "AAPL")),
            approval_kind="OPERATOR",
            approver_safe_reference="operator.local",
            approved_at=NOW,
            expires_at=NOW - timedelta(seconds=1),
            recorded_at=NOW,
            schema_version=SCHEMA_VERSION,
        )


def test_reconciliation_record_is_append_only_data_only() -> None:
    record = ExecutionReconciliationRecord(
        reconciliation_id="reconciliation-1",
        aggregate_id=aggregate_id(),
        starting_local_revision=PaperExecutionRevision(3),
        starting_lifecycle_state=PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
        broker_observation_references=("observation-1", "observation-2"),
        result_classification=ExecutionReconciliationResultClassification.CONFLICTING,
        operator_action_required=True,
        unresolved=True,
        safe_reason_code="BROKER_CONFLICT",
        recorded_at=NOW,
        schema_version=SCHEMA_VERSION,
    )

    assert record.to_primitive()["broker_observation_references"] == (
        "observation-1",
        "observation-2",
    )
    assert not hasattr(record, "recover")


@pytest.mark.parametrize(
    "factory",
    [
        lambda: aggregate_record(created_at=datetime(2026, 8, 5, 12, 0)),
        lambda: command_record(received_at=datetime(2026, 8, 5, 12, 0)),
        lambda: idempotency_record(created_at=datetime(2026, 8, 5, 12, 0)),
    ],
)
def test_records_require_timezone_aware_timestamps(factory) -> None:
    with pytest.raises(Exception):
        factory()


@pytest.mark.parametrize(
    "factory",
    [aggregate_record, command_record, idempotency_record],
)
def test_schema_version_must_be_positive(factory) -> None:
    with pytest.raises(ExecutionPersistenceInvariantError):
        factory(schema_version=0)


def test_records_do_not_expose_database_or_broker_payload_fields() -> None:
    primitive = aggregate_record().to_primitive() | command_record().to_primitive()

    forbidden = {
        "database",
        "sql",
        "orm",
        "raw_broker_payload",
        "broker_client",
        "callback",
    }

    assert forbidden.isdisjoint(primitive)


def test_failure_record_reuses_existing_failure_fingerprint() -> None:
    record = ExecutionFailureRecord(
        failure=failure(),
        recorded_at=NOW,
        schema_version=SCHEMA_VERSION,
    )

    assert record.failure.failure_fingerprint == failure().failure_fingerprint
    assert record.record_fingerprint.startswith("pfr-")


def test_receipt_record_reuses_existing_receipt_fingerprint() -> None:
    record = ExecutionReceiptRecord(
        receipt=receipt(),
        recorded_at=NOW,
        schema_version=SCHEMA_VERSION,
    )

    assert record.receipt.receipt_fingerprint == receipt().receipt_fingerprint
    assert record.record_fingerprint.startswith("prr-")


def test_raw_exception_text_is_rejected_from_failure_contract() -> None:
    with pytest.raises(Exception):
        PaperExecutionFailure(
            failure_kind=PaperExecutionFailureKind.INTERNAL_INVARIANT,
            severity=PaperExecutionFailureSeverity.ERROR,
            code="INTERNAL",
            safe_message="authorization header leaked",
            retryable=False,
            reconciliation_required=False,
            operator_action_required=True,
            terminal=False,
            authority_impacting=True,
        )


def test_logical_operation_fingerprint_is_required() -> None:
    with pytest.raises(Exception):
        idempotency_record(logical_operation_fingerprint=failure_fingerprint(("x",)))
