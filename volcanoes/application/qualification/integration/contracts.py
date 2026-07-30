"""Immutable contracts for Paper qualification runtime integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import TypeAlias

from volcanoes.application.qualification.contracts import (
    ActorType,
    CommandId,
    CorrelationId,
    Guard,
    IdempotencyKey,
    QualificationRunId,
    QualificationScenarioId,
    StateRevision,
)
from volcanoes.application.qualification.integration.errors import (
    PaperEnvironmentRequiredError,
    RuntimeRequestValidationError,
    UnsafeIntegrationMetadataError,
)

MetadataScalar: TypeAlias = str | int | bool | None
MetadataValue: TypeAlias = MetadataScalar | tuple[MetadataScalar, ...]
SafeMetadata: TypeAlias = tuple[tuple[str, MetadataValue], ...]

_SECRET_TERMS = (
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "passwd",
    "authorization",
    "cookie",
    "private_key",
    "account",
    "connection_string",
)
_SECRET_VALUE_MARKERS = (
    "sentinel_integration_secret_do_not_expose",
    "sentinel_broker_token_do_not_expose",
    "sentinel_password_do_not_expose",
    "api_key=",
    "secret=",
    "token=",
    "password=",
    "authorization:",
    "bearer ",
)
_PROHIBITED_METADATA_KEYS = frozenset({"raw_payload", "broker_payload"})


class PaperIntegrationEnvironment(StrEnum):
    """Explicit runtime environment values accepted by integration contracts."""

    PAPER = "PAPER"
    LIVE = "LIVE"


class RuntimeRequestKind(StrEnum):
    """Runtime-originated qualification commands supported by this slice."""

    START_QUALIFICATION = "START_QUALIFICATION"
    PRECHECKS_PASSED = "PRECHECKS_PASSED"
    PRECHECKS_FAILED = "PRECHECKS_FAILED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    OPERATOR_APPROVED = "OPERATOR_APPROVED"
    OPERATOR_REJECTED = "OPERATOR_REJECTED"
    CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"
    ABORT_REQUESTED = "ABORT_REQUESTED"


class IntegrationOrderType(StrEnum):
    """Broker-neutral order intent categories safe for translation."""

    LIMIT = "LIMIT"
    MARKET = "MARKET"
    BRACKET_LIMIT = "BRACKET_LIMIT"


class IntegrationTimeInForce(StrEnum):
    """Broker-neutral time-in-force values currently safe to describe."""

    DAY = "DAY"
    GTC = "GTC"


class RuntimeActionKind(StrEnum):
    """Runtime action descriptions derived from qualification execution plans."""

    PREPARE_BROKER_SUBMISSION = "PREPARE_BROKER_SUBMISSION"
    REQUEST_BROKER_SUBMISSION = "REQUEST_BROKER_SUBMISSION"
    REQUEST_BROKER_CANCELLATION = "REQUEST_BROKER_CANCELLATION"
    START_RECONCILIATION = "START_RECONCILIATION"
    BLOCK_CONSEQUENTIAL_ACTION = "BLOCK_CONSEQUENTIAL_ACTION"
    FINALIZE_WITHOUT_EXTERNAL_EFFECT = "FINALIZE_WITHOUT_EXTERNAL_EFFECT"
    NO_RUNTIME_ACTION_REQUIRED = "NO_RUNTIME_ACTION_REQUIRED"


class RuntimeObservationType(StrEnum):
    """Normalized runtime observations for later qualification facade slices."""

    BROKER_REQUEST_ACKNOWLEDGED = "BROKER_REQUEST_ACKNOWLEDGED"
    BROKER_REQUEST_REJECTED = "BROKER_REQUEST_REJECTED"
    BROKER_REQUEST_OUTCOME_UNCERTAIN = "BROKER_REQUEST_OUTCOME_UNCERTAIN"
    CANCELLATION_CONFIRMED = "CANCELLATION_CONFIRMED"
    CANCELLATION_REJECTED = "CANCELLATION_REJECTED"
    PARTIAL_FILL_OBSERVED = "PARTIAL_FILL_OBSERVED"
    COMPLETE_FILL_OBSERVED = "COMPLETE_FILL_OBSERVED"
    RECONCILIATION_RESOLVED = "RECONCILIATION_RESOLVED"
    RECONCILIATION_INCONCLUSIVE = "RECONCILIATION_INCONCLUSIVE"
    ORDER_ABSENT = "ORDER_ABSENT"
    OPEN_ORDER_PRESENT = "OPEN_ORDER_PRESENT"
    NO_POSITION = "NO_POSITION"
    POSITION_PRESENT = "POSITION_PRESENT"


@dataclass(frozen=True, slots=True)
class SafeOrderIntent:
    """Safe order intent facts; this is not a broker order or acknowledgment."""

    symbol: str
    quantity: int
    order_type: IntegrationOrderType
    limit_price: Decimal | None = None
    time_in_force: IntegrationTimeInForce | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", normalize_symbol(self.symbol))
        object.__setattr__(self, "quantity", validate_positive_int(self.quantity))
        if not isinstance(self.order_type, IntegrationOrderType):
            raise RuntimeRequestValidationError(
                reason_code="UNSUPPORTED_ORDER_TYPE",
                safe_message="Order type is unsupported.",
            )
        if self.time_in_force is not None and not isinstance(
            self.time_in_force,
            IntegrationTimeInForce,
        ):
            raise RuntimeRequestValidationError(
                reason_code="UNSUPPORTED_TIME_IN_FORCE",
                safe_message="Time in force is unsupported.",
            )
        normalized_limit = normalize_optional_decimal(self.limit_price)
        if (
            self.order_type
            in {
                IntegrationOrderType.LIMIT,
                IntegrationOrderType.BRACKET_LIMIT,
            }
            and normalized_limit is None
        ):
            raise RuntimeRequestValidationError(
                reason_code="LIMIT_PRICE_REQUIRED",
                safe_message="Limit order intent requires a limit price.",
            )
        if (
            self.order_type is IntegrationOrderType.MARKET
            and normalized_limit is not None
        ):
            raise RuntimeRequestValidationError(
                reason_code="IRRELEVANT_LIMIT_PRICE",
                safe_message="Market order intent cannot carry a limit price.",
            )
        object.__setattr__(self, "limit_price", normalized_limit)


@dataclass(frozen=True, slots=True)
class PaperRuntimeRequest:
    """Minimum safe input from the existing Paper runtime."""

    environment: PaperIntegrationEnvironment
    runtime_request_id: str
    qualification_run_id: QualificationRunId
    qualification_scenario_id: QualificationScenarioId
    request_kind: RuntimeRequestKind
    command_id: CommandId
    correlation_id: CorrelationId
    idempotency_key: IdempotencyKey
    expected_revision: StateRevision
    actor_type: ActorType
    occurred_at: datetime
    order_intent: SafeOrderIntent | None = None
    satisfied_guards: frozenset[Guard] = frozenset()
    object_reference: str | None = None
    reason_code: str | None = None
    metadata: SafeMetadata = ()

    def __post_init__(self) -> None:
        require_paper_environment(self.environment)
        object.__setattr__(
            self,
            "runtime_request_id",
            validate_identifier(self.runtime_request_id, "runtime_request_id"),
        )
        for name in (
            "qualification_run_id",
            "qualification_scenario_id",
            "command_id",
            "correlation_id",
            "idempotency_key",
        ):
            validate_identifier(getattr(self, name), name)
        if not isinstance(self.request_kind, RuntimeRequestKind):
            raise RuntimeRequestValidationError(
                reason_code="UNSUPPORTED_RUNTIME_REQUEST",
                safe_message="Runtime request kind is unsupported.",
            )
        if not isinstance(self.actor_type, ActorType):
            raise RuntimeRequestValidationError(
                reason_code="INVALID_ACTOR_TYPE",
                safe_message="Actor type is invalid.",
            )
        object.__setattr__(
            self,
            "expected_revision",
            StateRevision(validate_non_negative_int(self.expected_revision)),
        )
        object.__setattr__(self, "occurred_at", normalize_timestamp(self.occurred_at))
        object.__setattr__(
            self,
            "satisfied_guards",
            frozenset(validate_guard(guard) for guard in self.satisfied_guards),
        )
        if self.object_reference is not None:
            object.__setattr__(
                self,
                "object_reference",
                validate_identifier(self.object_reference, "object_reference"),
            )
        if self.reason_code is not None:
            object.__setattr__(
                self,
                "reason_code",
                validate_identifier(self.reason_code, "reason_code"),
            )
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class RuntimeActionRequest:
    """Description of a runtime action; not proof that any effect happened."""

    environment: PaperIntegrationEnvironment
    action_request_id: str
    action_kind: RuntimeActionKind
    qualification_run_id: QualificationRunId
    command_id: CommandId
    correlation_id: CorrelationId
    idempotency_key: IdempotencyKey
    source_transition_id: str
    source_revision: StateRevision
    safe_operator_message: str
    order_intent: SafeOrderIntent | None = None
    cancellation_reference: str | None = None
    reconciliation_reason: str | None = None
    metadata: SafeMetadata = ()

    def __post_init__(self) -> None:
        require_paper_environment(self.environment)
        object.__setattr__(
            self,
            "action_request_id",
            validate_identifier(self.action_request_id, "action_request_id"),
        )
        if not isinstance(self.action_kind, RuntimeActionKind):
            raise RuntimeRequestValidationError(
                reason_code="UNSUPPORTED_ACTION_KIND",
                safe_message="Runtime action kind is unsupported.",
            )
        for name in (
            "qualification_run_id",
            "command_id",
            "correlation_id",
            "idempotency_key",
            "source_transition_id",
            "safe_operator_message",
        ):
            validate_identifier(getattr(self, name), name)
        object.__setattr__(
            self,
            "source_revision",
            StateRevision(validate_non_negative_int(self.source_revision)),
        )
        if self.cancellation_reference is not None:
            object.__setattr__(
                self,
                "cancellation_reference",
                validate_identifier(
                    self.cancellation_reference,
                    "cancellation_reference",
                ),
            )
        if self.reconciliation_reason is not None:
            object.__setattr__(
                self,
                "reconciliation_reason",
                validate_identifier(
                    self.reconciliation_reason,
                    "reconciliation_reason",
                ),
            )
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class NormalizedRuntimeObservation:
    """Broker-neutral reported fact; not a transition decision."""

    environment: PaperIntegrationEnvironment
    observation_id: str
    qualification_run_id: QualificationRunId
    qualification_scenario_id: QualificationScenarioId
    observation_type: RuntimeObservationType
    command_id: CommandId
    correlation_id: CorrelationId
    idempotency_key: IdempotencyKey
    expected_revision: StateRevision
    actor_type: ActorType
    occurred_at: datetime
    broker_request_reference: str | None = None
    order_reference: str | None = None
    quantity: int | None = None
    satisfied_guards: frozenset[Guard] = frozenset()
    safe_reason_code: str | None = None
    metadata: SafeMetadata = ()

    def __post_init__(self) -> None:
        require_paper_environment(self.environment)
        object.__setattr__(
            self,
            "observation_id",
            validate_identifier(self.observation_id, "observation_id"),
        )
        for name in (
            "qualification_run_id",
            "qualification_scenario_id",
            "command_id",
            "correlation_id",
            "idempotency_key",
        ):
            validate_identifier(getattr(self, name), name)
        if not isinstance(self.observation_type, RuntimeObservationType):
            raise RuntimeRequestValidationError(
                reason_code="UNSUPPORTED_OBSERVATION_TYPE",
                safe_message="Runtime observation type is unsupported.",
            )
        if not isinstance(self.actor_type, ActorType):
            raise RuntimeRequestValidationError(
                reason_code="INVALID_ACTOR_TYPE",
                safe_message="Actor type is invalid.",
            )
        object.__setattr__(
            self,
            "expected_revision",
            StateRevision(validate_non_negative_int(self.expected_revision)),
        )
        object.__setattr__(self, "occurred_at", normalize_timestamp(self.occurred_at))
        for name in ("broker_request_reference", "order_reference", "safe_reason_code"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, validate_identifier(value, name))
        if self.quantity is not None:
            object.__setattr__(self, "quantity", validate_positive_int(self.quantity))
        object.__setattr__(
            self,
            "satisfied_guards",
            frozenset(validate_guard(guard) for guard in self.satisfied_guards),
        )
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))


def require_paper_environment(
    environment: PaperIntegrationEnvironment,
) -> PaperIntegrationEnvironment:
    """Return PAPER or fail deterministically without silent fallback."""

    if environment is PaperIntegrationEnvironment.PAPER:
        return environment
    if environment is PaperIntegrationEnvironment.LIVE:
        raise PaperEnvironmentRequiredError(
            reason_code="PAPER_ENVIRONMENT_REQUIRED",
            safe_message="Paper qualification integration requires Paper environment.",
        )
    raise PaperEnvironmentRequiredError(
        reason_code="UNKNOWN_ENVIRONMENT",
        safe_message="Paper qualification integration environment is unsupported.",
    )


def validate_identifier(value: object, field_name: str) -> str:
    """Validate one safe opaque identifier."""

    if not isinstance(value, str) or not value.strip():
        raise RuntimeRequestValidationError(
            reason_code="INVALID_IDENTIFIER",
            safe_message=f"{field_name} cannot be empty.",
        )
    normalized = value.strip()
    if _unsafe_string(normalized):
        raise RuntimeRequestValidationError(
            reason_code="UNSAFE_IDENTIFIER",
            safe_message=f"{field_name} is not safe for integration use.",
        )
    return normalized


def validate_positive_int(value: object) -> int:
    """Validate a positive integer while rejecting bools."""

    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeRequestValidationError(
            reason_code="INVALID_QUANTITY",
            safe_message="Quantity must be a positive integer.",
        )
    return value


def validate_non_negative_int(value: object) -> int:
    """Validate a non-negative integer while rejecting bools."""

    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RuntimeRequestValidationError(
            reason_code="INVALID_REVISION",
            safe_message="Expected revision must be a non-negative integer.",
        )
    return value


def validate_guard(value: object) -> Guard:
    """Validate one qualification guard fact."""

    if not isinstance(value, Guard):
        raise RuntimeRequestValidationError(
            reason_code="INVALID_GUARD",
            safe_message="Guard fact is invalid.",
        )
    return value


def normalize_symbol(symbol: object) -> str:
    """Normalize symbols using the repository's uppercase convention."""

    if not isinstance(symbol, str) or not symbol.strip():
        raise RuntimeRequestValidationError(
            reason_code="INVALID_SYMBOL",
            safe_message="Symbol cannot be empty.",
        )
    normalized = symbol.strip().upper()
    if _unsafe_string(normalized):
        raise RuntimeRequestValidationError(
            reason_code="UNSAFE_SYMBOL",
            safe_message="Symbol is not safe for integration use.",
        )
    return normalized


def normalize_optional_decimal(value: object) -> Decimal | None:
    """Normalize optional decimal input without binary-float ambiguity."""

    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise RuntimeRequestValidationError(
            reason_code="INVALID_DECIMAL",
            safe_message="Decimal values must be supplied without binary floats.",
        )
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise RuntimeRequestValidationError(
            reason_code="INVALID_DECIMAL",
            safe_message="Decimal value is invalid.",
        ) from error
    if not decimal_value.is_finite():
        raise RuntimeRequestValidationError(
            reason_code="INVALID_DECIMAL",
            safe_message="Decimal value must be finite.",
        )
    return decimal_value


def normalize_timestamp(value: object) -> datetime:
    """Require timezone-aware timestamps and normalize to UTC."""

    if not isinstance(value, datetime) or value.tzinfo is None:
        raise RuntimeRequestValidationError(
            reason_code="INVALID_TIMESTAMP",
            safe_message="Timestamp must be timezone-aware.",
        )
    return value.astimezone(UTC)


def normalize_metadata(metadata: object) -> SafeMetadata:
    """Normalize safe metadata without accepting mutable or secret payloads."""

    if not isinstance(metadata, tuple):
        raise UnsafeIntegrationMetadataError(
            reason_code="UNSAFE_METADATA",
            safe_message="Integration metadata must be an immutable tuple.",
        )
    normalized: list[tuple[str, MetadataValue]] = []
    for item in metadata:
        if not isinstance(item, tuple) or len(item) != 2:
            raise UnsafeIntegrationMetadataError(
                reason_code="UNSAFE_METADATA",
                safe_message="Integration metadata entries are invalid.",
            )
        if not isinstance(item[0], str) or not item[0].strip():
            raise UnsafeIntegrationMetadataError(
                reason_code="UNSAFE_METADATA",
                safe_message="Integration metadata entries are invalid.",
            )
        key = item[0].strip().lower()
        if key in _PROHIBITED_METADATA_KEYS or _unsafe_string(key):
            raise UnsafeIntegrationMetadataError(
                reason_code="UNSAFE_METADATA",
                safe_message="Integration metadata contains unsafe keys.",
            )
        normalized.append((key, _normalize_metadata_value(item[1])))
    return tuple(sorted(normalized))


def _normalize_metadata_value(value: object) -> MetadataValue:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if _unsafe_string(stripped):
            raise UnsafeIntegrationMetadataError(
                reason_code="UNSAFE_METADATA",
                safe_message="Integration metadata contains unsafe values.",
            )
        return stripped
    if isinstance(value, tuple):
        return tuple(_normalize_metadata_scalar(item) for item in value)
    raise UnsafeIntegrationMetadataError(
        reason_code="UNSAFE_METADATA",
        safe_message="Integration metadata contains unsupported values.",
    )


def _normalize_metadata_scalar(value: object) -> MetadataScalar:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if _unsafe_string(stripped):
            raise UnsafeIntegrationMetadataError(
                reason_code="UNSAFE_METADATA",
                safe_message="Integration metadata contains unsafe values.",
            )
        return stripped
    raise UnsafeIntegrationMetadataError(
        reason_code="UNSAFE_METADATA",
        safe_message="Integration metadata contains unsupported values.",
    )


def _unsafe_string(value: str) -> bool:
    lower = value.lower()
    if "/" in value or "\\" in value:
        return True
    return any(term in lower for term in _SECRET_TERMS) or any(
        marker in lower for marker in _SECRET_VALUE_MARKERS
    )
