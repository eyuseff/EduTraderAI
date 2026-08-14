"""Immutable contracts for offline Paper boundary certification."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import TypeAlias

from volcanoes.application.execution._canonical import normalize_decimal
from volcanoes.application.execution.contracts._validation import (
    normalize_alias,
    normalize_code,
    normalize_symbol,
    validate_no_sensitive_text,
)
from volcanoes.application.execution.errors import PaperExecutionInvariantError
from volcanoes.application.execution.fingerprints import fingerprint_payload

SafeScalar: TypeAlias = str | int | bool | None
SafeFields: TypeAlias = tuple[tuple[str, SafeScalar], ...]


class CertificationObservationKind(StrEnum):
    """Supported normalized synthetic observation categories."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REPLACED = "REPLACED"


class CertificationFailurePhase(StrEnum):
    """Whether an external effect is impossible or may have occurred."""

    PRE_DISPATCH = "PRE_DISPATCH"
    POSSIBLE_POST_DISPATCH = "POSSIBLE_POST_DISPATCH"


class CertificationResultKind(StrEnum):
    OBSERVATION = "OBSERVATION"
    PRE_DISPATCH_FAILURE = "PRE_DISPATCH_FAILURE"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"
    IDENTITY_CONFLICT = "IDENTITY_CONFLICT"
    OWNERSHIP_CONFLICT = "OWNERSHIP_CONFLICT"
    MALFORMED = "MALFORMED"


@dataclass(frozen=True, slots=True)
class SyntheticOrderFixture:
    """Synthetic input used only to certify deterministic request mapping."""

    fixture_id: str
    client_order_id: str
    symbol: str
    side: str
    quantity: Decimal
    order_type: str
    time_in_force: str
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    fixture_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "fixture_id", normalize_alias(self.fixture_id, "fixture_id")
        )
        object.__setattr__(
            self,
            "client_order_id",
            normalize_alias(self.client_order_id, "client_order_id"),
        )
        object.__setattr__(self, "symbol", normalize_symbol(self.symbol))
        for name in ("side", "order_type", "time_in_force"):
            normalized_code = normalize_code(getattr(self, name), name)
            object.__setattr__(
                self,
                name,
                validate_no_sensitive_text(normalized_code, name),
            )
        object.__setattr__(
            self, "quantity", _positive_decimal(self.quantity, "quantity")
        )
        for name in ("limit_price", "stop_price"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _positive_decimal(value, name))
        object.__setattr__(
            self,
            "fixture_fingerprint",
            fingerprint_payload("cfi", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "fixture_fingerprint": self.fixture_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "client_order_id": self.client_order_id,
            "fixture_id": self.fixture_id,
            "limit_price": self.limit_price,
            "order_type": self.order_type,
            "quantity": self.quantity,
            "side": self.side,
            "stop_price": self.stop_price,
            "symbol": self.symbol,
            "time_in_force": self.time_in_force,
        }

    def expected_mapped_fields(self) -> SafeFields:
        """Return the one complete canonical mapping accepted by the harness."""

        return _normalize_safe_fields(
            (
                ("limit_price", _optional_decimal_text(self.limit_price)),
                ("order_type", self.order_type),
                ("quantity", normalize_decimal(self.quantity, "quantity")),
                ("side", self.side),
                ("stop_price", _optional_decimal_text(self.stop_price)),
                ("symbol", self.symbol),
                ("time_in_force", self.time_in_force),
            )
        )


@dataclass(frozen=True, slots=True)
class MappedRequest:
    """Secret-free immutable result of a pure mapper."""

    fixture_id: str
    client_order_id: str
    fields: SafeFields
    request_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "fixture_id", normalize_alias(self.fixture_id, "fixture_id")
        )
        object.__setattr__(
            self,
            "client_order_id",
            normalize_alias(self.client_order_id, "client_order_id"),
        )
        object.__setattr__(self, "fields", _normalize_safe_fields(self.fields))
        object.__setattr__(
            self,
            "request_fingerprint",
            fingerprint_payload("cmr", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "request_fingerprint": self.request_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "client_order_id": self.client_order_id,
            "fields": self.fields,
            "fixture_id": self.fixture_id,
        }


@dataclass(frozen=True, slots=True)
class SyntheticResponseFixture:
    """Synthetic response or failure presented to a pure normalizer."""

    fixture_id: str
    broker_reference: str | None = None
    observation_kind: CertificationObservationKind | None = None
    message_code: str = "CERTIFICATION_FIXTURE"
    fields: SafeFields = ()
    failure_phase: CertificationFailurePhase | None = None
    expected_safe_message: str | None = None
    response_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "fixture_id", normalize_alias(self.fixture_id, "fixture_id")
        )
        if self.broker_reference is not None:
            object.__setattr__(
                self,
                "broker_reference",
                normalize_alias(self.broker_reference, "broker_reference"),
            )
        if self.observation_kind is not None and not isinstance(
            self.observation_kind, CertificationObservationKind
        ):
            raise PaperExecutionInvariantError(
                "INVALID_OBSERVATION", "Observation kind is invalid."
            )
        if self.failure_phase is not None and not isinstance(
            self.failure_phase, CertificationFailurePhase
        ):
            raise PaperExecutionInvariantError(
                "INVALID_FAILURE_PHASE", "Failure phase is invalid."
            )
        if (self.observation_kind is None) == (self.failure_phase is None):
            raise PaperExecutionInvariantError(
                "AMBIGUOUS_RESPONSE_FIXTURE",
                "Exactly one observation or failure phase is required.",
            )
        if self.observation_kind is not None and self.broker_reference is None:
            raise PaperExecutionInvariantError(
                "BROKER_REFERENCE_REQUIRED", "Observations require a broker reference."
            )
        if self.failure_phase is not None:
            safe_message = (
                "Synthetic failure normalized safely."
                if self.expected_safe_message is None
                else self.expected_safe_message
            )
            object.__setattr__(
                self, "expected_safe_message", _normalize_safe_message(safe_message)
            )
        elif self.expected_safe_message is not None:
            raise PaperExecutionInvariantError(
                "UNEXPECTED_SAFE_MESSAGE",
                "Observation fixtures cannot define a failure safe message.",
            )
        object.__setattr__(
            self,
            "message_code",
            validate_no_sensitive_text(
                normalize_code(self.message_code, "message_code"), "message_code"
            ),
        )
        object.__setattr__(self, "fields", _normalize_safe_fields(self.fields))
        object.__setattr__(
            self,
            "response_fingerprint",
            fingerprint_payload("crf", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "response_fingerprint": self.response_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "broker_reference": self.broker_reference,
            "expected_safe_message": self.expected_safe_message,
            "failure_phase": self.failure_phase,
            "fields": self.fields,
            "fixture_id": self.fixture_id,
            "message_code": self.message_code,
            "observation_kind": self.observation_kind,
        }


@dataclass(frozen=True, slots=True)
class NormalizedObservation:
    fixture_id: str
    broker_reference: str
    kind: CertificationObservationKind
    message_code: str
    fields: SafeFields = ()
    observation_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "fixture_id", normalize_alias(self.fixture_id, "fixture_id")
        )
        object.__setattr__(
            self,
            "broker_reference",
            normalize_alias(self.broker_reference, "broker_reference"),
        )
        if not isinstance(self.kind, CertificationObservationKind):
            raise PaperExecutionInvariantError(
                "INVALID_OBSERVATION", "Observation kind is invalid."
            )
        object.__setattr__(
            self,
            "message_code",
            validate_no_sensitive_text(
                normalize_code(self.message_code, "message_code"), "message_code"
            ),
        )
        object.__setattr__(self, "fields", _normalize_safe_fields(self.fields))
        object.__setattr__(
            self,
            "observation_fingerprint",
            fingerprint_payload("cob", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "observation_fingerprint": self.observation_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "broker_reference": self.broker_reference,
            "fields": self.fields,
            "fixture_id": self.fixture_id,
            "kind": self.kind,
            "message_code": self.message_code,
        }


@dataclass(frozen=True, slots=True)
class NormalizedFailure:
    fixture_id: str
    phase: CertificationFailurePhase
    reason_code: str
    safe_message: str
    broker_reference: str | None = None
    fields: SafeFields = ()
    outcome_unknown: bool = field(init=False)
    automatic_resubmission: bool = field(init=False, default=False)
    failure_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "fixture_id", normalize_alias(self.fixture_id, "fixture_id")
        )
        if not isinstance(self.phase, CertificationFailurePhase):
            raise PaperExecutionInvariantError(
                "INVALID_FAILURE_PHASE", "Failure phase is invalid."
            )
        if self.broker_reference is not None:
            object.__setattr__(
                self,
                "broker_reference",
                normalize_alias(self.broker_reference, "broker_reference"),
            )
        object.__setattr__(
            self,
            "reason_code",
            validate_no_sensitive_text(
                normalize_code(self.reason_code, "reason_code"), "reason_code"
            ),
        )
        object.__setattr__(
            self,
            "safe_message",
            _normalize_safe_message(self.safe_message),
        )
        object.__setattr__(self, "fields", _normalize_safe_fields(self.fields))
        object.__setattr__(
            self,
            "outcome_unknown",
            self.phase is CertificationFailurePhase.POSSIBLE_POST_DISPATCH,
        )
        object.__setattr__(self, "automatic_resubmission", False)
        object.__setattr__(
            self,
            "failure_fingerprint",
            fingerprint_payload("cnf", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "failure_fingerprint": self.failure_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "automatic_resubmission": self.automatic_resubmission,
            "broker_reference": self.broker_reference,
            "fields": self.fields,
            "fixture_id": self.fixture_id,
            "outcome_unknown": self.outcome_unknown,
            "phase": self.phase,
            "reason_code": self.reason_code,
            "safe_message": self.safe_message,
        }


@dataclass(frozen=True, slots=True)
class CertificationResult:
    fixture_id: str
    request_fingerprint: str
    response_fingerprint: str
    kind: CertificationResultKind
    observation: NormalizedObservation | None = None
    failure: NormalizedFailure | None = None
    reason_code: str = "CERTIFIED"
    result_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "fixture_id", normalize_alias(self.fixture_id, "fixture_id")
        )
        object.__setattr__(
            self,
            "request_fingerprint",
            normalize_alias(self.request_fingerprint, "request_fingerprint"),
        )
        object.__setattr__(
            self,
            "response_fingerprint",
            normalize_alias(self.response_fingerprint, "response_fingerprint"),
        )
        if not isinstance(self.kind, CertificationResultKind):
            raise PaperExecutionInvariantError(
                "INVALID_RESULT", "Result kind is invalid."
            )
        object.__setattr__(
            self,
            "reason_code",
            validate_no_sensitive_text(
                normalize_code(self.reason_code, "reason_code"), "reason_code"
            ),
        )
        if (
            self.kind is CertificationResultKind.OBSERVATION
            and self.observation is None
        ):
            raise PaperExecutionInvariantError(
                "INCOMPLETE_RESULT", "Observation result is incomplete."
            )
        if (
            self.kind
            in (
                CertificationResultKind.PRE_DISPATCH_FAILURE,
                CertificationResultKind.OUTCOME_UNKNOWN,
            )
            and self.failure is None
        ):
            raise PaperExecutionInvariantError(
                "INCOMPLETE_RESULT", "Failure result is incomplete."
            )
        if (
            self.observation is not None
            and self.observation.fixture_id != self.fixture_id
        ):
            raise PaperExecutionInvariantError(
                "RESULT_IDENTITY_MISMATCH",
                "Observation identity must match result identity.",
            )
        if self.failure is not None and self.failure.fixture_id != self.fixture_id:
            raise PaperExecutionInvariantError(
                "RESULT_IDENTITY_MISMATCH",
                "Failure identity must match result identity.",
            )
        if (
            self.kind is CertificationResultKind.OBSERVATION
            and self.failure is not None
        ):
            raise PaperExecutionInvariantError(
                "AMBIGUOUS_RESULT", "Observation result cannot carry failure."
            )
        if (
            self.kind is not CertificationResultKind.OBSERVATION
            and self.observation is not None
        ):
            raise PaperExecutionInvariantError(
                "AMBIGUOUS_RESULT", "Non-observation result cannot carry observation."
            )
        if (
            self.kind
            not in (
                CertificationResultKind.PRE_DISPATCH_FAILURE,
                CertificationResultKind.OUTCOME_UNKNOWN,
            )
            and self.failure is not None
        ):
            raise PaperExecutionInvariantError(
                "AMBIGUOUS_RESULT", "This result kind cannot carry failure."
            )
        if (
            self.kind is CertificationResultKind.PRE_DISPATCH_FAILURE
            and self.failure is not None
            and (
                self.failure.phase is not CertificationFailurePhase.PRE_DISPATCH
                or self.failure.outcome_unknown
            )
        ):
            raise PaperExecutionInvariantError(
                "FAILURE_VARIANT_MISMATCH",
                "Pre-dispatch results require a known pre-dispatch failure.",
            )
        if (
            self.kind is CertificationResultKind.OUTCOME_UNKNOWN
            and self.failure is not None
            and (
                self.failure.phase
                is not CertificationFailurePhase.POSSIBLE_POST_DISPATCH
                or not self.failure.outcome_unknown
            )
        ):
            raise PaperExecutionInvariantError(
                "FAILURE_VARIANT_MISMATCH",
                "Unknown outcomes require possible-post-dispatch ambiguity.",
            )
        if (
            self.kind
            in (
                CertificationResultKind.PRE_DISPATCH_FAILURE,
                CertificationResultKind.OUTCOME_UNKNOWN,
            )
            and self.failure is not None
            and self.reason_code != self.failure.reason_code
        ):
            raise PaperExecutionInvariantError(
                "FAILURE_REASON_MISMATCH",
                "Failure result reason must match its normalized failure.",
            )
        expected_reason = {
            CertificationResultKind.OBSERVATION: "CERTIFIED",
            CertificationResultKind.IDENTITY_CONFLICT: "FIXTURE_IDENTITY_CONFLICT",
            CertificationResultKind.OWNERSHIP_CONFLICT: (
                "BROKER_REFERENCE_OWNERSHIP_CONFLICT"
            ),
        }.get(self.kind)
        if expected_reason is not None and self.reason_code != expected_reason:
            raise PaperExecutionInvariantError(
                "RESULT_REASON_MISMATCH",
                "Result reason does not match its result variant.",
            )
        if (
            self.kind is CertificationResultKind.MALFORMED
            and self.reason_code == "CERTIFIED"
        ):
            raise PaperExecutionInvariantError(
                "RESULT_REASON_MISMATCH",
                "Malformed results require a specific safe reason.",
            )
        object.__setattr__(
            self,
            "result_fingerprint",
            fingerprint_payload("cer", self._primitive_without_fingerprint()),
        )

    def to_primitive(self) -> dict[str, object]:
        return {
            **self._primitive_without_fingerprint(),
            "result_fingerprint": self.result_fingerprint,
        }

    def _primitive_without_fingerprint(self) -> dict[str, object]:
        return {
            "failure": self.failure,
            "fixture_id": self.fixture_id,
            "kind": self.kind,
            "observation": self.observation,
            "reason_code": self.reason_code,
            "request_fingerprint": self.request_fingerprint,
            "response_fingerprint": self.response_fingerprint,
        }


def _positive_decimal(value: Decimal, field_name: str) -> Decimal:
    try:
        normalize_decimal(value, field_name)
    except Exception as error:
        raise PaperExecutionInvariantError(
            "INVALID_DECIMAL", f"{field_name} is invalid."
        ) from error
    if value <= Decimal("0"):
        raise PaperExecutionInvariantError(
            "NON_POSITIVE_DECIMAL", f"{field_name} must be positive."
        )
    return value


def _optional_decimal_text(value: Decimal | None) -> str | None:
    return None if value is None else normalize_decimal(value)


def _normalize_safe_message(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PaperExecutionInvariantError(
            "INVALID_SAFE_MESSAGE", "Safe message cannot be empty."
        )
    return validate_no_sensitive_text(value.strip(), "safe_message")


def _normalize_safe_fields(fields: SafeFields) -> SafeFields:
    if not isinstance(fields, tuple):
        raise PaperExecutionInvariantError(
            "INVALID_FIELDS", "Fields must be an immutable tuple."
        )
    normalized: list[tuple[str, SafeScalar]] = []
    seen: set[str] = set()
    for item in fields:
        if not isinstance(item, tuple) or len(item) != 2:
            raise PaperExecutionInvariantError(
                "INVALID_FIELDS", "Each field must be a key/value pair."
            )
        key, value = item
        normalized_key = normalize_alias(key, "field name")
        validate_no_sensitive_text(normalized_key, "field name")
        if normalized_key.lower() in seen:
            raise PaperExecutionInvariantError(
                "DUPLICATE_FIELD", "Field names must be unique."
            )
        seen.add(normalized_key.lower())
        if not (value is None or isinstance(value, str | int | bool)):
            raise PaperExecutionInvariantError(
                "INVALID_FIELD_VALUE", "Field values must be safe scalars."
            )
        if isinstance(value, str):
            value = validate_no_sensitive_text(value, "field value")
        normalized.append((normalized_key, value))
    return tuple(sorted(normalized))
