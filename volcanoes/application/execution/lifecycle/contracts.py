"""Immutable contracts for the pure Paper execution lifecycle core."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from volcanoes.application.execution.contracts._validation import (
    normalize_alias,
    normalize_code,
    require_decimal,
    validate_no_sensitive_text,
)
from volcanoes.application.execution.enums import PaperExecutionMode
from volcanoes.application.execution.identities import (
    PaperBrokerOrderReference,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionIdempotencyKey,
    PaperExecutionRevision,
)
from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionLifecycleEvidenceIntentKind,
    PaperExecutionLifecycleGuard,
    PaperExecutionLifecycleInputCategory,
    PaperExecutionLifecycleInputType,
    PaperExecutionLifecycleSideEffectIntentKind,
    PaperExecutionLifecycleState,
    PaperExecutionReconciliationOutcome,
    PaperExecutionReplayKind,
    PaperExecutionTransitionDecisionType,
)

COMMAND_TERMINAL_STATES = frozenset(
    {
        PaperExecutionLifecycleState.INELIGIBLE,
        PaperExecutionLifecycleState.ABORTED_BEFORE_DISPATCH,
        PaperExecutionLifecycleState.BROKER_REJECTED,
        PaperExecutionLifecycleState.REPLACED,
        PaperExecutionLifecycleState.FAILED_TERMINAL,
    }
)

BROKER_ORDER_TERMINAL_STATES = frozenset(
    {
        PaperExecutionLifecycleState.FILLED,
        PaperExecutionLifecycleState.CANCELLED,
        PaperExecutionLifecycleState.BROKER_REJECTED,
    }
)

RESTRICTED_NON_TERMINAL_STATES = frozenset(
    {
        PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
        PaperExecutionLifecycleState.RECONCILIATION_REQUIRED,
    }
)


def is_command_terminal(state: PaperExecutionLifecycleState) -> bool:
    """Return whether state is terminal for the current command."""

    return state in COMMAND_TERMINAL_STATES


def is_broker_order_terminal(state: PaperExecutionLifecycleState) -> bool:
    """Return whether state represents terminal broker-order truth."""

    return state in BROKER_ORDER_TERMINAL_STATES


def is_aggregate_terminal(
    state: PaperExecutionLifecycleState,
    *,
    has_remaining_broker_reference: bool = False,
) -> bool:
    """Return whether state is terminal for the aggregate."""

    if state in {
        PaperExecutionLifecycleState.FILLED,
        PaperExecutionLifecycleState.FAILED_TERMINAL,
    }:
        return True
    return (
        state is PaperExecutionLifecycleState.CANCELLED
        and not has_remaining_broker_reference
    )


@dataclass(frozen=True, slots=True)
class PaperExecutionLifecycleSideEffectIntent:
    """Descriptive future side-effect intent; never executable."""

    kind: PaperExecutionLifecycleSideEffectIntentKind
    reason_code: str = "NONE"

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PaperExecutionLifecycleSideEffectIntentKind):
            raise TypeError("kind must be a side-effect intent kind.")
        object.__setattr__(
            self,
            "reason_code",
            validate_no_sensitive_text(
                normalize_code(self.reason_code, "reason_code"), "reason_code"
            ),
        )

    def to_primitive(self) -> dict[str, object]:
        return {"kind": self.kind, "reason_code": self.reason_code}


@dataclass(frozen=True, slots=True)
class PaperExecutionLifecycleEvidenceIntent:
    """Descriptive future evidence intent; never persisted by this core."""

    kind: PaperExecutionLifecycleEvidenceIntentKind
    reason_code: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PaperExecutionLifecycleEvidenceIntentKind):
            raise TypeError("kind must be an evidence intent kind.")
        object.__setattr__(
            self,
            "reason_code",
            validate_no_sensitive_text(
                normalize_code(self.reason_code, "reason_code"), "reason_code"
            ),
        )

    def to_primitive(self) -> dict[str, object]:
        return {"kind": self.kind, "reason_code": self.reason_code}


@dataclass(frozen=True, slots=True)
class PaperExecutionLifecycle:
    """Immutable Paper execution lifecycle aggregate."""

    aggregate_id: PaperExecutionAggregateId
    state: PaperExecutionLifecycleState
    revision: PaperExecutionRevision
    correlation_id: PaperExecutionCorrelationId
    last_command_id: PaperExecutionCommandId | None = None
    last_command_payload_fingerprint: str | None = None
    last_idempotency_key: PaperExecutionIdempotencyKey | None = None
    last_idempotency_payload_fingerprint: str | None = None
    broker_order_reference: PaperBrokerOrderReference | None = None
    last_broker_observation_id: str | None = None
    last_broker_observation_fingerprint: str | None = None
    requested_quantity: Decimal | None = None
    cumulative_filled_quantity: Decimal = Decimal("0")
    active_replacement_command_id: PaperExecutionCommandId | None = None
    reconciliation_required: bool = False
    outcome_unknown: bool = False
    last_transition_id: str | None = None
    last_receipt_fingerprint: str | None = None
    last_failure_fingerprint: str | None = None
    mode: PaperExecutionMode = PaperExecutionMode.PAPER

    def __post_init__(self) -> None:
        if self.mode is not PaperExecutionMode.PAPER:
            raise ValueError("Paper execution lifecycle requires Paper mode.")
        if not isinstance(self.state, PaperExecutionLifecycleState):
            raise TypeError("state must be a lifecycle state.")
        _require_type(self.aggregate_id, PaperExecutionAggregateId, "aggregate_id")
        _require_type(self.revision, PaperExecutionRevision, "revision")
        _require_type(
            self.correlation_id, PaperExecutionCorrelationId, "correlation_id"
        )
        if self.requested_quantity is not None:
            object.__setattr__(
                self,
                "requested_quantity",
                require_decimal(self.requested_quantity, "requested_quantity"),
            )
        object.__setattr__(
            self,
            "cumulative_filled_quantity",
            require_decimal(
                self.cumulative_filled_quantity, "cumulative_filled_quantity"
            ),
        )
        if self.cumulative_filled_quantity < Decimal("0"):
            raise ValueError("cumulative_filled_quantity cannot be negative.")
        for name in (
            "last_command_payload_fingerprint",
            "last_idempotency_payload_fingerprint",
            "last_broker_observation_id",
            "last_broker_observation_fingerprint",
            "last_transition_id",
            "last_receipt_fingerprint",
            "last_failure_fingerprint",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, normalize_alias(value, name))

    @classmethod
    def initial(
        cls,
        *,
        aggregate_id: PaperExecutionAggregateId,
        correlation_id: PaperExecutionCorrelationId,
        requested_quantity: Decimal | None = None,
    ) -> "PaperExecutionLifecycle":
        """Create the inert initial local lifecycle state."""

        return cls(
            aggregate_id=aggregate_id,
            state=PaperExecutionLifecycleState.CREATED,
            revision=PaperExecutionRevision.initial(),
            correlation_id=correlation_id,
            requested_quantity=requested_quantity,
            last_transition_id="PX-TRN-001",
        )

    @property
    def command_terminal(self) -> bool:
        return is_command_terminal(self.state)

    @property
    def aggregate_terminal(self) -> bool:
        return is_aggregate_terminal(
            self.state,
            has_remaining_broker_reference=self.broker_order_reference is not None
            and self.state is PaperExecutionLifecycleState.CANCELLED
            and self.cumulative_filled_quantity > Decimal("0"),
        )

    @property
    def broker_order_terminal(self) -> bool:
        return is_broker_order_terminal(self.state)

    def to_primitive(self) -> dict[str, object]:
        return {
            "active_replacement_command_id": self.active_replacement_command_id,
            "aggregate_id": self.aggregate_id,
            "broker_order_reference": self.broker_order_reference,
            "correlation_id": self.correlation_id,
            "cumulative_filled_quantity": self.cumulative_filled_quantity,
            "last_broker_observation_fingerprint": (
                self.last_broker_observation_fingerprint
            ),
            "last_broker_observation_id": self.last_broker_observation_id,
            "last_command_id": self.last_command_id,
            "last_command_payload_fingerprint": self.last_command_payload_fingerprint,
            "last_failure_fingerprint": self.last_failure_fingerprint,
            "last_idempotency_key": self.last_idempotency_key,
            "last_idempotency_payload_fingerprint": (
                self.last_idempotency_payload_fingerprint
            ),
            "last_receipt_fingerprint": self.last_receipt_fingerprint,
            "last_transition_id": self.last_transition_id,
            "mode": self.mode,
            "outcome_unknown": self.outcome_unknown,
            "reconciliation_required": self.reconciliation_required,
            "requested_quantity": self.requested_quantity,
            "revision": self.revision,
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class PaperExecutionLifecycleInput:
    """Immutable lifecycle input or observation."""

    input_type: PaperExecutionLifecycleInputType
    command_id: PaperExecutionCommandId
    aggregate_id: PaperExecutionAggregateId
    correlation_id: PaperExecutionCorrelationId
    idempotency_key: PaperExecutionIdempotencyKey | None = None
    command_payload_fingerprint: str | None = None
    idempotency_payload_fingerprint: str | None = None
    broker_observation_id: str | None = None
    broker_observation_fingerprint: str | None = None
    receipt_fingerprint: str | None = None
    failure_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.input_type, PaperExecutionLifecycleInputType):
            raise TypeError("input_type must be a lifecycle input type.")
        for value, expected, name in (
            (self.command_id, PaperExecutionCommandId, "command_id"),
            (self.aggregate_id, PaperExecutionAggregateId, "aggregate_id"),
            (self.correlation_id, PaperExecutionCorrelationId, "correlation_id"),
        ):
            _require_type(value, expected, name)
        for name in (
            "command_payload_fingerprint",
            "idempotency_payload_fingerprint",
            "broker_observation_id",
            "broker_observation_fingerprint",
            "receipt_fingerprint",
            "failure_fingerprint",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, normalize_alias(value, name))

    @property
    def category(self) -> PaperExecutionLifecycleInputCategory:
        return input_category(self.input_type)


@dataclass(frozen=True, slots=True)
class PaperExecutionTransitionContext:
    """Immutable caller-supplied guard facts."""

    expected_revision: PaperExecutionRevision
    paper_mode_confirmed: bool = True
    eligibility_decision: str | None = None
    approval_binding_valid: bool = False
    approval_time_valid: bool = False
    policy_compatible: bool = False
    idempotency_reservation_confirmed: bool = False
    emergency_stop_clearance: bool = True
    external_prerequisites_satisfied: bool = False
    broker_reference: PaperBrokerOrderReference | None = None
    observed_cumulative_fill_quantity: Decimal | None = None
    requested_quantity: Decimal | None = None
    replacement_quantity: Decimal | None = None
    reconciliation_outcome: PaperExecutionReconciliationOutcome | None = None
    reconciliation_destination: PaperExecutionLifecycleState | None = None
    broker_observation_matches_prior: bool = False
    broker_observation_conflicts_with_prior: bool = False
    command_matches_prior: bool = False
    command_conflicts_with_prior: bool = False
    idempotency_matches_prior: bool = False
    idempotency_conflicts_with_prior: bool = False

    def __post_init__(self) -> None:
        _require_type(
            self.expected_revision, PaperExecutionRevision, "expected_revision"
        )
        for name in (
            "paper_mode_confirmed",
            "approval_binding_valid",
            "approval_time_valid",
            "policy_compatible",
            "idempotency_reservation_confirmed",
            "emergency_stop_clearance",
            "external_prerequisites_satisfied",
            "broker_observation_matches_prior",
            "broker_observation_conflicts_with_prior",
            "command_matches_prior",
            "command_conflicts_with_prior",
            "idempotency_matches_prior",
            "idempotency_conflicts_with_prior",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a boolean.")
        for name in (
            "observed_cumulative_fill_quantity",
            "requested_quantity",
            "replacement_quantity",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, require_decimal(value, name))
        if self.eligibility_decision is not None:
            object.__setattr__(
                self,
                "eligibility_decision",
                normalize_code(self.eligibility_decision, "eligibility_decision"),
            )


@dataclass(frozen=True, slots=True)
class PaperExecutionTransitionSpecification:
    """Immutable accepted transition specification."""

    transition_id: str
    sources: tuple[PaperExecutionLifecycleState, ...]
    input_type: PaperExecutionLifecycleInputType
    destination: PaperExecutionLifecycleState
    guards: tuple[PaperExecutionLifecycleGuard, ...]
    side_effect_intent_kind: PaperExecutionLifecycleSideEffectIntentKind
    evidence_intent_kind: PaperExecutionLifecycleEvidenceIntentKind
    reconciliation_required: bool = False
    command_terminal: bool = False
    aggregate_terminal: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "transition_id",
            normalize_alias(self.transition_id, "transition_id"),
        )
        if not self.transition_id.startswith("PX-TRN-"):
            raise ValueError("transition_id must use PX-TRN- prefix.")
        if not isinstance(self.sources, tuple) or not self.sources:
            raise TypeError("sources must be a non-empty tuple.")
        if not all(
            isinstance(item, PaperExecutionLifecycleState) for item in self.sources
        ):
            raise TypeError("sources must contain lifecycle states.")


@dataclass(frozen=True, slots=True)
class PaperExecutionTransitionDecision:
    """Pure transition decision."""

    decision_type: PaperExecutionTransitionDecisionType
    transition_id: str | None
    previous_state: PaperExecutionLifecycleState
    next_state: PaperExecutionLifecycleState
    previous_revision: PaperExecutionRevision
    next_revision: PaperExecutionRevision
    replay_kind: PaperExecutionReplayKind
    reason_code: str
    side_effect_intents: tuple[PaperExecutionLifecycleSideEffectIntent, ...]
    evidence_intents: tuple[PaperExecutionLifecycleEvidenceIntent, ...]
    accepted: bool = False
    revision_incremented: bool = False
    reconciliation_required: bool = False
    outcome_unknown: bool = False
    command_terminal: bool = False
    aggregate_terminal: bool = False
    broker_order_terminal: bool = False
    command_id: PaperExecutionCommandId | None = None
    command_payload_fingerprint: str | None = None
    idempotency_key: PaperExecutionIdempotencyKey | None = None
    idempotency_payload_fingerprint: str | None = None
    broker_order_reference: PaperBrokerOrderReference | None = None
    broker_observation_id: str | None = None
    broker_observation_fingerprint: str | None = None
    requested_quantity: Decimal | None = None
    observed_cumulative_fill_quantity: Decimal | None = None
    active_replacement_command_id: PaperExecutionCommandId | None = None
    receipt_fingerprint: str | None = None
    failure_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision_type, PaperExecutionTransitionDecisionType):
            raise TypeError("decision_type must be a transition decision type.")
        object.__setattr__(
            self,
            "reason_code",
            validate_no_sensitive_text(
                normalize_code(self.reason_code, "reason_code"), "reason_code"
            ),
        )
        if self.transition_id is not None:
            object.__setattr__(
                self,
                "transition_id",
                normalize_alias(self.transition_id, "transition_id"),
            )
        for name in (
            "command_payload_fingerprint",
            "idempotency_payload_fingerprint",
            "broker_observation_id",
            "broker_observation_fingerprint",
            "receipt_fingerprint",
            "failure_fingerprint",
        ):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, normalize_alias(value, name))
        for name in ("requested_quantity", "observed_cumulative_fill_quantity"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, require_decimal(value, name))


def input_category(
    input_type: PaperExecutionLifecycleInputType,
) -> PaperExecutionLifecycleInputCategory:
    """Return the accepted input category."""

    if input_type in {
        PaperExecutionLifecycleInputType.OBSERVE_BROKER_ACKNOWLEDGEMENT,
        PaperExecutionLifecycleInputType.OBSERVE_BROKER_REJECTION,
        PaperExecutionLifecycleInputType.OBSERVE_PARTIAL_FILL,
        PaperExecutionLifecycleInputType.OBSERVE_FILL,
        PaperExecutionLifecycleInputType.OBSERVE_CANCELLATION_CONFIRMATION,
        PaperExecutionLifecycleInputType.OBSERVE_REPLACEMENT_CONFIRMATION,
    }:
        return PaperExecutionLifecycleInputCategory.BROKER_OBSERVATION
    if input_type in {
        PaperExecutionLifecycleInputType.REQUIRE_RECONCILIATION,
        PaperExecutionLifecycleInputType.RECORD_RECONCILIATION_RESULT,
    }:
        return PaperExecutionLifecycleInputCategory.RECONCILIATION
    if input_type in {
        PaperExecutionLifecycleInputType.PREPARE_DISPATCH,
        PaperExecutionLifecycleInputType.RECORD_DISPATCH_PENDING,
        PaperExecutionLifecycleInputType.RECORD_DISPATCH,
        PaperExecutionLifecycleInputType.RECORD_CANCELLATION_PENDING,
        PaperExecutionLifecycleInputType.RECORD_REPLACEMENT_PENDING,
        PaperExecutionLifecycleInputType.MARK_OUTCOME_UNKNOWN,
    }:
        return PaperExecutionLifecycleInputCategory.INTERNAL
    return PaperExecutionLifecycleInputCategory.APPLICATION


def _require_type(value: object, expected: type[Any], name: str) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"{name} must be {expected.__name__}.")
