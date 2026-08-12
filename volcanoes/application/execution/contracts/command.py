"""Immutable Paper execution command envelope."""

from __future__ import annotations

from dataclasses import dataclass, field

from volcanoes.application.execution.enums import (
    PaperExecutionMode,
    PaperExecutionOperation,
)
from volcanoes.application.execution.errors import PaperExecutionInvariantError
from volcanoes.application.execution.fingerprints import command_payload_fingerprint
from volcanoes.application.execution.identities import (
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionIdempotencyKey,
    PaperExecutionRevision,
)
from volcanoes.application.execution.contracts.approval import PaperExecutionApproval
from volcanoes.application.execution.contracts.context import PaperExecutionContext
from volcanoes.application.execution.contracts.intent import PaperExecutionIntent
from volcanoes.application.execution.contracts.policy import (
    PaperExecutionPolicySnapshot,
)


@dataclass(frozen=True, slots=True)
class PaperExecutionCommand:
    """Inert immutable command data. It cannot execute itself."""

    command_id: PaperExecutionCommandId
    aggregate_id: PaperExecutionAggregateId
    correlation_id: PaperExecutionCorrelationId
    idempotency_key: PaperExecutionIdempotencyKey
    operation: PaperExecutionOperation
    expected_execution_revision: PaperExecutionRevision
    approval: PaperExecutionApproval
    policy_snapshot: PaperExecutionPolicySnapshot
    context: PaperExecutionContext
    intent: PaperExecutionIntent | None = None
    replacement_intent: PaperExecutionIntent | None = None
    mode: PaperExecutionMode = PaperExecutionMode.PAPER
    payload_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_type(self.command_id, PaperExecutionCommandId, "command_id")
        _require_type(self.aggregate_id, PaperExecutionAggregateId, "aggregate_id")
        _require_type(
            self.correlation_id, PaperExecutionCorrelationId, "correlation_id"
        )
        _require_type(
            self.idempotency_key,
            PaperExecutionIdempotencyKey,
            "idempotency_key",
        )
        _require_type(
            self.expected_execution_revision,
            PaperExecutionRevision,
            "expected_execution_revision",
        )
        _require_type(self.approval, PaperExecutionApproval, "approval")
        _require_type(
            self.policy_snapshot,
            PaperExecutionPolicySnapshot,
            "policy_snapshot",
        )
        _require_type(self.context, PaperExecutionContext, "context")
        if self.mode is not PaperExecutionMode.PAPER:
            raise PaperExecutionInvariantError(
                "PAPER_MODE_REQUIRED",
                "Paper execution commands require Paper mode.",
            )
        if not isinstance(self.operation, PaperExecutionOperation):
            raise PaperExecutionInvariantError(
                "INVALID_OPERATION",
                "Unsupported execution operation.",
            )
        if self.operation is PaperExecutionOperation.SUBMIT:
            if not isinstance(self.intent, PaperExecutionIntent):
                raise PaperExecutionInvariantError(
                    "SUBMIT_INTENT_REQUIRED",
                    "Submit commands require an intent.",
                )
            if self.replacement_intent is not None:
                raise PaperExecutionInvariantError(
                    "SUBMIT_REPLACEMENT_FORBIDDEN",
                    "Submit commands cannot carry replacement intent.",
                )
        if self.operation is PaperExecutionOperation.CANCEL:
            if self.intent is not None or self.replacement_intent is not None:
                raise PaperExecutionInvariantError(
                    "CANCEL_INTENT_FORBIDDEN",
                    "Cancel commands cannot carry order intent.",
                )
        if self.operation is PaperExecutionOperation.REPLACE:
            if not isinstance(self.replacement_intent, PaperExecutionIntent):
                raise PaperExecutionInvariantError(
                    "REPLACE_INTENT_REQUIRED",
                    "Replace commands require replacement intent.",
                )
            if self.intent is not None:
                raise PaperExecutionInvariantError(
                    "REPLACE_ORIGINAL_INTENT_FORBIDDEN",
                    "Replace commands retain aggregate identity and carry replacement intent only.",
                )
        if self.context.aggregate_id != self.aggregate_id:
            raise PaperExecutionInvariantError(
                "CONTEXT_AGGREGATE_MISMATCH",
                "Command aggregate must match context aggregate.",
            )
        if self.context.correlation_id != self.correlation_id:
            raise PaperExecutionInvariantError(
                "CONTEXT_CORRELATION_MISMATCH",
                "Command correlation must match context correlation.",
            )
        object.__setattr__(
            self,
            "payload_fingerprint",
            command_payload_fingerprint(self.canonical_payload()),
        )

    def canonical_payload(self) -> dict[str, object]:
        """Return the deterministic command content excluding command identity."""

        return {
            "aggregate_id": self.aggregate_id,
            "approval": self.approval,
            "context": self.context,
            "correlation_id": self.correlation_id,
            "expected_execution_revision": self.expected_execution_revision,
            "idempotency_key": self.idempotency_key,
            "intent": self.intent,
            "mode": self.mode,
            "operation": self.operation,
            "policy_snapshot": self.policy_snapshot,
            "replacement_intent": self.replacement_intent,
        }

    def to_primitive(self) -> dict[str, object]:
        return {
            "command_id": self.command_id,
            "payload_fingerprint": self.payload_fingerprint,
            **self.canonical_payload(),
        }

    def fingerprint(self) -> str:
        """Return the command payload fingerprint."""

        return self.payload_fingerprint


def _require_type(value: object, expected_type: type[object], name: str) -> None:
    if not isinstance(value, expected_type):
        raise PaperExecutionInvariantError(
            "INVALID_COMMAND_FIELD",
            f"{name} has an invalid type.",
        )
