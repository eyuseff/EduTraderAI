"""Immutable normalized Paper execution receipt."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from volcanoes.application.execution.contracts._validation import (
    normalize_code,
    require_datetime,
    validate_no_sensitive_text,
)
from volcanoes.application.execution.enums import (
    PaperExecutionMode,
    PaperExecutionOperation,
    PaperExecutionReceiptKind,
    PaperExecutionStatus,
)
from volcanoes.application.execution.errors import PaperExecutionInvariantError
from volcanoes.application.execution.fingerprints import receipt_fingerprint
from volcanoes.application.execution.identities import (
    PaperBrokerOrderReference,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionRevision,
)

_BROKER_REFERENCE_KINDS = frozenset(
    {
        PaperExecutionReceiptKind.BROKER_ACKNOWLEDGED,
        PaperExecutionReceiptKind.PARTIAL_FILL_OBSERVED,
        PaperExecutionReceiptKind.FILL_OBSERVED,
        PaperExecutionReceiptKind.CANCEL_ACKNOWLEDGED,
        PaperExecutionReceiptKind.CANCEL_CONFIRMED,
        PaperExecutionReceiptKind.REPLACE_ACKNOWLEDGED,
        PaperExecutionReceiptKind.REPLACE_CONFIRMED,
    }
)


@dataclass(frozen=True, slots=True)
class PaperExecutionReceipt:
    """Normalized observation, not raw broker response."""

    command_id: PaperExecutionCommandId
    aggregate_id: PaperExecutionAggregateId
    correlation_id: PaperExecutionCorrelationId
    operation: PaperExecutionOperation
    receipt_kind: PaperExecutionReceiptKind
    status: PaperExecutionStatus
    observed_execution_revision: PaperExecutionRevision
    observed_at: datetime
    message_code: str
    broker_order_reference: PaperBrokerOrderReference | None = None
    outcome_known: bool = True
    reconciliation_required: bool = False
    mode: PaperExecutionMode = PaperExecutionMode.PAPER
    receipt_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if self.mode is not PaperExecutionMode.PAPER:
            raise PaperExecutionInvariantError(
                "PAPER_MODE_REQUIRED",
                "Paper execution receipts require Paper mode.",
            )
        if self.receipt_kind in _BROKER_REFERENCE_KINDS and not isinstance(
            self.broker_order_reference,
            PaperBrokerOrderReference,
        ):
            raise PaperExecutionInvariantError(
                "BROKER_REFERENCE_REQUIRED",
                "This receipt kind requires a broker order reference.",
            )
        if self.receipt_kind is PaperExecutionReceiptKind.OUTCOME_UNKNOWN:
            object.__setattr__(self, "outcome_known", False)
            object.__setattr__(self, "reconciliation_required", True)
        if self.receipt_kind is PaperExecutionReceiptKind.RECONCILIATION_REQUIRED:
            object.__setattr__(self, "reconciliation_required", True)
        object.__setattr__(
            self, "observed_at", require_datetime(self.observed_at, "observed_at")
        )
        object.__setattr__(
            self,
            "message_code",
            validate_no_sensitive_text(
                normalize_code(self.message_code, "message_code"),
                "message_code",
            ),
        )
        object.__setattr__(
            self,
            "receipt_fingerprint",
            receipt_fingerprint(self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "receipt_fingerprint": self.receipt_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "aggregate_id": self.aggregate_id,
            "broker_order_reference": self.broker_order_reference,
            "command_id": self.command_id,
            "correlation_id": self.correlation_id,
            "message_code": self.message_code,
            "mode": self.mode,
            "observed_at": self.observed_at,
            "observed_execution_revision": self.observed_execution_revision,
            "operation": self.operation,
            "outcome_known": self.outcome_known,
            "receipt_kind": self.receipt_kind,
            "reconciliation_required": self.reconciliation_required,
            "status": self.status,
        }
