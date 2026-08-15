"""Immutable storage-neutral contracts for Paper execution persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from datetime import UTC
from decimal import Decimal
from typing import Any
import hashlib
import hmac
import secrets

from volcanoes.application.execution._canonical import (
    canonical_json_text,
    canonicalize,
)
from volcanoes.application.execution.contracts import (
    PaperExecutionFailure,
    PaperExecutionReceipt,
)
from volcanoes.application.execution.contracts._validation import (
    normalize_alias,
    normalize_code,
    require_datetime,
    require_decimal,
    validate_no_sensitive_text,
)
from volcanoes.application.execution.enums import (
    PaperExecutionMode,
    PaperExecutionOperation,
)
from volcanoes.application.execution.errors import PaperExecutionContractError
from volcanoes.application.execution.fingerprints import (
    fingerprint_payload,
    validate_fingerprint,
)
from volcanoes.application.execution.identities import (
    PaperBrokerOrderReference,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionIdempotencyKey,
    PaperExecutionRevision,
)
from volcanoes.application.execution.lifecycle import (
    PaperExecutionLifecycleEvidenceIntentKind,
    PaperExecutionLifecycleInputType,
    PaperExecutionLifecycleSideEffectIntentKind,
    PaperExecutionLifecycleState,
)
from volcanoes.application.execution.persistence.enums import (
    DispatchClaimStatus,
    DispatchEffectPhase,
    DispatchResolutionStatus,
    ExecutionBrokerReferenceStatus,
    ExecutionCommandProcessingOutcome,
    ExecutionIdempotencyReservationStatus,
    ExecutionPersistenceConflictKind,
    ExecutionPersistenceConflictSeverity,
    ExecutionPersistenceResultStatus,
    ExecutionReconciliationResultClassification,
    ExecutionReplayKind,
)
from volcanoes.application.execution.persistence.errors import (
    ExecutionPersistenceInvariantError,
)

PrimitiveSnapshot = tuple[tuple[str, object], ...]
ExecutionTimestamp = datetime


def fail_closed_dispatch_control() -> "ExecutionDispatchControlRecord":
    """Build the adapter-independent V004 fail-closed singleton value."""

    return ExecutionDispatchControlRecord(
        enabled=False,
        emergency_stop_active=True,
        legacy_authority_active=True,
        generation=1,
        updated_at=datetime(1970, 1, 1, tzinfo=UTC),
        schema_version=4,
    )


@dataclass(frozen=True, slots=True)
class ExecutionDispatchClaimAttempt:
    """Caller-stable lookup identity; contains no payload or safety authority."""

    submission_id: str
    command_id: PaperExecutionCommandId
    idempotency_key: PaperExecutionIdempotencyKey
    attempt_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "submission_id", normalize_alias(self.submission_id, "submission_id")
        )
        object.__setattr__(
            self, "attempt_fingerprint", _fingerprint("psq", self.to_primitive())
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            "command_id": self.command_id,
            "idempotency_key": self.idempotency_key,
            "submission_id": self.submission_id,
        }


@dataclass(frozen=True, slots=True)
class DispatchWinnerGrant:
    """Opaque one-call capability returned only to the inserting transaction."""

    claim_token: str
    _capability: bytes = field(repr=False)
    claim_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "claim_token", normalize_alias(self.claim_token, "claim_token")
        )
        if not isinstance(self._capability, bytes) or len(self._capability) != 32:
            raise ExecutionPersistenceInvariantError(
                "INVALID_WINNER_CAPABILITY", "Winner capability must be 256 bits."
            )
        object.__setattr__(
            self,
            "claim_fingerprint",
            validate_fingerprint(self.claim_fingerprint, "pcl"),
        )

    def authenticates(self, claim: "ExecutionDispatchClaimRecord") -> bool:
        return (
            self.claim_token == claim.claim_token
            and self.claim_fingerprint == claim.record_fingerprint
            and hmac.compare_digest(
                dispatch_capability_verifier(self._capability),
                claim.capability_verifier,
            )
        )


def new_dispatch_capability() -> bytes:
    return secrets.token_bytes(32)


def dispatch_capability_verifier(capability: bytes) -> str:
    digest = hashlib.sha256(b"paper-dispatch-capability-v1\0" + capability).hexdigest()
    return "pcv-" + digest


@dataclass(frozen=True, slots=True)
class ExecutionDispatchControlRecord:
    enabled: bool
    emergency_stop_active: bool
    legacy_authority_active: bool
    generation: int
    updated_at: datetime
    schema_version: int
    mode: PaperExecutionMode = PaperExecutionMode.PAPER
    record_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_mode(self.mode)
        _require_schema_version(self.schema_version)
        _require_bool_fields(
            self, ("enabled", "emergency_stop_active", "legacy_authority_active")
        )
        if isinstance(self.generation, bool) or self.generation < 1:
            raise ExecutionPersistenceInvariantError(
                "INVALID_CONTROL_GENERATION", "Control generation must be positive."
            )
        object.__setattr__(
            self, "updated_at", require_datetime(self.updated_at, "updated_at")
        )
        object.__setattr__(
            self, "record_fingerprint", _fingerprint("pdc", self._primitive())
        )

    @property
    def permits_dispatch(self) -> bool:
        return (
            self.enabled
            and not self.emergency_stop_active
            and not self.legacy_authority_active
        )

    def _primitive(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "emergency_stop_active": self.emergency_stop_active,
            "generation": self.generation,
            "legacy_authority_active": self.legacy_authority_active,
            "mode": self.mode,
            "schema_version": self.schema_version,
            "updated_at": self.updated_at,
        }

    def to_primitive(self) -> dict[str, object]:
        return {**self._primitive(), "record_fingerprint": self.record_fingerprint}


@dataclass(frozen=True, slots=True)
class ExecutionDispatchClaimRecord:
    claim_token: str
    submission_id: str
    command_id: PaperExecutionCommandId
    aggregate_id: PaperExecutionAggregateId
    correlation_id: PaperExecutionCorrelationId
    idempotency_key: PaperExecutionIdempotencyKey
    expected_execution_revision: PaperExecutionRevision
    request_fingerprint: str
    command_record_fingerprint: str
    canonical_payload_fingerprint: str
    approval_fingerprint: str
    policy_fingerprint: str
    client_order_id: str
    capability_verifier: str
    canonical_order_json: str
    control_generation: int
    claimed_at: datetime
    schema_version: int
    mode: PaperExecutionMode = PaperExecutionMode.PAPER
    record_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_mode(self.mode)
        _require_schema_version(self.schema_version)
        for name in ("claim_token", "submission_id", "client_order_id"):
            object.__setattr__(self, name, normalize_alias(getattr(self, name), name))
        if len(self.client_order_id) != 48:
            raise ExecutionPersistenceInvariantError(
                "INVALID_CLIENT_ORDER_ID",
                "Client order identity must be 48 characters.",
            )
        for name, prefix in (
            ("request_fingerprint", "psq"),
            ("command_record_fingerprint", "pcm"),
            ("canonical_payload_fingerprint", "pcf"),
            ("approval_fingerprint", "pap"),
            ("policy_fingerprint", "pps"),
            ("capability_verifier", "pcv"),
        ):
            object.__setattr__(
                self, name, validate_fingerprint(getattr(self, name), prefix)
            )
        object.__setattr__(
            self,
            "canonical_order_json",
            _normalize_safe_json_text(self.canonical_order_json),
        )
        if isinstance(self.control_generation, bool) or self.control_generation < 1:
            raise ExecutionPersistenceInvariantError(
                "INVALID_CONTROL_GENERATION", "Control generation must be positive."
            )
        object.__setattr__(
            self, "claimed_at", require_datetime(self.claimed_at, "claimed_at")
        )
        object.__setattr__(
            self, "record_fingerprint", _fingerprint("pcl", self._primitive())
        )

    def _primitive(self) -> dict[str, object]:
        return {
            name: getattr(self, name)
            for name in (
                "aggregate_id",
                "approval_fingerprint",
                "canonical_order_json",
                "canonical_payload_fingerprint",
                "claim_token",
                "claimed_at",
                "client_order_id",
                "capability_verifier",
                "command_id",
                "command_record_fingerprint",
                "control_generation",
                "correlation_id",
                "expected_execution_revision",
                "idempotency_key",
                "mode",
                "policy_fingerprint",
                "request_fingerprint",
                "schema_version",
                "submission_id",
            )
        }

    def to_primitive(self) -> dict[str, object]:
        return {**self._primitive(), "record_fingerprint": self.record_fingerprint}

    def to_public(self) -> "ExecutionDispatchClaim":
        return ExecutionDispatchClaim(
            claim_token=self.claim_token,
            submission_id=self.submission_id,
            command_id=self.command_id,
            aggregate_id=self.aggregate_id,
            correlation_id=self.correlation_id,
            idempotency_key=self.idempotency_key,
            expected_execution_revision=self.expected_execution_revision,
            request_fingerprint=self.request_fingerprint,
            command_record_fingerprint=self.command_record_fingerprint,
            canonical_payload_fingerprint=self.canonical_payload_fingerprint,
            approval_fingerprint=self.approval_fingerprint,
            policy_fingerprint=self.policy_fingerprint,
            client_order_id=self.client_order_id,
            canonical_order_json=self.canonical_order_json,
            control_generation=self.control_generation,
            claimed_at=self.claimed_at,
            schema_version=self.schema_version,
            record_fingerprint=self.record_fingerprint,
        )


@dataclass(frozen=True, slots=True)
class ExecutionDispatchClaim:
    """Non-secret immutable claim projection for application callers."""

    claim_token: str
    submission_id: str
    command_id: PaperExecutionCommandId
    aggregate_id: PaperExecutionAggregateId
    correlation_id: PaperExecutionCorrelationId
    idempotency_key: PaperExecutionIdempotencyKey
    expected_execution_revision: PaperExecutionRevision
    request_fingerprint: str
    command_record_fingerprint: str
    canonical_payload_fingerprint: str
    approval_fingerprint: str
    policy_fingerprint: str
    client_order_id: str
    canonical_order_json: str = field(repr=False)
    control_generation: int
    claimed_at: datetime
    schema_version: int
    record_fingerprint: str

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        for name, identity_type in (
            ("command_id", PaperExecutionCommandId),
            ("aggregate_id", PaperExecutionAggregateId),
            ("correlation_id", PaperExecutionCorrelationId),
            ("idempotency_key", PaperExecutionIdempotencyKey),
            ("expected_execution_revision", PaperExecutionRevision),
        ):
            value = getattr(self, name)
            object.__setattr__(
                self,
                name,
                value if isinstance(value, identity_type) else identity_type(value),
            )
        for name in ("claim_token", "submission_id", "client_order_id"):
            object.__setattr__(self, name, normalize_alias(getattr(self, name), name))
        if len(self.client_order_id) != 48:
            raise ExecutionPersistenceInvariantError(
                "INVALID_CLIENT_ORDER_ID",
                "Client order identity must be 48 characters.",
            )
        for name, prefix in (
            ("request_fingerprint", "psq"),
            ("command_record_fingerprint", "pcm"),
            ("canonical_payload_fingerprint", "pcf"),
            ("approval_fingerprint", "pap"),
            ("policy_fingerprint", "pps"),
            ("record_fingerprint", "pcl"),
        ):
            object.__setattr__(
                self, name, validate_fingerprint(getattr(self, name), prefix)
            )
        object.__setattr__(
            self,
            "canonical_order_json",
            _normalize_safe_json_text(self.canonical_order_json),
        )
        if isinstance(self.control_generation, bool) or self.control_generation < 1:
            raise ExecutionPersistenceInvariantError(
                "INVALID_CONTROL_GENERATION", "Control generation must be positive."
            )
        object.__setattr__(
            self, "claimed_at", require_datetime(self.claimed_at, "claimed_at")
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
            if name != "canonical_order_json"
        }


@dataclass(frozen=True, slots=True)
class ExecutionDispatchAuthorizationRecord:
    claim_token: str
    control_generation: int
    authorized_at: datetime
    schema_version: int
    authorization_fingerprint: str = field(init=False)
    record_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        object.__setattr__(
            self, "claim_token", normalize_alias(self.claim_token, "claim_token")
        )
        if isinstance(self.control_generation, bool) or self.control_generation < 1:
            raise ExecutionPersistenceInvariantError(
                "INVALID_CONTROL_GENERATION", "Control generation must be positive."
            )
        object.__setattr__(
            self, "authorized_at", require_datetime(self.authorized_at, "authorized_at")
        )
        primitive = {
            "authorized_at": self.authorized_at,
            "claim_token": self.claim_token,
            "control_generation": self.control_generation,
            "schema_version": self.schema_version,
        }
        object.__setattr__(
            self, "authorization_fingerprint", _fingerprint("pda", primitive)
        )
        object.__setattr__(self, "record_fingerprint", _fingerprint("par", primitive))


@dataclass(frozen=True, slots=True)
class ExecutionDispatchResolutionRecord:
    claim_token: str
    status: DispatchResolutionStatus
    effect_phase: DispatchEffectPhase
    resolved_at: datetime
    result_fingerprint: str
    evidence_fingerprint: str
    evidence_record_fingerprint: str
    safe_reason_code: str
    reconciliation_required: bool
    operator_action_required: bool
    schema_version: int
    broker_reference: str | None = None
    observation_fingerprint: str | None = None
    conflicting_owner_aggregate_id: PaperExecutionAggregateId | None = None
    conflicting_owner_command_id: PaperExecutionCommandId | None = None
    conflicting_owner_record_fingerprint: str | None = None
    automatic_retry: bool = False
    record_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        object.__setattr__(
            self, "claim_token", normalize_alias(self.claim_token, "claim_token")
        )
        if not isinstance(self.status, DispatchResolutionStatus) or not isinstance(
            self.effect_phase, DispatchEffectPhase
        ):
            raise ExecutionPersistenceInvariantError(
                "INVALID_DISPATCH_RESOLUTION", "Dispatch resolution variant is invalid."
            )
        _require_bool_fields(
            self,
            ("reconciliation_required", "operator_action_required", "automatic_retry"),
        )
        if self.automatic_retry:
            raise ExecutionPersistenceInvariantError(
                "AUTOMATIC_RETRY_FORBIDDEN",
                "Dispatch resolution cannot enable automatic retry.",
            )
        if (
            self.status
            in {
                DispatchResolutionStatus.OUTCOME_UNKNOWN,
                DispatchResolutionStatus.EVIDENCE_RECORDING_FAILED,
                DispatchResolutionStatus.BROKER_REFERENCE_CONFLICT,
            }
            and not self.reconciliation_required
        ):
            raise ExecutionPersistenceInvariantError(
                "RECONCILIATION_REQUIRED",
                "Ambiguous dispatch resolution requires reconciliation.",
            )
        object.__setattr__(
            self, "resolved_at", require_datetime(self.resolved_at, "resolved_at")
        )
        object.__setattr__(
            self,
            "result_fingerprint",
            normalize_alias(self.result_fingerprint, "result_fingerprint"),
        )
        if self.status is DispatchResolutionStatus.PRE_EFFECT_BLOCKED:
            evidence_prefix, record_prefix = "pfl", "pfr"
        else:
            evidence_prefix, record_prefix = "prc", "prr"
        object.__setattr__(
            self,
            "evidence_fingerprint",
            validate_fingerprint(self.evidence_fingerprint, evidence_prefix),
        )
        object.__setattr__(
            self,
            "evidence_record_fingerprint",
            validate_fingerprint(self.evidence_record_fingerprint, record_prefix),
        )
        object.__setattr__(
            self,
            "safe_reason_code",
            normalize_code(self.safe_reason_code, "safe_reason_code"),
        )
        _normalize_optional_alias(self, "broker_reference")
        _normalize_optional_alias(self, "observation_fingerprint")
        owner_values = (
            self.conflicting_owner_aggregate_id,
            self.conflicting_owner_command_id,
            self.conflicting_owner_record_fingerprint,
        )
        ownership_conflict = (
            self.status is DispatchResolutionStatus.BROKER_REFERENCE_CONFLICT
        )
        if ownership_conflict:
            if (
                self.broker_reference is None
                or not isinstance(
                    self.conflicting_owner_aggregate_id, PaperExecutionAggregateId
                )
                or not isinstance(
                    self.conflicting_owner_command_id, PaperExecutionCommandId
                )
                or self.conflicting_owner_record_fingerprint is None
                or not self.operator_action_required
            ):
                raise ExecutionPersistenceInvariantError(
                    "INCOMPLETE_CONFLICT_OWNER",
                    "Broker conflict requires exact durable owner evidence.",
                )
            object.__setattr__(
                self,
                "conflicting_owner_record_fingerprint",
                validate_fingerprint(self.conflicting_owner_record_fingerprint, "pbf"),
            )
        elif any(value is not None for value in owner_values):
            raise ExecutionPersistenceInvariantError(
                "UNEXPECTED_CONFLICT_OWNER",
                "Non-conflict resolution cannot carry owner evidence.",
            )
        object.__setattr__(
            self,
            "record_fingerprint",
            _fingerprint(
                "pds",
                {
                    name: getattr(self, name)
                    for name in (
                        "automatic_retry",
                        "broker_reference",
                        "claim_token",
                        "conflicting_owner_aggregate_id",
                        "conflicting_owner_command_id",
                        "conflicting_owner_record_fingerprint",
                        "effect_phase",
                        "evidence_fingerprint",
                        "evidence_record_fingerprint",
                        "observation_fingerprint",
                        "operator_action_required",
                        "reconciliation_required",
                        "resolved_at",
                        "result_fingerprint",
                        "safe_reason_code",
                        "schema_version",
                        "status",
                    )
                },
            ),
        )


@dataclass(frozen=True, slots=True)
class DispatchClaimResult:
    status: DispatchClaimStatus
    claim: ExecutionDispatchClaim | None
    schema_version: int
    reason_code: str
    authorized: bool = False
    authorization: ExecutionDispatchAuthorizationRecord | None = None
    aggregate: ExecutionAggregateRecord | None = None
    result_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        if not isinstance(self.status, DispatchClaimStatus):
            raise ExecutionPersistenceInvariantError(
                "INVALID_CLAIM_STATUS", "Claim status is invalid."
            )
        if (
            self.status
            in {
                DispatchClaimStatus.ACQUIRED,
                DispatchClaimStatus.EXACT_REPLAY,
                DispatchClaimStatus.ALREADY_CLAIMED,
            }
            and self.claim is None
        ):
            raise ExecutionPersistenceInvariantError(
                "CLAIM_REQUIRED", "Claim result requires durable claim evidence."
            )
        if self.claim is not None and not isinstance(
            self.claim, ExecutionDispatchClaim
        ):
            raise ExecutionPersistenceInvariantError(
                "PUBLIC_CLAIM_REQUIRED",
                "Claim results may contain only the non-secret public projection.",
            )
        if not isinstance(self.authorized, bool):
            raise ExecutionPersistenceInvariantError(
                "INVALID_AUTHORITY_RESULT", "Authorized must be boolean."
            )
        if self.authorized != (
            self.status is DispatchClaimStatus.ACQUIRED
            and self.authorization is not None
            and self.aggregate is not None
        ):
            raise ExecutionPersistenceInvariantError(
                "INVALID_AUTHORITY_RESULT",
                "Only an authorized new winner may carry authority facts.",
            )
        object.__setattr__(
            self, "reason_code", normalize_code(self.reason_code, "reason_code")
        )
        object.__setattr__(
            self,
            "result_fingerprint",
            _fingerprint(
                "pcr",
                {
                    "claim_fingerprint": (
                        None if self.claim is None else self.claim.record_fingerprint
                    ),
                    "authorization_fingerprint": (
                        None
                        if self.authorization is None
                        else self.authorization.authorization_fingerprint
                    ),
                    "authorized": self.authorized,
                    "reason_code": self.reason_code,
                    "schema_version": self.schema_version,
                    "status": self.status,
                },
            ),
        )


@dataclass(frozen=True, slots=True)
class DispatchOutcomeWriteSet:
    """Complete storage-neutral write set for one atomic dispatch outcome."""

    claim: ExecutionDispatchClaim
    authorization: ExecutionDispatchAuthorizationRecord
    expected_revision: PaperExecutionRevision
    evidence: ExecutionReceiptRecord | ExecutionFailureRecord
    transitions: tuple[ExecutionTransitionRecord, ...]
    aggregate: ExecutionAggregateRecord
    resolution: ExecutionDispatchResolutionRecord
    broker_reference: ExecutionBrokerReferenceRecord | None = None

    def __post_init__(self) -> None:
        if self.claim.client_order_id != _public_client_order_id(self.claim):
            raise ExecutionPersistenceInvariantError(
                "OUTCOME_CLIENT_ORDER_MISMATCH",
                "Outcome claim client-order identity is invalid.",
            )
        if self.claim.claim_token != self.authorization.claim_token:
            raise ExecutionPersistenceInvariantError(
                "OUTCOME_AUTHORITY_MISMATCH", "Authorization does not bind the claim."
            )
        if self.authorization.control_generation != self.claim.control_generation:
            raise ExecutionPersistenceInvariantError(
                "OUTCOME_GENERATION_MISMATCH", "Authorization generation is invalid."
            )
        if self.resolution.claim_token != self.claim.claim_token:
            raise ExecutionPersistenceInvariantError(
                "OUTCOME_RESOLUTION_MISMATCH", "Resolution does not bind the claim."
            )
        if (
            self.aggregate.aggregate_id != self.claim.aggregate_id
            or self.aggregate.correlation_id != self.claim.correlation_id
            or not self.transitions
            or self.transitions[-1].next_revision != self.aggregate.execution_revision
        ):
            raise ExecutionPersistenceInvariantError(
                "OUTCOME_TRANSITION_MISMATCH",
                "Outcome transitions do not bind the aggregate.",
            )
        if self.transitions[0].previous_revision != self.expected_revision:
            raise ExecutionPersistenceInvariantError(
                "OUTCOME_REVISION_MISMATCH", "Outcome expected revision is invalid."
            )
        if (
            self.expected_revision != self.claim.expected_execution_revision
            or self.transitions[0].source_state
            is not PaperExecutionLifecycleState.DISPATCH_PENDING
            or len(self.transitions)
            != int(self.aggregate.execution_revision) - int(self.expected_revision)
        ):
            raise ExecutionPersistenceInvariantError(
                "OUTCOME_STARTING_STATE_MISMATCH",
                "Outcome chain must begin at the claimed dispatch-pending revision.",
            )
        expected_edges = {
            DispatchResolutionStatus.PRE_EFFECT_BLOCKED: (
                (
                    "PX-TRN-029",
                    PaperExecutionLifecycleInputType.ABORT_BEFORE_DISPATCH,
                    PaperExecutionLifecycleState.DISPATCH_PENDING,
                    PaperExecutionLifecycleState.ABORTED_BEFORE_DISPATCH,
                ),
            ),
            DispatchResolutionStatus.ACKNOWLEDGED: (
                (
                    "PX-TRN-009",
                    PaperExecutionLifecycleInputType.RECORD_DISPATCH,
                    PaperExecutionLifecycleState.DISPATCH_PENDING,
                    PaperExecutionLifecycleState.DISPATCHED,
                ),
                (
                    "PX-TRN-010",
                    PaperExecutionLifecycleInputType.OBSERVE_BROKER_ACKNOWLEDGEMENT,
                    PaperExecutionLifecycleState.DISPATCHED,
                    PaperExecutionLifecycleState.BROKER_ACKNOWLEDGED,
                ),
            ),
            DispatchResolutionStatus.BROKER_REJECTED: (
                (
                    "PX-TRN-009",
                    PaperExecutionLifecycleInputType.RECORD_DISPATCH,
                    PaperExecutionLifecycleState.DISPATCH_PENDING,
                    PaperExecutionLifecycleState.DISPATCHED,
                ),
                (
                    "PX-TRN-011",
                    PaperExecutionLifecycleInputType.OBSERVE_BROKER_REJECTION,
                    PaperExecutionLifecycleState.DISPATCHED,
                    PaperExecutionLifecycleState.BROKER_REJECTED,
                ),
            ),
            DispatchResolutionStatus.OUTCOME_UNKNOWN: (
                (
                    "PX-TRN-009",
                    PaperExecutionLifecycleInputType.RECORD_DISPATCH,
                    PaperExecutionLifecycleState.DISPATCH_PENDING,
                    PaperExecutionLifecycleState.DISPATCHED,
                ),
                (
                    "PX-TRN-012",
                    PaperExecutionLifecycleInputType.MARK_OUTCOME_UNKNOWN,
                    PaperExecutionLifecycleState.DISPATCHED,
                    PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
                ),
            ),
            DispatchResolutionStatus.BROKER_REFERENCE_CONFLICT: (
                (
                    "PX-TRN-009",
                    PaperExecutionLifecycleInputType.RECORD_DISPATCH,
                    PaperExecutionLifecycleState.DISPATCH_PENDING,
                    PaperExecutionLifecycleState.DISPATCHED,
                ),
                (
                    "PX-TRN-012",
                    PaperExecutionLifecycleInputType.MARK_OUTCOME_UNKNOWN,
                    PaperExecutionLifecycleState.DISPATCHED,
                    PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
                ),
            ),
        }[self.resolution.status]
        if len(self.transitions) != len(expected_edges):
            raise ExecutionPersistenceInvariantError(
                "OUTCOME_TRANSITION_COUNT_MISMATCH",
                "Outcome transition count is invalid.",
            )
        previous_state: PaperExecutionLifecycleState = self.transitions[0].source_state
        previous_revision = self.expected_revision
        seen_records: set[str] = set()
        for transition, expected_edge in zip(
            self.transitions, expected_edges, strict=True
        ):
            if (
                transition.aggregate_id != self.claim.aggregate_id
                or transition.command_id != self.claim.command_id
                or transition.correlation_id != self.claim.correlation_id
                or transition.idempotency_key != self.claim.idempotency_key
                or transition.source_state is not previous_state
                or transition.previous_revision != previous_revision
                or (
                    transition.transition_id,
                    transition.lifecycle_input_kind,
                    transition.source_state,
                    transition.destination_state,
                )
                != expected_edge
                or transition.transition_record_id
                != f"{self.claim.claim_token}-{transition.transition_id}"
                or transition.transition_record_id in seen_records
            ):
                raise ExecutionPersistenceInvariantError(
                    "OUTCOME_IDENTITY_MISMATCH",
                    "Outcome transition identity is invalid.",
                )
            seen_records.add(transition.transition_record_id)
            previous_state = transition.destination_state
            previous_revision = transition.next_revision
        if self.aggregate.lifecycle_state is not previous_state:
            raise ExecutionPersistenceInvariantError(
                "OUTCOME_AGGREGATE_MISMATCH", "Outcome aggregate state is invalid."
            )
        if isinstance(self.evidence, ExecutionReceiptRecord):
            if self.resolution.status is DispatchResolutionStatus.PRE_EFFECT_BLOCKED:
                raise ExecutionPersistenceInvariantError(
                    "OUTCOME_EVIDENCE_MISMATCH",
                    "Pre-effect outcome requires failure evidence.",
                )
            evidence_command: PaperExecutionCommandId | None = (
                self.evidence.receipt.command_id
            )
            evidence_aggregate: PaperExecutionAggregateId | None = (
                self.evidence.receipt.aggregate_id
            )
            evidence_correlation: PaperExecutionCorrelationId | None = (
                self.evidence.receipt.correlation_id
            )
            identity = self.evidence.receipt.receipt_fingerprint
            wrapper = self.evidence.record_fingerprint
        else:
            if (
                self.resolution.status
                is not DispatchResolutionStatus.PRE_EFFECT_BLOCKED
            ):
                raise ExecutionPersistenceInvariantError(
                    "OUTCOME_EVIDENCE_MISMATCH",
                    "Observed outcome requires receipt evidence.",
                )
            evidence_command = self.evidence.failure.command_id
            evidence_aggregate = self.evidence.failure.aggregate_id
            evidence_correlation = self.evidence.failure.correlation_id
            identity = self.evidence.failure.failure_fingerprint
            wrapper = self.evidence.record_fingerprint
        if (
            evidence_command != self.claim.command_id
            or evidence_aggregate != self.claim.aggregate_id
            or evidence_correlation != self.claim.correlation_id
            or self.resolution.evidence_fingerprint != identity
            or self.resolution.evidence_record_fingerprint != wrapper
        ):
            raise ExecutionPersistenceInvariantError(
                "OUTCOME_EVIDENCE_MISMATCH", "Resolution evidence binding is invalid."
            )
        final = self.transitions[-1]
        expected_receipt = (
            identity if isinstance(self.evidence, ExecutionReceiptRecord) else None
        )
        expected_failure = (
            identity if isinstance(self.evidence, ExecutionFailureRecord) else None
        )
        if (
            any(
                transition.receipt_fingerprint is not None
                or transition.failure_fingerprint is not None
                or transition.broker_observation_identity is not None
                for transition in self.transitions[:-1]
            )
            or final.receipt_fingerprint != expected_receipt
            or final.failure_fingerprint != expected_failure
            or self.aggregate.last_receipt_fingerprint != expected_receipt
            or self.aggregate.last_failure_fingerprint != expected_failure
        ):
            raise ExecutionPersistenceInvariantError(
                "OUTCOME_EVIDENCE_MISMATCH", "Outcome evidence chain is invalid."
            )
        ownership_conflict = (
            self.resolution.status is DispatchResolutionStatus.BROKER_REFERENCE_CONFLICT
        )
        if ownership_conflict and (
            self.resolution.broker_reference is None
            or self.broker_reference is not None
        ):
            raise ExecutionPersistenceInvariantError(
                "OUTCOME_BROKER_OWNERSHIP_MISMATCH",
                "Broker conflict must preserve only the observed reference.",
            )
        if not ownership_conflict and (
            (self.resolution.broker_reference is None)
            != (self.broker_reference is None)
        ):
            raise ExecutionPersistenceInvariantError(
                "OUTCOME_BROKER_OWNERSHIP_MISMATCH",
                "Outcome broker ownership is incomplete.",
            )
        if self.broker_reference is not None and (
            self.broker_reference.aggregate_id != self.claim.aggregate_id
            or self.broker_reference.command_id != self.claim.command_id
            or str(self.broker_reference.broker_reference)
            != self.resolution.broker_reference
        ):
            raise ExecutionPersistenceInvariantError(
                "OUTCOME_BROKER_OWNERSHIP_MISMATCH",
                "Broker reference does not bind the outcome.",
            )


def _public_client_order_id(claim: ExecutionDispatchClaim) -> str:
    digest = fingerprint_payload(
        "pci",
        {
            "domain": "paper-client-order-v1",
            "inputs": {
                "canonical_payload_fingerprint": claim.canonical_payload_fingerprint,
                "command_id": claim.command_id,
                "idempotency_key": claim.idempotency_key,
                "submission_id": claim.submission_id,
            },
        },
    ).rsplit("-", 1)[-1]
    return "paper-" + digest[:42]


@dataclass(frozen=True, slots=True)
class ExecutionAggregateRecord:
    """Materialized local execution lifecycle view."""

    aggregate_id: PaperExecutionAggregateId
    correlation_id: PaperExecutionCorrelationId
    lifecycle_state: PaperExecutionLifecycleState
    execution_revision: PaperExecutionRevision
    cumulative_filled_quantity: Decimal
    outcome_unknown: bool
    reconciliation_required: bool
    command_terminal: bool
    aggregate_terminal: bool
    last_transition_id: str
    created_at: datetime
    updated_at: datetime
    schema_version: int
    requested_quantity: Decimal | None = None
    active_broker_reference: PaperBrokerOrderReference | None = None
    last_command_id: PaperExecutionCommandId | None = None
    last_idempotency_key: PaperExecutionIdempotencyKey | None = None
    last_receipt_fingerprint: str | None = None
    last_failure_fingerprint: str | None = None
    mode: PaperExecutionMode = PaperExecutionMode.PAPER
    record_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_mode(self.mode)
        _require_schema_version(self.schema_version)
        _require_bool_fields(
            self,
            (
                "outcome_unknown",
                "reconciliation_required",
                "command_terminal",
                "aggregate_terminal",
            ),
        )
        object.__setattr__(
            self,
            "cumulative_filled_quantity",
            require_decimal(
                self.cumulative_filled_quantity,
                "cumulative_filled_quantity",
            ),
        )
        if self.cumulative_filled_quantity < Decimal("0"):
            raise ExecutionPersistenceInvariantError(
                "NEGATIVE_FILLED_QUANTITY",
                "Cumulative filled quantity cannot be negative.",
            )
        if self.requested_quantity is not None:
            object.__setattr__(
                self,
                "requested_quantity",
                require_decimal(self.requested_quantity, "requested_quantity"),
            )
        object.__setattr__(
            self,
            "last_transition_id",
            normalize_alias(self.last_transition_id, "last_transition_id"),
        )
        _normalize_optional_fingerprint(self, "last_receipt_fingerprint", "prc")
        _normalize_optional_fingerprint(self, "last_failure_fingerprint", "pfl")
        object.__setattr__(
            self,
            "created_at",
            require_datetime(self.created_at, "created_at"),
        )
        object.__setattr__(
            self,
            "updated_at",
            require_datetime(self.updated_at, "updated_at"),
        )
        if self.updated_at < self.created_at:
            raise ExecutionPersistenceInvariantError(
                "UPDATED_BEFORE_CREATED",
                "Updated timestamp cannot precede created timestamp.",
            )
        object.__setattr__(
            self,
            "record_fingerprint",
            _fingerprint("par", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "record_fingerprint": self.record_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "active_broker_reference": self.active_broker_reference,
            "aggregate_id": self.aggregate_id,
            "aggregate_terminal": self.aggregate_terminal,
            "command_terminal": self.command_terminal,
            "correlation_id": self.correlation_id,
            "created_at": self.created_at,
            "cumulative_filled_quantity": self.cumulative_filled_quantity,
            "execution_revision": self.execution_revision,
            "last_command_id": self.last_command_id,
            "last_failure_fingerprint": self.last_failure_fingerprint,
            "last_idempotency_key": self.last_idempotency_key,
            "last_receipt_fingerprint": self.last_receipt_fingerprint,
            "last_transition_id": self.last_transition_id,
            "lifecycle_state": self.lifecycle_state,
            "mode": self.mode,
            "outcome_unknown": self.outcome_unknown,
            "reconciliation_required": self.reconciliation_required,
            "requested_quantity": self.requested_quantity,
            "schema_version": self.schema_version,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True, slots=True)
class ExecutionCommandRecord:
    """Immutable durable command-envelope record."""

    command_id: PaperExecutionCommandId
    aggregate_id: PaperExecutionAggregateId
    correlation_id: PaperExecutionCorrelationId
    idempotency_key: PaperExecutionIdempotencyKey
    operation: PaperExecutionOperation
    expected_execution_revision: PaperExecutionRevision
    canonical_payload_fingerprint: str
    canonical_command_json: str
    approval_fingerprint: str
    policy_fingerprint: str
    received_at: datetime
    processing_outcome: ExecutionCommandProcessingOutcome
    schema_version: int
    mode: PaperExecutionMode = PaperExecutionMode.PAPER
    record_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_mode(self.mode)
        _require_schema_version(self.schema_version)
        if not isinstance(self.operation, PaperExecutionOperation):
            raise ExecutionPersistenceInvariantError(
                "INVALID_OPERATION",
                "Command operation is invalid.",
            )
        if not isinstance(
            self.processing_outcome,
            ExecutionCommandProcessingOutcome,
        ):
            raise ExecutionPersistenceInvariantError(
                "INVALID_PROCESSING_OUTCOME",
                "Command processing outcome is invalid.",
            )
        object.__setattr__(
            self,
            "canonical_payload_fingerprint",
            validate_fingerprint(self.canonical_payload_fingerprint, "pcf"),
        )
        object.__setattr__(
            self,
            "approval_fingerprint",
            validate_fingerprint(self.approval_fingerprint, "pap"),
        )
        object.__setattr__(
            self,
            "policy_fingerprint",
            validate_fingerprint(self.policy_fingerprint, "pps"),
        )
        object.__setattr__(
            self,
            "canonical_command_json",
            _normalize_safe_json_text(self.canonical_command_json),
        )
        object.__setattr__(
            self,
            "received_at",
            require_datetime(self.received_at, "received_at"),
        )
        object.__setattr__(
            self,
            "record_fingerprint",
            _fingerprint("pcm", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "record_fingerprint": self.record_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "aggregate_id": self.aggregate_id,
            "approval_fingerprint": self.approval_fingerprint,
            "canonical_command_json": self.canonical_command_json,
            "canonical_payload_fingerprint": self.canonical_payload_fingerprint,
            "command_id": self.command_id,
            "correlation_id": self.correlation_id,
            "expected_execution_revision": self.expected_execution_revision,
            "idempotency_key": self.idempotency_key,
            "mode": self.mode,
            "operation": self.operation,
            "policy_fingerprint": self.policy_fingerprint,
            "processing_outcome": self.processing_outcome,
            "received_at": self.received_at,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ExecutionIdempotencyRecord:
    """Durable logical-operation reservation contract."""

    idempotency_key: PaperExecutionIdempotencyKey
    logical_operation_fingerprint: str
    command_id: PaperExecutionCommandId
    aggregate_id: PaperExecutionAggregateId
    reservation_status: ExecutionIdempotencyReservationStatus
    created_at: datetime
    schema_version: int
    original_result_fingerprint: str | None = None
    resolved_at: datetime | None = None
    conflict: bool = False
    mode: PaperExecutionMode = PaperExecutionMode.PAPER
    record_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_mode(self.mode)
        _require_schema_version(self.schema_version)
        if not isinstance(
            self.reservation_status,
            ExecutionIdempotencyReservationStatus,
        ):
            raise ExecutionPersistenceInvariantError(
                "INVALID_RESERVATION_STATUS",
                "Idempotency reservation status is invalid.",
            )
        if not isinstance(self.conflict, bool):
            raise ExecutionPersistenceInvariantError(
                "INVALID_CONFLICT_FLAG",
                "Conflict flag must be boolean.",
            )
        object.__setattr__(
            self,
            "logical_operation_fingerprint",
            validate_fingerprint(self.logical_operation_fingerprint, "plo"),
        )
        _normalize_optional_alias(self, "original_result_fingerprint")
        object.__setattr__(
            self,
            "created_at",
            require_datetime(self.created_at, "created_at"),
        )
        if self.resolved_at is not None:
            object.__setattr__(
                self,
                "resolved_at",
                require_datetime(self.resolved_at, "resolved_at"),
            )
            if self.resolved_at < self.created_at:
                raise ExecutionPersistenceInvariantError(
                    "RESOLVED_BEFORE_CREATED",
                    "Resolved timestamp cannot precede created timestamp.",
                )
        object.__setattr__(
            self,
            "record_fingerprint",
            _fingerprint("pir", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "record_fingerprint": self.record_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "aggregate_id": self.aggregate_id,
            "command_id": self.command_id,
            "conflict": self.conflict,
            "created_at": self.created_at,
            "idempotency_key": self.idempotency_key,
            "logical_operation_fingerprint": self.logical_operation_fingerprint,
            "mode": self.mode,
            "original_result_fingerprint": self.original_result_fingerprint,
            "reservation_status": self.reservation_status,
            "resolved_at": self.resolved_at,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ExecutionTransitionRecord:
    """Append-only accepted lifecycle transition record."""

    transition_record_id: str
    aggregate_id: PaperExecutionAggregateId
    transition_id: str
    source_state: PaperExecutionLifecycleState
    destination_state: PaperExecutionLifecycleState
    previous_revision: PaperExecutionRevision
    next_revision: PaperExecutionRevision
    lifecycle_input_kind: PaperExecutionLifecycleInputType
    input_identity: str
    command_id: PaperExecutionCommandId
    correlation_id: PaperExecutionCorrelationId
    idempotency_key: PaperExecutionIdempotencyKey
    replay_indicator: ExecutionReplayKind
    side_effect_intent_kinds: tuple[PaperExecutionLifecycleSideEffectIntentKind, ...]
    evidence_intent_kinds: tuple[PaperExecutionLifecycleEvidenceIntentKind, ...]
    safe_reason_code: str
    recorded_at: datetime
    schema_version: int
    broker_observation_identity: str | None = None
    receipt_fingerprint: str | None = None
    failure_fingerprint: str | None = None
    mode: PaperExecutionMode = PaperExecutionMode.PAPER
    record_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_mode(self.mode)
        _require_schema_version(self.schema_version)
        if int(self.next_revision) != int(self.previous_revision) + 1:
            raise ExecutionPersistenceInvariantError(
                "NON_SEQUENTIAL_TRANSITION_REVISION",
                "Accepted transition revisions must advance by exactly one.",
            )
        if self.replay_indicator is not ExecutionReplayKind.NONE:
            raise ExecutionPersistenceInvariantError(
                "REPLAY_TRANSITION_NOT_ACCEPTED",
                "Accepted transition records cannot represent replay.",
            )
        object.__setattr__(
            self,
            "transition_record_id",
            normalize_alias(self.transition_record_id, "transition_record_id"),
        )
        object.__setattr__(
            self,
            "transition_id",
            normalize_alias(self.transition_id, "transition_id"),
        )
        object.__setattr__(
            self,
            "input_identity",
            normalize_alias(self.input_identity, "input_identity"),
        )
        _normalize_optional_alias(self, "broker_observation_identity")
        _normalize_optional_fingerprint(self, "receipt_fingerprint", "prc")
        _normalize_optional_fingerprint(self, "failure_fingerprint", "pfl")
        object.__setattr__(
            self,
            "safe_reason_code",
            _safe_text(
                normalize_code(self.safe_reason_code, "safe_reason_code"),
                "safe_reason_code",
            ),
        )
        _require_enum_tuple(
            self.side_effect_intent_kinds,
            PaperExecutionLifecycleSideEffectIntentKind,
            "side_effect_intent_kinds",
        )
        _require_enum_tuple(
            self.evidence_intent_kinds,
            PaperExecutionLifecycleEvidenceIntentKind,
            "evidence_intent_kinds",
        )
        object.__setattr__(
            self,
            "recorded_at",
            require_datetime(self.recorded_at, "recorded_at"),
        )
        object.__setattr__(
            self,
            "record_fingerprint",
            _fingerprint("ptr", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "record_fingerprint": self.record_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "aggregate_id": self.aggregate_id,
            "broker_observation_identity": self.broker_observation_identity,
            "command_id": self.command_id,
            "correlation_id": self.correlation_id,
            "destination_state": self.destination_state,
            "evidence_intent_kinds": self.evidence_intent_kinds,
            "failure_fingerprint": self.failure_fingerprint,
            "idempotency_key": self.idempotency_key,
            "input_identity": self.input_identity,
            "lifecycle_input_kind": self.lifecycle_input_kind,
            "mode": self.mode,
            "next_revision": self.next_revision,
            "previous_revision": self.previous_revision,
            "receipt_fingerprint": self.receipt_fingerprint,
            "recorded_at": self.recorded_at,
            "replay_indicator": self.replay_indicator,
            "safe_reason_code": self.safe_reason_code,
            "schema_version": self.schema_version,
            "side_effect_intent_kinds": self.side_effect_intent_kinds,
            "source_state": self.source_state,
            "transition_id": self.transition_id,
            "transition_record_id": self.transition_record_id,
        }


@dataclass(frozen=True, slots=True)
class ExecutionBrokerReferenceRecord:
    """Normalized Paper broker reference contract."""

    broker_reference: PaperBrokerOrderReference
    aggregate_id: PaperExecutionAggregateId
    command_id: PaperExecutionCommandId
    adapter_identity: str
    reference_status: ExecutionBrokerReferenceStatus
    first_seen_at: datetime
    last_seen_at: datetime
    active: bool
    schema_version: int
    replaced_by_reference: PaperBrokerOrderReference | None = None
    mode: PaperExecutionMode = PaperExecutionMode.PAPER
    record_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_mode(self.mode)
        _require_schema_version(self.schema_version)
        if not isinstance(self.reference_status, ExecutionBrokerReferenceStatus):
            raise ExecutionPersistenceInvariantError(
                "INVALID_REFERENCE_STATUS",
                "Broker reference status is invalid.",
            )
        if not isinstance(self.active, bool):
            raise ExecutionPersistenceInvariantError(
                "INVALID_ACTIVE_FLAG",
                "Active flag must be boolean.",
            )
        object.__setattr__(
            self,
            "adapter_identity",
            normalize_alias(self.adapter_identity, "adapter_identity"),
        )
        object.__setattr__(
            self,
            "first_seen_at",
            require_datetime(self.first_seen_at, "first_seen_at"),
        )
        object.__setattr__(
            self,
            "last_seen_at",
            require_datetime(self.last_seen_at, "last_seen_at"),
        )
        if self.last_seen_at < self.first_seen_at:
            raise ExecutionPersistenceInvariantError(
                "LAST_SEEN_BEFORE_FIRST_SEEN",
                "Last-seen timestamp cannot precede first-seen timestamp.",
            )
        object.__setattr__(
            self,
            "record_fingerprint",
            _fingerprint("pbf", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "record_fingerprint": self.record_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "active": self.active,
            "adapter_identity": self.adapter_identity,
            "aggregate_id": self.aggregate_id,
            "broker_reference": self.broker_reference,
            "command_id": self.command_id,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "mode": self.mode,
            "reference_status": self.reference_status,
            "replaced_by_reference": self.replaced_by_reference,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ExecutionReceiptRecord:
    """Durable receipt keyed by its embedded receipt fingerprint.

    The wrapper fingerprint distinguishes exact replay from conflicting wrapper
    content for an already-recorded embedded receipt identity.
    """

    receipt: PaperExecutionReceipt
    recorded_at: datetime
    schema_version: int
    record_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.receipt, PaperExecutionReceipt):
            raise ExecutionPersistenceInvariantError(
                "INVALID_RECEIPT",
                "Receipt record requires a PaperExecutionReceipt.",
            )
        _require_schema_version(self.schema_version)
        object.__setattr__(
            self,
            "recorded_at",
            require_datetime(self.recorded_at, "recorded_at"),
        )
        object.__setattr__(
            self,
            "record_fingerprint",
            _fingerprint("prr", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "record_fingerprint": self.record_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "receipt": self.receipt,
            "recorded_at": self.recorded_at,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ExecutionFailureRecord:
    """Durable failure keyed by its embedded failure fingerprint.

    The wrapper fingerprint distinguishes exact replay from conflicting wrapper
    content for an already-recorded embedded failure identity.
    """

    failure: PaperExecutionFailure
    recorded_at: datetime
    schema_version: int
    record_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.failure, PaperExecutionFailure):
            raise ExecutionPersistenceInvariantError(
                "INVALID_FAILURE",
                "Failure record requires a PaperExecutionFailure.",
            )
        _require_schema_version(self.schema_version)
        object.__setattr__(
            self,
            "recorded_at",
            require_datetime(self.recorded_at, "recorded_at"),
        )
        object.__setattr__(
            self,
            "record_fingerprint",
            _fingerprint("pfr", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "record_fingerprint": self.record_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "failure": self.failure,
            "recorded_at": self.recorded_at,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ExecutionApprovalRecord:
    """Durable approval-reference contract."""

    approval_fingerprint: str
    bound_fingerprint: str
    approval_kind: str
    approver_safe_reference: str
    approved_at: datetime
    recorded_at: datetime
    schema_version: int
    expires_at: datetime | None = None
    revocation_reference: str | None = None
    mode: PaperExecutionMode = PaperExecutionMode.PAPER
    record_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_mode(self.mode)
        _require_schema_version(self.schema_version)
        object.__setattr__(
            self,
            "approval_fingerprint",
            validate_fingerprint(self.approval_fingerprint, "pap"),
        )
        object.__setattr__(
            self,
            "bound_fingerprint",
            normalize_alias(self.bound_fingerprint, "bound_fingerprint"),
        )
        object.__setattr__(
            self,
            "approval_kind",
            normalize_code(self.approval_kind, "approval_kind"),
        )
        object.__setattr__(
            self,
            "approver_safe_reference",
            normalize_alias(
                self.approver_safe_reference,
                "approver_safe_reference",
            ),
        )
        _normalize_optional_alias(self, "revocation_reference")
        object.__setattr__(
            self,
            "approved_at",
            require_datetime(self.approved_at, "approved_at"),
        )
        object.__setattr__(
            self,
            "recorded_at",
            require_datetime(self.recorded_at, "recorded_at"),
        )
        if self.expires_at is not None:
            object.__setattr__(
                self,
                "expires_at",
                require_datetime(self.expires_at, "expires_at"),
            )
            if self.expires_at < self.approved_at:
                raise ExecutionPersistenceInvariantError(
                    "APPROVAL_EXPIRY_BEFORE_APPROVAL",
                    "Approval expiry cannot precede approval time.",
                )
        object.__setattr__(
            self,
            "record_fingerprint",
            _fingerprint("pav", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "record_fingerprint": self.record_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "approval_fingerprint": self.approval_fingerprint,
            "approval_kind": self.approval_kind,
            "approved_at": self.approved_at,
            "approver_safe_reference": self.approver_safe_reference,
            "bound_fingerprint": self.bound_fingerprint,
            "expires_at": self.expires_at,
            "mode": self.mode,
            "recorded_at": self.recorded_at,
            "revocation_reference": self.revocation_reference,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class ExecutionReconciliationRecord:
    """Append-only reconciliation result contract."""

    reconciliation_id: str
    aggregate_id: PaperExecutionAggregateId
    starting_local_revision: PaperExecutionRevision
    starting_lifecycle_state: PaperExecutionLifecycleState
    broker_observation_references: tuple[str, ...]
    result_classification: ExecutionReconciliationResultClassification
    operator_action_required: bool
    unresolved: bool
    safe_reason_code: str
    recorded_at: datetime
    schema_version: int
    resulting_transition_id: str | None = None
    resulting_revision: PaperExecutionRevision | None = None
    mode: PaperExecutionMode = PaperExecutionMode.PAPER
    record_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_mode(self.mode)
        _require_schema_version(self.schema_version)
        _require_bool_fields(self, ("operator_action_required", "unresolved"))
        object.__setattr__(
            self,
            "reconciliation_id",
            normalize_alias(self.reconciliation_id, "reconciliation_id"),
        )
        object.__setattr__(
            self,
            "broker_observation_references",
            _normalize_alias_tuple(
                self.broker_observation_references,
                "broker_observation_references",
            ),
        )
        if not isinstance(
            self.result_classification,
            ExecutionReconciliationResultClassification,
        ):
            raise ExecutionPersistenceInvariantError(
                "INVALID_RECONCILIATION_CLASSIFICATION",
                "Reconciliation classification is invalid.",
            )
        object.__setattr__(
            self,
            "safe_reason_code",
            normalize_code(self.safe_reason_code, "safe_reason_code"),
        )
        _normalize_optional_alias(self, "resulting_transition_id")
        object.__setattr__(
            self,
            "recorded_at",
            require_datetime(self.recorded_at, "recorded_at"),
        )
        object.__setattr__(
            self,
            "record_fingerprint",
            _fingerprint("prn", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "record_fingerprint": self.record_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "aggregate_id": self.aggregate_id,
            "broker_observation_references": self.broker_observation_references,
            "mode": self.mode,
            "operator_action_required": self.operator_action_required,
            "reconciliation_id": self.reconciliation_id,
            "recorded_at": self.recorded_at,
            "result_classification": self.result_classification,
            "resulting_revision": self.resulting_revision,
            "resulting_transition_id": self.resulting_transition_id,
            "safe_reason_code": self.safe_reason_code,
            "schema_version": self.schema_version,
            "starting_lifecycle_state": self.starting_lifecycle_state,
            "starting_local_revision": self.starting_local_revision,
            "unresolved": self.unresolved,
        }


@dataclass(frozen=True, slots=True)
class ExecutionPersistenceConflict:
    """Expected persistence conflict represented as immutable data."""

    kind: ExecutionPersistenceConflictKind
    severity: ExecutionPersistenceConflictSeverity
    code: str
    safe_message: str
    schema_version: int
    aggregate_id: PaperExecutionAggregateId | None = None
    command_id: PaperExecutionCommandId | None = None
    idempotency_key: PaperExecutionIdempotencyKey | None = None
    expected_revision: PaperExecutionRevision | None = None
    actual_revision: PaperExecutionRevision | None = None
    conflict_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        if not isinstance(self.kind, ExecutionPersistenceConflictKind):
            raise ExecutionPersistenceInvariantError(
                "INVALID_CONFLICT_KIND",
                "Conflict kind is invalid.",
            )
        if not isinstance(self.severity, ExecutionPersistenceConflictSeverity):
            raise ExecutionPersistenceInvariantError(
                "INVALID_CONFLICT_SEVERITY",
                "Conflict severity is invalid.",
            )
        object.__setattr__(self, "code", normalize_code(self.code, "code"))
        object.__setattr__(
            self,
            "safe_message",
            _safe_text(self.safe_message, "safe_message"),
        )
        object.__setattr__(
            self,
            "conflict_fingerprint",
            _fingerprint("pco", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "conflict_fingerprint": self.conflict_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "actual_revision": self.actual_revision,
            "aggregate_id": self.aggregate_id,
            "code": self.code,
            "command_id": self.command_id,
            "expected_revision": self.expected_revision,
            "idempotency_key": self.idempotency_key,
            "kind": self.kind,
            "safe_message": self.safe_message,
            "schema_version": self.schema_version,
            "severity": self.severity,
        }


@dataclass(frozen=True, slots=True)
class RecordLoadResult:
    """Result of loading one record reference."""

    status: ExecutionPersistenceResultStatus
    schema_version: int
    record_fingerprint: str | None = None
    conflict: ExecutionPersistenceConflict | None = None
    result_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _validate_result(self.status, self.schema_version, self.conflict)
        _normalize_optional_alias(self, "record_fingerprint")
        object.__setattr__(
            self,
            "result_fingerprint",
            _fingerprint("plr", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "result_fingerprint": self.result_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "conflict": self.conflict,
            "record_fingerprint": self.record_fingerprint,
            "schema_version": self.schema_version,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class AggregateSaveResult:
    """Revision-aware aggregate save result."""

    status: ExecutionPersistenceResultStatus
    aggregate_id: PaperExecutionAggregateId
    expected_revision: PaperExecutionRevision
    current_revision: PaperExecutionRevision | None
    schema_version: int
    aggregate_fingerprint: str | None = None
    conflict: ExecutionPersistenceConflict | None = None
    result_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _validate_result(self.status, self.schema_version, self.conflict)
        _normalize_optional_alias(self, "aggregate_fingerprint")
        object.__setattr__(
            self,
            "result_fingerprint",
            _fingerprint("pas", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "result_fingerprint": self.result_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "aggregate_fingerprint": self.aggregate_fingerprint,
            "aggregate_id": self.aggregate_id,
            "conflict": self.conflict,
            "current_revision": self.current_revision,
            "expected_revision": self.expected_revision,
            "schema_version": self.schema_version,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class CommandRegistrationResult:
    """Command registration, replay, or conflict result."""

    status: ExecutionPersistenceResultStatus
    command_id: PaperExecutionCommandId
    schema_version: int
    command_fingerprint: str | None = None
    original_command_id: PaperExecutionCommandId | None = None
    original_result_fingerprint: str | None = None
    conflict: ExecutionPersistenceConflict | None = None
    result_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _validate_result(self.status, self.schema_version, self.conflict)
        _normalize_optional_alias(self, "command_fingerprint")
        _normalize_optional_alias(self, "original_result_fingerprint")
        object.__setattr__(
            self,
            "result_fingerprint",
            _fingerprint("pcr", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "result_fingerprint": self.result_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "command_fingerprint": self.command_fingerprint,
            "command_id": self.command_id,
            "conflict": self.conflict,
            "original_command_id": self.original_command_id,
            "original_result_fingerprint": self.original_result_fingerprint,
            "schema_version": self.schema_version,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class IdempotencyReservationResult:
    """Idempotency reservation, replay, or conflict result."""

    status: ExecutionPersistenceResultStatus
    idempotency_key: PaperExecutionIdempotencyKey
    schema_version: int
    reservation_fingerprint: str | None = None
    original_command_id: PaperExecutionCommandId | None = None
    original_result_fingerprint: str | None = None
    conflict: ExecutionPersistenceConflict | None = None
    result_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _validate_result(self.status, self.schema_version, self.conflict)
        _normalize_optional_alias(self, "reservation_fingerprint")
        _normalize_optional_alias(self, "original_result_fingerprint")
        object.__setattr__(
            self,
            "result_fingerprint",
            _fingerprint("prs", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "result_fingerprint": self.result_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "conflict": self.conflict,
            "idempotency_key": self.idempotency_key,
            "original_command_id": self.original_command_id,
            "original_result_fingerprint": self.original_result_fingerprint,
            "reservation_fingerprint": self.reservation_fingerprint,
            "schema_version": self.schema_version,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class TransitionAppendResult:
    """Append-only transition journal result."""

    status: ExecutionPersistenceResultStatus
    aggregate_id: PaperExecutionAggregateId
    previous_revision: PaperExecutionRevision
    next_revision: PaperExecutionRevision | None
    schema_version: int
    transition_fingerprint: str | None = None
    conflict: ExecutionPersistenceConflict | None = None
    result_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _validate_result(self.status, self.schema_version, self.conflict)
        _normalize_optional_alias(self, "transition_fingerprint")
        object.__setattr__(
            self,
            "result_fingerprint",
            _fingerprint("pta", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "result_fingerprint": self.result_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "aggregate_id": self.aggregate_id,
            "conflict": self.conflict,
            "next_revision": self.next_revision,
            "previous_revision": self.previous_revision,
            "schema_version": self.schema_version,
            "status": self.status,
            "transition_fingerprint": self.transition_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class ReplayLookupResult:
    """Exact or logical replay lookup result."""

    status: ExecutionPersistenceResultStatus
    replay_kind: ExecutionReplayKind
    schema_version: int
    original_command_id: PaperExecutionCommandId | None = None
    original_result_fingerprint: str | None = None
    conflict: ExecutionPersistenceConflict | None = None
    result_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _validate_result(self.status, self.schema_version, self.conflict)
        if not isinstance(self.replay_kind, ExecutionReplayKind):
            raise ExecutionPersistenceInvariantError(
                "INVALID_REPLAY_KIND",
                "Replay kind is invalid.",
            )
        _normalize_optional_alias(self, "original_result_fingerprint")
        object.__setattr__(
            self,
            "result_fingerprint",
            _fingerprint("prl", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "result_fingerprint": self.result_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "conflict": self.conflict,
            "original_command_id": self.original_command_id,
            "original_result_fingerprint": self.original_result_fingerprint,
            "replay_kind": self.replay_kind,
            "schema_version": self.schema_version,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class ExecutionRestartDiscoveryQuery:
    """Pure query contract for aggregate-identity-ordered restart discovery.

    Cursor encodings are adapter-private and bind every filter except ``cursor``
    and ``limit``. Invalid, unknown, or cross-filter cursors restart at page one.
    """

    lifecycle_states: tuple[PaperExecutionLifecycleState, ...]
    schema_version: int
    minimum_updated_at: datetime | None = None
    maximum_updated_at: datetime | None = None
    limit: int | None = None
    cursor: str | None = None
    include_outcome_unknown: bool = True
    include_reconciliation_required: bool = True
    mode: PaperExecutionMode = PaperExecutionMode.PAPER
    query_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_mode(self.mode)
        _require_schema_version(self.schema_version)
        _require_bool_fields(
            self,
            ("include_outcome_unknown", "include_reconciliation_required"),
        )
        _require_enum_tuple(
            self.lifecycle_states,
            PaperExecutionLifecycleState,
            "lifecycle_states",
        )
        if not self.lifecycle_states:
            raise ExecutionPersistenceInvariantError(
                "EMPTY_RESTART_STATE_FILTER",
                "Restart discovery requires at least one lifecycle state.",
            )
        if self.minimum_updated_at is not None:
            object.__setattr__(
                self,
                "minimum_updated_at",
                require_datetime(self.minimum_updated_at, "minimum_updated_at"),
            )
        if self.maximum_updated_at is not None:
            object.__setattr__(
                self,
                "maximum_updated_at",
                require_datetime(self.maximum_updated_at, "maximum_updated_at"),
            )
        if (
            self.minimum_updated_at is not None
            and self.maximum_updated_at is not None
            and self.maximum_updated_at < self.minimum_updated_at
        ):
            raise ExecutionPersistenceInvariantError(
                "INVALID_RESTART_DISCOVERY_WINDOW",
                "Maximum updated timestamp cannot precede minimum timestamp.",
            )
        if self.limit is not None and self.limit <= 0:
            raise ExecutionPersistenceInvariantError(
                "INVALID_RESTART_DISCOVERY_LIMIT",
                "Restart discovery limit must be positive.",
            )
        _normalize_optional_alias(self, "cursor")
        object.__setattr__(
            self,
            "query_fingerprint",
            _fingerprint("pdq", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "query_fingerprint": self.query_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "cursor": self.cursor,
            "include_outcome_unknown": self.include_outcome_unknown,
            "include_reconciliation_required": self.include_reconciliation_required,
            "lifecycle_states": self.lifecycle_states,
            "limit": self.limit,
            "maximum_updated_at": self.maximum_updated_at,
            "minimum_updated_at": self.minimum_updated_at,
            "mode": self.mode,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class RestartDiscoveryResult:
    """Restart discovery page of aggregate records."""

    aggregates: tuple[ExecutionAggregateRecord, ...]
    complete: bool
    schema_version: int
    next_cursor: str | None = None
    query_fingerprint: str | None = None
    result_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version)
        if not isinstance(self.aggregates, tuple) or not all(
            isinstance(record, ExecutionAggregateRecord) for record in self.aggregates
        ):
            raise ExecutionPersistenceInvariantError(
                "INVALID_RESTART_DISCOVERY_RECORDS",
                "Restart discovery records must be an immutable tuple.",
            )
        if not isinstance(self.complete, bool):
            raise ExecutionPersistenceInvariantError(
                "INVALID_COMPLETE_FLAG",
                "Complete flag must be boolean.",
            )
        _normalize_optional_alias(self, "next_cursor")
        _normalize_optional_alias(self, "query_fingerprint")
        object.__setattr__(
            self,
            "result_fingerprint",
            _fingerprint("pdr", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "result_fingerprint": self.result_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "aggregates": self.aggregates,
            "complete": self.complete,
            "next_cursor": self.next_cursor,
            "query_fingerprint": self.query_fingerprint,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class UnitOfWorkCommitResult:
    """Explicit unit-of-work commit result contract."""

    status: ExecutionPersistenceResultStatus
    committed: bool
    schema_version: int
    conflict: ExecutionPersistenceConflict | None = None
    result_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        _validate_result(self.status, self.schema_version, self.conflict)
        if not isinstance(self.committed, bool):
            raise ExecutionPersistenceInvariantError(
                "INVALID_COMMITTED_FLAG",
                "Committed flag must be boolean.",
            )
        object.__setattr__(
            self,
            "result_fingerprint",
            _fingerprint("puw", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "result_fingerprint": self.result_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "committed": self.committed,
            "conflict": self.conflict,
            "schema_version": self.schema_version,
            "status": self.status,
        }


def canonical_payload_text(value: Any) -> str:
    """Return canonical command text for storage-neutral command records."""

    return canonical_json_text(canonicalize(value))


def _fingerprint(prefix: str, value: object) -> str:
    return fingerprint_payload(prefix, value)


def _require_mode(mode: PaperExecutionMode) -> None:
    if mode is not PaperExecutionMode.PAPER:
        raise ExecutionPersistenceInvariantError(
            "PAPER_MODE_REQUIRED",
            "Execution persistence contracts require Paper mode.",
        )


def _require_schema_version(schema_version: int) -> None:
    if isinstance(schema_version, bool) or not isinstance(schema_version, int):
        raise ExecutionPersistenceInvariantError(
            "INVALID_SCHEMA_VERSION",
            "Schema version must be a positive integer.",
        )
    if schema_version <= 0:
        raise ExecutionPersistenceInvariantError(
            "INVALID_SCHEMA_VERSION",
            "Schema version must be a positive integer.",
        )


def _require_bool_fields(instance: object, names: tuple[str, ...]) -> None:
    for name in names:
        if not isinstance(getattr(instance, name), bool):
            raise ExecutionPersistenceInvariantError(
                "INVALID_BOOLEAN_FIELD",
                f"{name} must be boolean.",
            )


def _require_enum_tuple(
    values: tuple[object, ...],
    expected_type: type[object],
    field_name: str,
) -> None:
    if not isinstance(values, tuple) or not all(
        isinstance(value, expected_type) for value in values
    ):
        raise ExecutionPersistenceInvariantError(
            "INVALID_ENUM_TUPLE",
            f"{field_name} must be an immutable tuple of expected enum values.",
        )


def _normalize_alias_tuple(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise ExecutionPersistenceInvariantError(
            "INVALID_ALIAS_TUPLE",
            f"{field_name} must be an immutable tuple.",
        )
    return tuple(normalize_alias(value, field_name) for value in values)


def _normalize_optional_alias(instance: object, field_name: str) -> None:
    value = getattr(instance, field_name)
    if value is not None:
        object.__setattr__(
            instance,
            field_name,
            normalize_alias(value, field_name),
        )


def _normalize_optional_fingerprint(
    instance: object,
    field_name: str,
    prefix: str,
) -> None:
    value = getattr(instance, field_name)
    if value is not None:
        object.__setattr__(
            instance,
            field_name,
            validate_fingerprint(value, prefix),
        )


def _normalize_safe_json_text(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionPersistenceInvariantError(
            "INVALID_CANONICAL_COMMAND",
            "Canonical command representation must be non-empty text.",
        )
    return _safe_text(value, "canonical_command_json")


def _safe_text(value: str, field_name: str) -> str:
    try:
        return validate_no_sensitive_text(value, field_name)
    except PaperExecutionContractError as error:
        raise ExecutionPersistenceInvariantError(
            error.reason_code,
            error.safe_message,
        ) from error


def _validate_result(
    status: ExecutionPersistenceResultStatus,
    schema_version: int,
    conflict: ExecutionPersistenceConflict | None,
) -> None:
    if not isinstance(status, ExecutionPersistenceResultStatus):
        raise ExecutionPersistenceInvariantError(
            "INVALID_RESULT_STATUS",
            "Persistence result status is invalid.",
        )
    _require_schema_version(schema_version)
    if conflict is not None and not isinstance(conflict, ExecutionPersistenceConflict):
        raise ExecutionPersistenceInvariantError(
            "INVALID_CONFLICT",
            "Conflict must be an ExecutionPersistenceConflict.",
        )
