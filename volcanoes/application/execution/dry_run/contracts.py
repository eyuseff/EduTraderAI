"""Immutable contracts for deterministic Paper execution dry runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from volcanoes.application.execution.contracts import PaperExecutionCommand
from volcanoes.application.execution.contracts._validation import (
    normalize_code,
    require_datetime,
    validate_no_sensitive_text,
)
from volcanoes.application.execution.dry_run.enums import (
    PaperDryRunFailureReason,
    PaperDryRunOutcomeKind,
    PaperDryRunStepKind,
    PaperExecutionEffectMode,
)
from volcanoes.application.execution.errors import PaperExecutionInvariantError
from volcanoes.application.execution.fingerprints import fingerprint_payload
from volcanoes.application.execution.identities import (
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionRevision,
)
from volcanoes.application.execution.lifecycle import (
    PaperExecutionLifecycle,
    PaperExecutionLifecycleEvidenceIntentKind,
    PaperExecutionLifecycleSideEffectIntentKind,
    PaperExecutionTransitionContext,
)
from volcanoes.application.execution.eligibility import (
    PaperExecutionEligibilityPolicy,
    PaperExecutionEligibilityResult,
)


def dry_run_request_fingerprint(primitive: object) -> str:
    """Return a deterministic dry-run request fingerprint."""

    return fingerprint_payload("pdr", primitive)


def dry_run_result_fingerprint(primitive: object) -> str:
    """Return a deterministic dry-run result fingerprint."""

    return fingerprint_payload("pdo", primitive)


def dry_run_receipt_fingerprint(primitive: object) -> str:
    """Return a deterministic dry-run receipt fingerprint."""

    return fingerprint_payload("pdt", primitive)


def dry_run_failure_fingerprint(primitive: object) -> str:
    """Return a deterministic dry-run failure fingerprint."""

    return fingerprint_payload("pdf", primitive)


@dataclass(frozen=True, slots=True)
class PaperDryRunStep:
    """One immutable dry-run orchestration step."""

    sequence: int
    kind: PaperDryRunStepKind
    reason_code: str
    lifecycle_transition_id: str | None = None
    previous_revision: PaperExecutionRevision | None = None
    next_revision: PaperExecutionRevision | None = None
    side_effect_intent_kinds: tuple[
        PaperExecutionLifecycleSideEffectIntentKind, ...
    ] = ()
    evidence_intent_kinds: tuple[PaperExecutionLifecycleEvidenceIntentKind, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise PaperExecutionInvariantError(
                "INVALID_DRY_RUN_STEP",
                "Step sequence must be an integer.",
            )
        if self.sequence < 1:
            raise PaperExecutionInvariantError(
                "INVALID_DRY_RUN_STEP",
                "Step sequence must be positive.",
            )
        if not isinstance(self.kind, PaperDryRunStepKind):
            raise PaperExecutionInvariantError(
                "INVALID_DRY_RUN_STEP",
                "Step kind is invalid.",
            )
        object.__setattr__(
            self,
            "reason_code",
            validate_no_sensitive_text(
                normalize_code(self.reason_code, "reason_code"),
                "reason_code",
            ),
        )
        if not isinstance(self.side_effect_intent_kinds, tuple):
            raise PaperExecutionInvariantError(
                "INVALID_DRY_RUN_STEP",
                "Side-effect intent kinds must be immutable.",
            )
        if not isinstance(self.evidence_intent_kinds, tuple):
            raise PaperExecutionInvariantError(
                "INVALID_DRY_RUN_STEP",
                "Evidence intent kinds must be immutable.",
            )

    def to_primitive(self) -> dict[str, object]:
        return {
            "evidence_intent_kinds": self.evidence_intent_kinds,
            "kind": self.kind,
            "lifecycle_transition_id": self.lifecycle_transition_id,
            "next_revision": self.next_revision,
            "previous_revision": self.previous_revision,
            "reason_code": self.reason_code,
            "sequence": self.sequence,
            "side_effect_intent_kinds": self.side_effect_intent_kinds,
        }


@dataclass(frozen=True, slots=True)
class PaperDryRunReceipt:
    """Deterministic dry-run receipt with no broker truth."""

    request_fingerprint: str
    command_id: PaperExecutionCommandId
    aggregate_id: PaperExecutionAggregateId
    correlation_id: PaperExecutionCorrelationId
    outcome_kind: PaperDryRunOutcomeKind
    simulated_at: datetime
    final_lifecycle_state: str
    final_revision: PaperExecutionRevision
    safe_message_code: str
    would_dispatch: bool = False
    would_reject: bool = False
    external_evidence_required: bool = False
    reconciliation_required: bool = False
    action_executed: bool = False
    broker_reference: None = None
    receipt_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_outcome(self.outcome_kind)
        object.__setattr__(
            self,
            "simulated_at",
            _require_datetime(self.simulated_at, "simulated_at"),
        )
        object.__setattr__(
            self,
            "safe_message_code",
            validate_no_sensitive_text(
                normalize_code(self.safe_message_code, "safe_message_code"),
                "safe_message_code",
            ),
        )
        object.__setattr__(self, "action_executed", False)
        object.__setattr__(self, "broker_reference", None)
        object.__setattr__(
            self,
            "receipt_fingerprint",
            dry_run_receipt_fingerprint(self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "receipt_fingerprint": self.receipt_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "action_executed": self.action_executed,
            "aggregate_id": self.aggregate_id,
            "broker_reference": self.broker_reference,
            "command_id": self.command_id,
            "correlation_id": self.correlation_id,
            "external_evidence_required": self.external_evidence_required,
            "final_lifecycle_state": self.final_lifecycle_state,
            "final_revision": self.final_revision,
            "outcome_kind": self.outcome_kind,
            "reconciliation_required": self.reconciliation_required,
            "request_fingerprint": self.request_fingerprint,
            "safe_message_code": self.safe_message_code,
            "simulated_at": self.simulated_at,
            "would_dispatch": self.would_dispatch,
            "would_reject": self.would_reject,
        }


@dataclass(frozen=True, slots=True)
class PaperDryRunFailure:
    """Immutable normalized dry-run failure."""

    request_fingerprint: str
    reason: PaperDryRunFailureReason
    safe_message_code: str
    command_id: PaperExecutionCommandId
    aggregate_id: PaperExecutionAggregateId
    correlation_id: PaperExecutionCorrelationId
    lifecycle_transition_id: str | None = None
    failure_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.reason, PaperDryRunFailureReason):
            raise PaperExecutionInvariantError(
                "INVALID_DRY_RUN_FAILURE",
                "Failure reason is invalid.",
            )
        object.__setattr__(
            self,
            "safe_message_code",
            validate_no_sensitive_text(
                normalize_code(self.safe_message_code, "safe_message_code"),
                "safe_message_code",
            ),
        )
        object.__setattr__(
            self,
            "failure_fingerprint",
            dry_run_failure_fingerprint(self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "failure_fingerprint": self.failure_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "aggregate_id": self.aggregate_id,
            "command_id": self.command_id,
            "correlation_id": self.correlation_id,
            "lifecycle_transition_id": self.lifecycle_transition_id,
            "reason": self.reason,
            "request_fingerprint": self.request_fingerprint,
            "safe_message_code": self.safe_message_code,
        }


@dataclass(frozen=True, slots=True)
class PaperDryRunRequest:
    """Explicit immutable request for dry-run orchestration."""

    command: PaperExecutionCommand
    eligibility_policy: PaperExecutionEligibilityPolicy
    evaluated_at: datetime
    initial_lifecycle: PaperExecutionLifecycle
    lifecycle_context: PaperExecutionTransitionContext
    prior_result: "PaperDryRunResult | None" = None
    effect_mode: PaperExecutionEffectMode = PaperExecutionEffectMode.DRY_RUN
    request_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.command, PaperExecutionCommand):
            raise PaperExecutionInvariantError(
                "INVALID_DRY_RUN_REQUEST",
                "Dry-run request requires a PaperExecutionCommand.",
            )
        if not isinstance(self.eligibility_policy, PaperExecutionEligibilityPolicy):
            raise PaperExecutionInvariantError(
                "INVALID_DRY_RUN_REQUEST",
                "Dry-run request requires an eligibility policy.",
            )
        object.__setattr__(
            self,
            "evaluated_at",
            _require_datetime(self.evaluated_at, "evaluated_at"),
        )
        if not isinstance(self.initial_lifecycle, PaperExecutionLifecycle):
            raise PaperExecutionInvariantError(
                "INVALID_DRY_RUN_REQUEST",
                "Dry-run request requires an initial lifecycle.",
            )
        if not isinstance(self.lifecycle_context, PaperExecutionTransitionContext):
            raise PaperExecutionInvariantError(
                "INVALID_DRY_RUN_REQUEST",
                "Dry-run request requires lifecycle guard facts.",
            )
        if self.effect_mode is not PaperExecutionEffectMode.DRY_RUN:
            raise PaperExecutionInvariantError(
                "DRY_RUN_MODE_REQUIRED",
                "Dry-run requests require DRY_RUN effect mode.",
            )
        if self.command.aggregate_id != self.initial_lifecycle.aggregate_id:
            raise PaperExecutionInvariantError(
                "DRY_RUN_AGGREGATE_MISMATCH",
                "Command and lifecycle aggregate must match.",
            )
        if self.command.correlation_id != self.initial_lifecycle.correlation_id:
            raise PaperExecutionInvariantError(
                "DRY_RUN_CORRELATION_MISMATCH",
                "Command and lifecycle correlation must match.",
            )
        object.__setattr__(
            self,
            "request_fingerprint",
            dry_run_request_fingerprint(self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "request_fingerprint": self.request_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "command": self.command.to_primitive(),
            "effect_mode": self.effect_mode,
            "eligibility_policy": self.eligibility_policy.to_primitive(),
            "evaluated_at": self.evaluated_at,
            "initial_lifecycle": self.initial_lifecycle.to_primitive(),
            "lifecycle_context": self.lifecycle_context,
        }


@dataclass(frozen=True, slots=True)
class PaperDryRunResult:
    """Deterministic dry-run result with immutable safety invariants."""

    outcome_kind: PaperDryRunOutcomeKind
    request_fingerprint: str
    command_id: PaperExecutionCommandId
    aggregate_id: PaperExecutionAggregateId
    correlation_id: PaperExecutionCorrelationId
    eligibility_result: PaperExecutionEligibilityResult | None
    initial_lifecycle: PaperExecutionLifecycle
    final_lifecycle: PaperExecutionLifecycle
    steps: tuple[PaperDryRunStep, ...]
    receipt: PaperDryRunReceipt | None
    failure: PaperDryRunFailure | None
    lifecycle_transition_ids: tuple[str, ...]
    initial_revision: PaperExecutionRevision
    final_revision: PaperExecutionRevision
    replayed: bool = False
    external_evidence_required: bool = False
    reconciliation_required: bool = False
    execution_authorized: bool = False
    action_executed: bool = False
    broker_accessed: bool = False
    simulator_accessed: bool = False
    persistence_accessed: bool = False
    runtime_changed: bool = False
    live_authorized: bool = False
    result_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_outcome(self.outcome_kind)
        if not isinstance(self.steps, tuple):
            raise PaperExecutionInvariantError(
                "INVALID_DRY_RUN_RESULT",
                "Dry-run steps must be immutable.",
            )
        if not all(isinstance(step, PaperDryRunStep) for step in self.steps):
            raise PaperExecutionInvariantError(
                "INVALID_DRY_RUN_RESULT",
                "Dry-run steps must contain PaperDryRunStep values.",
            )
        object.__setattr__(self, "execution_authorized", False)
        object.__setattr__(self, "action_executed", False)
        object.__setattr__(self, "broker_accessed", False)
        object.__setattr__(self, "simulator_accessed", False)
        object.__setattr__(self, "persistence_accessed", False)
        object.__setattr__(self, "runtime_changed", False)
        object.__setattr__(self, "live_authorized", False)
        object.__setattr__(
            self,
            "result_fingerprint",
            dry_run_result_fingerprint(self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "result_fingerprint": self.result_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "action_executed": self.action_executed,
            "aggregate_id": self.aggregate_id,
            "broker_accessed": self.broker_accessed,
            "command_id": self.command_id,
            "correlation_id": self.correlation_id,
            "eligibility_result": (
                None
                if self.eligibility_result is None
                else self.eligibility_result.to_primitive()
            ),
            "execution_authorized": self.execution_authorized,
            "external_evidence_required": self.external_evidence_required,
            "failure": None if self.failure is None else self.failure.to_primitive(),
            "final_lifecycle": self.final_lifecycle.to_primitive(),
            "final_revision": self.final_revision,
            "initial_lifecycle": self.initial_lifecycle.to_primitive(),
            "initial_revision": self.initial_revision,
            "lifecycle_transition_ids": self.lifecycle_transition_ids,
            "live_authorized": self.live_authorized,
            "outcome_kind": self.outcome_kind,
            "persistence_accessed": self.persistence_accessed,
            "receipt": None if self.receipt is None else self.receipt.to_primitive(),
            "reconciliation_required": self.reconciliation_required,
            "replayed": self.replayed,
            "request_fingerprint": self.request_fingerprint,
            "runtime_changed": self.runtime_changed,
            "simulator_accessed": self.simulator_accessed,
            "steps": tuple(step.to_primitive() for step in self.steps),
        }


PaperDryRunDecision = PaperDryRunOutcomeKind


def _require_outcome(outcome: PaperDryRunOutcomeKind) -> None:
    if not isinstance(outcome, PaperDryRunOutcomeKind):
        raise PaperExecutionInvariantError(
            "INVALID_DRY_RUN_OUTCOME",
            "Dry-run outcome is invalid.",
        )


def _require_datetime(value: datetime, field_name: str) -> datetime:
    normalized = require_datetime(value, field_name)
    if normalized.tzinfo is None or normalized.utcoffset() is None:
        raise PaperExecutionInvariantError(
            "TIMEZONE_AWARE_REQUIRED",
            f"{field_name} must be timezone-aware.",
        )
    return normalized
