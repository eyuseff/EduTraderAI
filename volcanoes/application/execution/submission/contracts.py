"""Immutable contracts for durably claimed, broker-neutral Paper submission."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
import json

from volcanoes.application.execution._canonical import canonical_json_text
from volcanoes.application.execution.contracts._validation import (
    normalize_alias,
    normalize_code,
    normalize_symbol,
    require_positive_decimal,
    validate_no_sensitive_text,
)
from volcanoes.application.execution.errors import PaperExecutionInvariantError
from volcanoes.application.execution.fingerprints import (
    command_payload_fingerprint,
    fingerprint_payload,
)
from volcanoes.application.execution.persistence import ExecutionDispatchClaimAttempt
from volcanoes.application.execution.persistence.contracts import ExecutionDispatchClaim
from volcanoes.application.execution.identities import (
    PaperBrokerOrderReference,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionIdempotencyKey,
)
from volcanoes.application.execution.enums import (
    PaperExecutionFailureKind,
    PaperExecutionOrderType,
    PaperExecutionSide,
    PaperExecutionTimeInForce,
)


class DispatchFailurePhase(StrEnum):
    PRE_DISPATCH = "PRE_DISPATCH"
    POSSIBLE_POST_DISPATCH = "POSSIBLE_POST_DISPATCH"


class ControlledSubmissionStatus(StrEnum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    BROKER_REJECTED = "BROKER_REJECTED"
    PRE_DISPATCH_FAILURE = "PRE_DISPATCH_FAILURE"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
    EXACT_REPLAY = "EXACT_REPLAY"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class ControlledSubmissionRequest:
    """Stable lookup identity with no payload or safety authority."""

    submission_id: str
    command_id: PaperExecutionCommandId
    idempotency_key: PaperExecutionIdempotencyKey
    request_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "submission_id", _safe_alias(self.submission_id, "submission_id")
        )
        if not isinstance(self.command_id, PaperExecutionCommandId):
            raise PaperExecutionInvariantError(
                "INVALID_COMMAND_ID", "Command identity must be committed."
            )
        if not isinstance(self.idempotency_key, PaperExecutionIdempotencyKey):
            raise PaperExecutionInvariantError(
                "INVALID_IDEMPOTENCY_KEY", "Idempotency identity must be committed."
            )
        object.__setattr__(
            self, "request_fingerprint", fingerprint_payload("psq", self._primitive())
        )

    def _primitive(self) -> dict[str, object]:
        return {
            "command_id": self.command_id,
            "idempotency_key": self.idempotency_key,
            "submission_id": self.submission_id,
        }

    def to_attempt(self) -> ExecutionDispatchClaimAttempt:
        return ExecutionDispatchClaimAttempt(
            self.submission_id, self.command_id, self.idempotency_key
        )


def deterministic_client_order_id(claim: ExecutionDispatchClaim) -> str:
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
class ControlledPaperOrder:
    submission_id: str
    command_id: str
    aggregate_id: str
    correlation_id: str
    idempotency_key: str
    execution_revision: int
    approval_fingerprint: str
    policy_fingerprint: str
    canonical_payload_fingerprint: str
    client_order_id: str
    symbol: str
    side: str
    quantity: Decimal
    order_type: str
    time_in_force: str
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    asset_class: str = "equity"
    currency: str = "USD"
    venue: str | None = None
    mode: str = "PAPER"
    order_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "submission_id",
            "command_id",
            "aggregate_id",
            "correlation_id",
            "idempotency_key",
            "approval_fingerprint",
            "policy_fingerprint",
            "canonical_payload_fingerprint",
            "client_order_id",
        ):
            object.__setattr__(self, name, _safe_alias(getattr(self, name), name))
        if len(self.client_order_id) != 48 or not self.client_order_id.startswith(
            "paper-"
        ):
            raise PaperExecutionInvariantError(
                "INVALID_CLIENT_ORDER_ID",
                "Client order identity must use the 48-character paper scheme.",
            )
        object.__setattr__(self, "symbol", normalize_symbol(self.symbol))
        for name in ("side", "order_type", "time_in_force", "mode"):
            object.__setattr__(self, name, _safe_code(getattr(self, name), name))
        if self.side not in {item.value for item in PaperExecutionSide}:
            raise PaperExecutionInvariantError("INVALID_SIDE", "Order side is invalid.")
        if self.order_type not in {item.value for item in PaperExecutionOrderType}:
            raise PaperExecutionInvariantError(
                "INVALID_ORDER_TYPE", "Order type is invalid."
            )
        if self.time_in_force not in {item.value for item in PaperExecutionTimeInForce}:
            raise PaperExecutionInvariantError(
                "INVALID_TIME_IN_FORCE", "Time in force is invalid."
            )
        if self.mode != "PAPER":
            raise PaperExecutionInvariantError(
                "PAPER_MODE_REQUIRED", "Controlled submission is Paper-only."
            )
        if self.asset_class != "equity":
            raise PaperExecutionInvariantError(
                "UNSUPPORTED_ASSET_CLASS",
                "Controlled submission supports equity instruments only.",
            )
        if self.currency != "USD":
            raise PaperExecutionInvariantError(
                "UNSUPPORTED_CURRENCY",
                "Controlled submission supports USD instruments only.",
            )
        if self.venue is not None:
            raise PaperExecutionInvariantError(
                "UNSUPPORTED_VENUE",
                "Controlled submission does not accept caller-selected venues.",
            )
        object.__setattr__(
            self, "quantity", require_positive_decimal(self.quantity, "quantity")
        )
        for name in ("limit_price", "stop_price"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, require_positive_decimal(value, name))
        if self.order_type == "MARKET" and (
            self.limit_price is not None or self.stop_price is not None
        ):
            raise PaperExecutionInvariantError(
                "INVALID_MARKET_PRICE_FIELDS", "Market prices are forbidden."
            )
        if self.order_type == "LIMIT" and (
            self.limit_price is None or self.stop_price is not None
        ):
            raise PaperExecutionInvariantError(
                "INVALID_LIMIT_PRICE_FIELDS", "Limit price shape is invalid."
            )
        if self.order_type == "STOP" and (
            self.stop_price is None or self.limit_price is not None
        ):
            raise PaperExecutionInvariantError(
                "INVALID_STOP_PRICE_FIELDS", "Stop price shape is invalid."
            )
        if self.order_type == "STOP_LIMIT" and (
            self.stop_price is None or self.limit_price is None
        ):
            raise PaperExecutionInvariantError(
                "INVALID_STOP_LIMIT_PRICE_FIELDS", "Stop-limit prices are required."
            )
        object.__setattr__(
            self, "order_fingerprint", fingerprint_payload("por", self.to_primitive())
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            name: getattr(self, name)
            for name in (
                "aggregate_id",
                "approval_fingerprint",
                "asset_class",
                "canonical_payload_fingerprint",
                "client_order_id",
                "command_id",
                "correlation_id",
                "currency",
                "execution_revision",
                "idempotency_key",
                "limit_price",
                "mode",
                "order_type",
                "policy_fingerprint",
                "quantity",
                "side",
                "stop_price",
                "submission_id",
                "symbol",
                "time_in_force",
                "venue",
            )
        }

    @classmethod
    def from_claim(cls, claim: ExecutionDispatchClaim) -> "ControlledPaperOrder":
        if not isinstance(claim, ExecutionDispatchClaim):
            raise PaperExecutionInvariantError(
                "PUBLIC_CLAIM_REQUIRED",
                "Order construction requires a non-secret public claim.",
            )

        def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in items:
                if key in result:
                    raise PaperExecutionInvariantError(
                        "DUPLICATE_ORDER_FIELD",
                        "Durable command contains a duplicate key.",
                    )
                result[key] = value
            return result

        try:
            data = json.loads(claim.canonical_order_json, object_pairs_hook=pairs)
        except (TypeError, ValueError) as exc:
            raise PaperExecutionInvariantError(
                "INVALID_CANONICAL_ORDER", "Durable command JSON is invalid."
            ) from exc
        expected_client_order_id = deterministic_client_order_id(claim)
        if claim.client_order_id != expected_client_order_id:
            raise PaperExecutionInvariantError(
                "CLIENT_ORDER_ID_MISMATCH",
                "Durable client-order identity does not match the claim.",
            )
        required = {
            "asset_class",
            "currency",
            "mode",
            "operation",
            "symbol",
            "side",
            "quantity",
            "order_type",
            "time_in_force",
        }
        allowed = required | {
            "limit_price",
            "stop_price",
            "venue",
        }
        if (
            not isinstance(data, dict)
            or set(data) - allowed
            or not required.issubset(data)
            or data["operation"] != "SUBMIT"
        ):
            raise PaperExecutionInvariantError(
                "INVALID_CANONICAL_ORDER", "Durable submit command schema is invalid."
            )
        if canonical_json_text(data) != claim.canonical_order_json:
            raise PaperExecutionInvariantError(
                "NONCANONICAL_ORDER", "Durable command JSON is not canonical."
            )
        if command_payload_fingerprint(data) != claim.canonical_payload_fingerprint:
            raise PaperExecutionInvariantError(
                "PAYLOAD_FINGERPRINT_MISMATCH",
                "Durable payload fingerprint does not match command JSON.",
            )
        return cls(
            submission_id=claim.submission_id,
            command_id=str(claim.command_id),
            aggregate_id=str(claim.aggregate_id),
            correlation_id=str(claim.correlation_id),
            idempotency_key=str(claim.idempotency_key),
            execution_revision=int(claim.expected_execution_revision),
            approval_fingerprint=claim.approval_fingerprint,
            policy_fingerprint=claim.policy_fingerprint,
            canonical_payload_fingerprint=claim.canonical_payload_fingerprint,
            client_order_id=expected_client_order_id,
            symbol=data["symbol"],
            side=data["side"],
            quantity=Decimal(str(data["quantity"])),
            order_type=data["order_type"],
            time_in_force=data["time_in_force"],
            limit_price=(
                None
                if data.get("limit_price") is None
                else Decimal(str(data["limit_price"]))
            ),
            stop_price=(
                None
                if data.get("stop_price") is None
                else Decimal(str(data["stop_price"]))
            ),
            asset_class=data["asset_class"],
            currency=data["currency"],
            venue=data.get("venue"),
            mode=data["mode"],
        )


@dataclass(frozen=True, slots=True)
class PaperDispatchObservation:
    submission_id: str
    broker_reference: PaperBrokerOrderReference
    accepted: bool
    message_code: str
    observation_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "submission_id", _safe_alias(self.submission_id, "submission_id")
        )
        if not isinstance(self.broker_reference, PaperBrokerOrderReference):
            raise PaperExecutionInvariantError(
                "INVALID_BROKER_REFERENCE", "Broker reference must be committed."
            )
        if not isinstance(self.accepted, bool):
            raise PaperExecutionInvariantError(
                "INVALID_OBSERVATION", "Accepted must be boolean."
            )
        object.__setattr__(
            self, "message_code", _safe_code(self.message_code, "message_code")
        )
        object.__setattr__(
            self,
            "observation_fingerprint",
            fingerprint_payload(
                "pso",
                {
                    "accepted": self.accepted,
                    "broker_reference": self.broker_reference,
                    "message_code": self.message_code,
                    "submission_id": self.submission_id,
                },
            ),
        )


@dataclass(frozen=True, slots=True)
class PaperDispatchFailure:
    submission_id: str
    phase: DispatchFailurePhase
    reason_code: str
    safe_message: str
    failure_kind: PaperExecutionFailureKind = (
        PaperExecutionFailureKind.INTERNAL_INVARIANT
    )
    failure_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "submission_id", _safe_alias(self.submission_id, "submission_id")
        )
        if not isinstance(self.phase, DispatchFailurePhase):
            raise PaperExecutionInvariantError(
                "INVALID_FAILURE_PHASE", "Failure phase is invalid."
            )
        if not isinstance(self.failure_kind, PaperExecutionFailureKind):
            raise PaperExecutionInvariantError(
                "INVALID_FAILURE_KIND", "Failure kind is invalid."
            )
        object.__setattr__(
            self, "reason_code", _safe_code(self.reason_code, "reason_code")
        )
        object.__setattr__(
            self,
            "safe_message",
            validate_no_sensitive_text(self.safe_message.strip(), "safe_message"),
        )
        object.__setattr__(
            self,
            "failure_fingerprint",
            fingerprint_payload(
                "psf",
                {
                    "phase": self.phase,
                    "failure_kind": self.failure_kind,
                    "reason_code": self.reason_code,
                    "safe_message": self.safe_message,
                    "submission_id": self.submission_id,
                },
            ),
        )


@dataclass(frozen=True, slots=True)
class ControlledSubmissionResult:
    submission_id: str
    request_fingerprint: str
    status: ControlledSubmissionStatus
    reason_code: str
    claim_token: str | None = None
    broker_reference: PaperBrokerOrderReference | None = None
    source_fingerprint: str | None = None
    conflicting_owner_aggregate_id: PaperExecutionAggregateId | None = None
    conflicting_owner_command_id: PaperExecutionCommandId | None = None
    conflicting_owner_record_fingerprint: str | None = None
    dispatch_invoked: bool = False
    outcome_unknown: bool = False
    reconciliation_required: bool = False
    operator_action_required: bool = False
    failure_kind: PaperExecutionFailureKind | None = None
    automatic_retry: bool = field(init=False, default=False)
    result_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        for name in ("submission_id", "request_fingerprint", "reason_code"):
            object.__setattr__(self, name, _safe_alias(getattr(self, name), name))
        if not isinstance(self.status, ControlledSubmissionStatus):
            raise PaperExecutionInvariantError(
                "INVALID_RESULT_STATUS", "Submission result status is invalid."
            )
        for name in (
            "dispatch_invoked",
            "outcome_unknown",
            "reconciliation_required",
            "operator_action_required",
        ):
            if not isinstance(getattr(self, name), bool):
                raise PaperExecutionInvariantError(
                    "INVALID_RESULT_FLAG", "Submission result flags must be boolean."
                )
        for name in ("claim_token", "source_fingerprint"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _safe_alias(value, name))
        if self.broker_reference is not None and not isinstance(
            self.broker_reference, PaperBrokerOrderReference
        ):
            raise PaperExecutionInvariantError(
                "INVALID_BROKER_REFERENCE", "Broker reference must be committed."
            )
        if self.failure_kind is not None and not isinstance(
            self.failure_kind, PaperExecutionFailureKind
        ):
            raise PaperExecutionInvariantError(
                "INVALID_FAILURE_KIND", "Failure kind is invalid."
            )
        owner_values = (
            self.conflicting_owner_aggregate_id,
            self.conflicting_owner_command_id,
            self.conflicting_owner_record_fingerprint,
        )
        ownership_conflict = self.reason_code == "BROKER_REFERENCE_OWNERSHIP_CONFLICT"
        if ownership_conflict:
            if (
                not isinstance(
                    self.conflicting_owner_aggregate_id, PaperExecutionAggregateId
                )
                or not isinstance(
                    self.conflicting_owner_command_id, PaperExecutionCommandId
                )
                or self.conflicting_owner_record_fingerprint is None
            ):
                raise PaperExecutionInvariantError(
                    "INCOMPLETE_CONFLICT_OWNER",
                    "Broker conflict result requires exact owner evidence.",
                )
            object.__setattr__(
                self,
                "conflicting_owner_record_fingerprint",
                _safe_alias(
                    self.conflicting_owner_record_fingerprint,
                    "conflicting_owner_record_fingerprint",
                ),
            )
        elif any(value is not None for value in owner_values):
            raise PaperExecutionInvariantError(
                "UNEXPECTED_CONFLICT_OWNER",
                "Non-conflict result cannot carry owner evidence.",
            )
        if self.status is ControlledSubmissionStatus.OUTCOME_UNKNOWN:
            if (
                not self.dispatch_invoked
                or not self.outcome_unknown
                or not self.reconciliation_required
            ):
                raise PaperExecutionInvariantError(
                    "INVALID_UNKNOWN_OUTCOME",
                    "Unknown outcome requires invocation and reconciliation.",
                )
        elif (
            self.outcome_unknown
            or self.reconciliation_required
            or self.operator_action_required
        ):
            raise PaperExecutionInvariantError(
                "INVALID_KNOWN_OUTCOME", "Known result cannot carry ambiguity flags."
            )
        if self.status in {
            ControlledSubmissionStatus.ACKNOWLEDGED,
            ControlledSubmissionStatus.BROKER_REJECTED,
        } and (not self.dispatch_invoked or self.broker_reference is None):
            raise PaperExecutionInvariantError(
                "BROKER_REFERENCE_REQUIRED", "Broker observation requires a reference."
            )
        if self.broker_reference is not None and self.status not in {
            ControlledSubmissionStatus.ACKNOWLEDGED,
            ControlledSubmissionStatus.BROKER_REJECTED,
            ControlledSubmissionStatus.OUTCOME_UNKNOWN,
        }:
            raise PaperExecutionInvariantError(
                "UNEXPECTED_BROKER_REFERENCE",
                "Result variant cannot carry broker reference.",
            )
        primitive = {
            name: getattr(self, name)
            for name in (
                "automatic_retry",
                "broker_reference",
                "claim_token",
                "conflicting_owner_aggregate_id",
                "conflicting_owner_command_id",
                "conflicting_owner_record_fingerprint",
                "dispatch_invoked",
                "failure_kind",
                "operator_action_required",
                "outcome_unknown",
                "reason_code",
                "reconciliation_required",
                "request_fingerprint",
                "source_fingerprint",
                "status",
                "submission_id",
            )
        }
        object.__setattr__(
            self, "result_fingerprint", fingerprint_payload("psr", primitive)
        )


def _safe_alias(value: str, field_name: str) -> str:
    return validate_no_sensitive_text(normalize_alias(value, field_name), field_name)


def _safe_code(value: str, field_name: str) -> str:
    return validate_no_sensitive_text(normalize_code(value, field_name), field_name)
