from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from volcanoes.application.execution import (
    PaperBrokerOrderReference,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionInvariantError,
    PaperExecutionMode,
    PaperExecutionOperation,
    PaperExecutionReceipt,
    PaperExecutionReceiptKind,
    PaperExecutionRevision,
    PaperExecutionStatus,
)


def ids() -> tuple[
    PaperExecutionCommandId,
    PaperExecutionAggregateId,
    PaperExecutionCorrelationId,
]:
    return (
        PaperExecutionCommandId.from_seed("command", "AAPL"),
        PaperExecutionAggregateId.from_seed("aggregate", "AAPL"),
        PaperExecutionCorrelationId.from_seed("correlation", "AAPL"),
    )


def broker_ref() -> PaperBrokerOrderReference:
    return PaperBrokerOrderReference.from_seed("broker", "paper-order-1")


def receipt(
    kind: PaperExecutionReceiptKind,
    status: PaperExecutionStatus,
    *,
    reference: PaperBrokerOrderReference | None = None,
) -> PaperExecutionReceipt:
    command_id, aggregate_id, correlation_id = ids()
    return PaperExecutionReceipt(
        command_id=command_id,
        aggregate_id=aggregate_id,
        correlation_id=correlation_id,
        operation=PaperExecutionOperation.SUBMIT,
        receipt_kind=kind,
        status=status,
        observed_execution_revision=PaperExecutionRevision(1),
        observed_at=datetime(2026, 7, 30, tzinfo=UTC),
        message_code="OBSERVED",
        broker_order_reference=reference,
    )


@pytest.mark.parametrize(
    ("kind", "status", "needs_reference"),
    (
        (
            PaperExecutionReceiptKind.COMMAND_ACCEPTED_LOCALLY,
            PaperExecutionStatus.CREATED,
            False,
        ),
        (
            PaperExecutionReceiptKind.DISPATCH_RECORDED,
            PaperExecutionStatus.DISPATCHED,
            False,
        ),
        (
            PaperExecutionReceiptKind.BROKER_ACKNOWLEDGED,
            PaperExecutionStatus.ACKNOWLEDGED,
            True,
        ),
        (
            PaperExecutionReceiptKind.BROKER_REJECTED,
            PaperExecutionStatus.BROKER_REJECTED,
            False,
        ),
        (
            PaperExecutionReceiptKind.PARTIAL_FILL_OBSERVED,
            PaperExecutionStatus.PARTIALLY_FILLED,
            True,
        ),
        (PaperExecutionReceiptKind.FILL_OBSERVED, PaperExecutionStatus.FILLED, True),
        (
            PaperExecutionReceiptKind.CANCEL_ACKNOWLEDGED,
            PaperExecutionStatus.CANCEL_PENDING,
            True,
        ),
        (
            PaperExecutionReceiptKind.CANCEL_CONFIRMED,
            PaperExecutionStatus.CANCELLED,
            True,
        ),
        (
            PaperExecutionReceiptKind.REPLACE_ACKNOWLEDGED,
            PaperExecutionStatus.REPLACE_PENDING,
            True,
        ),
        (
            PaperExecutionReceiptKind.REPLACE_CONFIRMED,
            PaperExecutionStatus.REPLACED,
            True,
        ),
        (
            PaperExecutionReceiptKind.OUTCOME_UNKNOWN,
            PaperExecutionStatus.OUTCOME_UNKNOWN,
            False,
        ),
        (
            PaperExecutionReceiptKind.RECONCILIATION_REQUIRED,
            PaperExecutionStatus.RECONCILIATION_REQUIRED,
            False,
        ),
    ),
)
def test_receipt_kinds_are_representable_and_fingerprinted(
    kind: PaperExecutionReceiptKind,
    status: PaperExecutionStatus,
    needs_reference: bool,
) -> None:
    result = receipt(
        kind, status, reference=(broker_ref() if needs_reference else None)
    )

    assert result.mode is PaperExecutionMode.PAPER
    assert result.receipt_fingerprint.startswith("prc-")
    assert result.to_primitive()["receipt_fingerprint"] == result.receipt_fingerprint


def test_acknowledgement_partial_fill_and_fill_are_distinct() -> None:
    acknowledged = receipt(
        PaperExecutionReceiptKind.BROKER_ACKNOWLEDGED,
        PaperExecutionStatus.ACKNOWLEDGED,
        reference=broker_ref(),
    )
    partial = receipt(
        PaperExecutionReceiptKind.PARTIAL_FILL_OBSERVED,
        PaperExecutionStatus.PARTIALLY_FILLED,
        reference=broker_ref(),
    )
    filled = receipt(
        PaperExecutionReceiptKind.FILL_OBSERVED,
        PaperExecutionStatus.FILLED,
        reference=broker_ref(),
    )

    assert (
        len(
            {
                acknowledged.receipt_fingerprint,
                partial.receipt_fingerprint,
                filled.receipt_fingerprint,
            }
        )
        == 3
    )


def test_unknown_outcome_forces_reconciliation_flag() -> None:
    result = receipt(
        PaperExecutionReceiptKind.OUTCOME_UNKNOWN,
        PaperExecutionStatus.OUTCOME_UNKNOWN,
    )

    assert result.outcome_known is False
    assert result.reconciliation_required is True


def test_reconciliation_required_is_explicit() -> None:
    result = receipt(
        PaperExecutionReceiptKind.RECONCILIATION_REQUIRED,
        PaperExecutionStatus.RECONCILIATION_REQUIRED,
    )

    assert result.outcome_known is True
    assert result.reconciliation_required is True


def test_receipt_requires_broker_reference_for_broker_observations() -> None:
    with pytest.raises(PaperExecutionInvariantError):
        receipt(
            PaperExecutionReceiptKind.BROKER_ACKNOWLEDGED,
            PaperExecutionStatus.ACKNOWLEDGED,
        )


def test_receipt_rejects_naive_time_and_mutation() -> None:
    command_id, aggregate_id, correlation_id = ids()
    with pytest.raises(Exception):
        PaperExecutionReceipt(
            command_id=command_id,
            aggregate_id=aggregate_id,
            correlation_id=correlation_id,
            operation=PaperExecutionOperation.SUBMIT,
            receipt_kind=PaperExecutionReceiptKind.DISPATCH_RECORDED,
            status=PaperExecutionStatus.DISPATCHED,
            observed_execution_revision=PaperExecutionRevision(1),
            observed_at=datetime(2026, 7, 30),
            message_code="OBSERVED",
        )
    result = receipt(
        PaperExecutionReceiptKind.DISPATCH_RECORDED,
        PaperExecutionStatus.DISPATCHED,
    )
    with pytest.raises(FrozenInstanceError):
        result.message_code = "CHANGED"  # type: ignore[misc]


def test_receipt_rejects_secret_like_message_codes_and_raw_payload_shape() -> None:
    command_id, aggregate_id, correlation_id = ids()
    with pytest.raises(PaperExecutionInvariantError):
        PaperExecutionReceipt(
            command_id=command_id,
            aggregate_id=aggregate_id,
            correlation_id=correlation_id,
            operation=PaperExecutionOperation.SUBMIT,
            receipt_kind=PaperExecutionReceiptKind.DISPATCH_RECORDED,
            status=PaperExecutionStatus.DISPATCHED,
            observed_execution_revision=PaperExecutionRevision(1),
            observed_at=datetime(2026, 7, 30, tzinfo=UTC),
            message_code="API_KEY_LEAK",
        )
