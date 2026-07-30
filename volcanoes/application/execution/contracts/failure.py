"""Immutable normalized Paper execution failure data."""

from __future__ import annotations

from dataclasses import dataclass, field

from volcanoes.application.execution.contracts._validation import (
    normalize_code,
    validate_no_sensitive_text,
)
from volcanoes.application.execution.enums import (
    PaperExecutionFailureKind,
    PaperExecutionFailureSeverity,
)
from volcanoes.application.execution.fingerprints import failure_fingerprint
from volcanoes.application.execution.identities import (
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
)


@dataclass(frozen=True, slots=True)
class PaperExecutionFailure:
    """Normalized immutable failure data, not an exception wrapper."""

    failure_kind: PaperExecutionFailureKind
    severity: PaperExecutionFailureSeverity
    code: str
    safe_message: str
    retryable: bool
    reconciliation_required: bool
    operator_action_required: bool
    terminal: bool
    authority_impacting: bool
    command_id: PaperExecutionCommandId | None = None
    aggregate_id: PaperExecutionAggregateId | None = None
    correlation_id: PaperExecutionCorrelationId | None = None
    failure_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.failure_kind, PaperExecutionFailureKind):
            raise TypeError("failure_kind must be a PaperExecutionFailureKind.")
        if not isinstance(self.severity, PaperExecutionFailureSeverity):
            raise TypeError("severity must be a PaperExecutionFailureSeverity.")
        object.__setattr__(self, "code", normalize_code(self.code, "code"))
        object.__setattr__(
            self,
            "safe_message",
            validate_no_sensitive_text(self.safe_message, "safe_message"),
        )
        for name in (
            "retryable",
            "reconciliation_required",
            "operator_action_required",
            "terminal",
            "authority_impacting",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a boolean.")
        object.__setattr__(
            self,
            "failure_fingerprint",
            failure_fingerprint(self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "failure_fingerprint": self.failure_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "aggregate_id": self.aggregate_id,
            "authority_impacting": self.authority_impacting,
            "code": self.code,
            "command_id": self.command_id,
            "correlation_id": self.correlation_id,
            "failure_kind": self.failure_kind,
            "operator_action_required": self.operator_action_required,
            "reconciliation_required": self.reconciliation_required,
            "retryable": self.retryable,
            "safe_message": self.safe_message,
            "severity": self.severity,
            "terminal": self.terminal,
        }
