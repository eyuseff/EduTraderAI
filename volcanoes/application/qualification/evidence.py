"""Canonical in-memory evidence adapter for Paper qualification."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType
from typing import TypeAlias

from volcanoes.application.qualification.contracts import (
    CorrelationId,
    EvidenceIntent,
    QualificationResult,
    StateRevision,
)
from volcanoes.application.qualification.ports import EvidenceRecordReference

QUALIFICATION_EVIDENCE_SCHEMA_VERSION = "qualification-evidence/v1"
REDACTED_VALUE = "[REDACTED]"

MetadataScalar: TypeAlias = str | int | bool | None
MetadataValue: TypeAlias = MetadataScalar | tuple[MetadataScalar, ...]
MetadataInput: TypeAlias = tuple[tuple[str, MetadataValue], ...]
CanonicalValue: TypeAlias = (
    str | int | bool | None | list["CanonicalValue"] | dict[str, "CanonicalValue"]
)

_PROHIBITED_METADATA_KEYS = frozenset(
    {
        "broker_payload",
        "raw_payload",
    }
)
_SECRET_METADATA_TERMS = (
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "passwd",
    "authorization",
    "auth",
    "cookie",
    "private_key",
    "access_key",
    "refresh_token",
    "account_number",
    "connection_string",
    "database_url",
)
_MESSAGE_SECRET_MARKERS = (
    "api_key",
    "secret",
    "token",
    "password",
    "authorization",
    "cookie",
)
_MAX_MESSAGE_LENGTH = 500
_MAX_METADATA_KEY_LENGTH = 80


class QualificationEvidenceType(StrEnum):
    """Stable canonical qualification evidence categories."""

    QUALIFICATION_TRANSITION_ACCEPTED = "QUALIFICATION_TRANSITION_ACCEPTED"
    QUALIFICATION_TRANSITION_REJECTED = "QUALIFICATION_TRANSITION_REJECTED"
    QUALIFICATION_IDEMPOTENCY_CONFLICT = "QUALIFICATION_IDEMPOTENCY_CONFLICT"
    QUALIFICATION_GUARD_FAILED = "QUALIFICATION_GUARD_FAILED"
    QUALIFICATION_RECONCILIATION_REQUIRED = "QUALIFICATION_RECONCILIATION_REQUIRED"
    QUALIFICATION_TERMINAL_RESULT = "QUALIFICATION_TERMINAL_RESULT"


class QualificationEvidenceError(Exception):
    """Base evidence-adapter error with safe structured metadata."""

    def __init__(self, *, reason_code: str, safe_message: str) -> None:
        if not reason_code.strip():
            raise ValueError("reason_code cannot be empty.")
        if not safe_message.strip():
            raise ValueError("safe_message cannot be empty.")
        self.reason_code = reason_code
        self.safe_message = safe_message
        super().__init__(safe_message)

    def __str__(self) -> str:
        return self.safe_message


class EvidenceSchemaVersionError(QualificationEvidenceError):
    """Raised when an unsupported schema version is requested."""


class EvidenceValidationError(QualificationEvidenceError):
    """Raised when evidence input is structurally invalid."""


class EvidenceRedactionError(QualificationEvidenceError):
    """Raised when evidence cannot be made audit-safe."""


class EvidenceSerializationError(QualificationEvidenceError):
    """Raised when canonical serialization cannot be produced."""


class EvidenceIntegrityError(QualificationEvidenceError):
    """Raised when evidence digest verification fails."""


class EvidenceRecordConflictError(QualificationEvidenceError):
    """Raised when a duplicate evidence ID has conflicting content."""


@dataclass(frozen=True, slots=True)
class QualificationEvidenceIntegrity:
    """Integrity metadata for canonical evidence records."""

    algorithm: str
    digest: str | None = None

    def __post_init__(self) -> None:
        if self.algorithm != "sha256":
            raise EvidenceValidationError(
                reason_code="UNSUPPORTED_DIGEST_ALGORITHM",
                safe_message="Evidence digest algorithm is unsupported.",
            )
        if self.digest is not None and (
            len(self.digest) != 64
            or any(character not in "0123456789abcdef" for character in self.digest)
        ):
            raise EvidenceIntegrityError(
                reason_code="INVALID_DIGEST",
                safe_message="Evidence digest is not a valid SHA-256 hex digest.",
            )


@dataclass(frozen=True, slots=True)
class RedactionResult:
    """Redaction metadata captured without exposing original values."""

    redacted_fields: tuple[str, ...] = ()
    rejected_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "redacted_fields", tuple(sorted(self.redacted_fields)))
        object.__setattr__(self, "rejected_fields", tuple(sorted(self.rejected_fields)))


@dataclass(frozen=True, slots=True)
class QualificationEvidenceRecord:
    """Canonical audit-safe evidence record; not durable persistence."""

    schema_version: str
    evidence_id: str
    evidence_type: QualificationEvidenceType
    qualification_run_id: str
    qualification_scenario_id: str
    transition_id: str
    event_type: str
    command_id: str
    correlation_id: CorrelationId
    idempotency_key: str
    source_state: str
    destination_state: str
    previous_revision: StateRevision | None
    next_revision: StateRevision | None
    qualification_result: str
    reason_code: str
    actor_type: str
    environment: str
    safe_operator_message: str
    reconciliation_required: bool
    replayed: bool
    diagnostic: bool
    object_reference: str | None
    occurred_at: str
    metadata: MappingProxyType[str, MetadataValue]
    redaction: RedactionResult
    integrity: QualificationEvidenceIntegrity

    def __post_init__(self) -> None:
        if self.schema_version != QUALIFICATION_EVIDENCE_SCHEMA_VERSION:
            raise EvidenceSchemaVersionError(
                reason_code="UNSUPPORTED_EVIDENCE_SCHEMA",
                safe_message="Evidence schema version is unsupported.",
            )
        for name in (
            "evidence_id",
            "qualification_run_id",
            "qualification_scenario_id",
            "transition_id",
            "event_type",
            "command_id",
            "correlation_id",
            "idempotency_key",
            "source_state",
            "destination_state",
            "qualification_result",
            "reason_code",
            "actor_type",
            "environment",
            "safe_operator_message",
            "occurred_at",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise EvidenceValidationError(
                    reason_code="INVALID_EVIDENCE_RECORD",
                    safe_message=f"{name} cannot be empty.",
                )
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(sorted(self.metadata.items()))),
        )

    def to_canonical_dict(
        self, *, include_digest: bool = True
    ) -> dict[str, CanonicalValue]:
        """Return a deterministic primitive representation."""

        payload: dict[str, CanonicalValue] = {
            "actor_type": self.actor_type,
            "command_id": self.command_id,
            "correlation_id": self.correlation_id,
            "destination_state": self.destination_state,
            "diagnostic": self.diagnostic,
            "environment": self.environment,
            "event_type": self.event_type,
            "evidence_id": self.evidence_id,
            "evidence_type": self.evidence_type.value,
            "idempotency_key": self.idempotency_key,
            "integrity": {
                "algorithm": self.integrity.algorithm,
                "digest": self.integrity.digest if include_digest else None,
            },
            "metadata": _metadata_to_dict(self.metadata),
            "next_revision": self.next_revision,
            "object_reference": self.object_reference,
            "occurred_at": self.occurred_at,
            "previous_revision": self.previous_revision,
            "qualification_result": self.qualification_result,
            "qualification_run_id": self.qualification_run_id,
            "qualification_scenario_id": self.qualification_scenario_id,
            "reason_code": self.reason_code,
            "reconciliation_required": self.reconciliation_required,
            "redaction": {
                "redacted_fields": list(self.redaction.redacted_fields),
                "rejected_fields": list(self.redaction.rejected_fields),
            },
            "replayed": self.replayed,
            "safe_operator_message": self.safe_operator_message,
            "schema_version": self.schema_version,
            "source_state": self.source_state,
            "transition_id": self.transition_id,
        }
        return payload


class QualificationEvidenceAdapter:
    """Build canonical qualification evidence records from EvidenceIntent."""

    def __init__(
        self,
        *,
        schema_version: str = QUALIFICATION_EVIDENCE_SCHEMA_VERSION,
    ) -> None:
        if schema_version != QUALIFICATION_EVIDENCE_SCHEMA_VERSION:
            raise EvidenceSchemaVersionError(
                reason_code="UNSUPPORTED_EVIDENCE_SCHEMA",
                safe_message="Evidence schema version is unsupported.",
            )
        self._schema_version = schema_version

    def build(
        self,
        intent: EvidenceIntent,
        *,
        occurred_at: datetime,
        additional_metadata: MetadataInput = (),
    ) -> QualificationEvidenceRecord:
        """Build one canonical evidence record without persistence or publishing."""

        if not isinstance(intent, EvidenceIntent):
            raise EvidenceValidationError(
                reason_code="INVALID_EVIDENCE_INTENT",
                safe_message="Evidence input must be an EvidenceIntent.",
            )
        occurred_at_text = _normalize_timestamp(occurred_at)
        metadata, redacted_fields = _normalize_metadata(additional_metadata)
        safe_message, message_redactions = _sanitize_message(intent.safe_message)
        redaction = RedactionResult(
            redacted_fields=(*redacted_fields, *message_redactions),
        )
        evidence_type = _evidence_type(intent)
        record_id = _evidence_id(
            schema_version=self._schema_version,
            evidence_type=evidence_type,
            intent=intent,
        )
        partial = QualificationEvidenceRecord(
            schema_version=self._schema_version,
            evidence_id=record_id,
            evidence_type=evidence_type,
            qualification_run_id=intent.qualification_run_id,
            qualification_scenario_id=intent.qualification_scenario_id,
            transition_id=intent.transition_id,
            event_type=intent.event_type.value,
            command_id=intent.command_id,
            correlation_id=intent.correlation_id,
            idempotency_key=intent.idempotency_key,
            source_state=intent.source_state.value,
            destination_state=intent.destination_state.value,
            previous_revision=intent.previous_revision,
            next_revision=intent.next_revision,
            qualification_result=intent.result.value,
            reason_code=intent.reason_code,
            actor_type=intent.actor_type.value,
            environment=_normalize_environment(intent.environment),
            safe_operator_message=safe_message,
            reconciliation_required=intent.reconciliation_required,
            replayed=intent.replayed,
            diagnostic=intent.diagnostic,
            object_reference=_sanitize_optional_identifier(intent.object_reference),
            occurred_at=occurred_at_text,
            metadata=MappingProxyType(metadata),
            redaction=redaction,
            integrity=QualificationEvidenceIntegrity(algorithm="sha256"),
        )
        digest = compute_evidence_digest(partial)
        return replace(
            partial,
            integrity=QualificationEvidenceIntegrity(
                algorithm="sha256",
                digest=digest,
            ),
        )

    def build_many(
        self,
        intents: tuple[EvidenceIntent, ...],
        *,
        occurred_at: datetime,
        additional_metadata: MetadataInput = (),
    ) -> tuple[QualificationEvidenceRecord, ...]:
        """Build records in the same order as supplied intents."""

        return tuple(
            self.build(
                intent,
                occurred_at=occurred_at,
                additional_metadata=additional_metadata,
            )
            for intent in intents
        )


class InMemoryCanonicalQualificationEvidenceRecorder:
    """Port-compatible canonical recorder with no durability claim."""

    def __init__(
        self,
        *,
        adapter: QualificationEvidenceAdapter | None = None,
        occurred_at: datetime,
        metadata: MetadataInput = (),
    ) -> None:
        self._adapter = adapter or QualificationEvidenceAdapter()
        self._occurred_at = occurred_at
        self._metadata = tuple(metadata)
        self._records: dict[str, QualificationEvidenceRecord] = {}
        self._order: list[str] = []
        self.operations: list[str] = []

    @property
    def records(self) -> tuple[QualificationEvidenceRecord, ...]:
        """Return immutable canonical records in deterministic insertion order."""

        return tuple(self._records[evidence_id] for evidence_id in self._order)

    def reset(self) -> None:
        """Clear in-memory records explicitly."""

        self._records.clear()
        self._order.clear()
        self.operations.clear()

    def record(
        self,
        evidence_intents: tuple[EvidenceIntent, ...],
    ) -> tuple[EvidenceRecordReference, ...]:
        """Build and retain canonical records, returning port references."""

        self.operations.append("record_canonical_evidence")
        references: list[EvidenceRecordReference] = []
        for record in self._adapter.build_many(
            evidence_intents,
            occurred_at=self._occurred_at,
            additional_metadata=self._metadata,
        ):
            existing = self._records.get(record.evidence_id)
            if existing is None:
                self._records[record.evidence_id] = record
                self._order.append(record.evidence_id)
            elif serialize_qualification_evidence(existing) != (
                serialize_qualification_evidence(record)
            ):
                raise EvidenceRecordConflictError(
                    reason_code="EVIDENCE_RECORD_CONFLICT",
                    safe_message="Canonical evidence record identity conflicts.",
                )
            references.append(
                EvidenceRecordReference(
                    evidence_id=record.evidence_id,
                    transition_id=record.transition_id,
                    correlation_id=record.correlation_id,
                )
            )
        return tuple(references)


def serialize_qualification_evidence(record: QualificationEvidenceRecord) -> str:
    """Serialize evidence deterministically as compact sorted JSON."""

    try:
        return json.dumps(
            record.to_canonical_dict(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise EvidenceSerializationError(
            reason_code="EVIDENCE_SERIALIZATION_FAILED",
            safe_message="Canonical evidence could not be serialized.",
        ) from error


def compute_evidence_digest(record: QualificationEvidenceRecord) -> str:
    """Return SHA-256 digest over canonical evidence excluding the digest value."""

    try:
        serialized = json.dumps(
            record.to_canonical_dict(include_digest=False),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise EvidenceSerializationError(
            reason_code="EVIDENCE_DIGEST_INPUT_FAILED",
            safe_message="Evidence digest input could not be serialized.",
        ) from error
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def verify_evidence_digest(record: QualificationEvidenceRecord) -> bool:
    """Verify deterministic evidence digest; this is not a digital signature."""

    if record.integrity.digest is None:
        raise EvidenceIntegrityError(
            reason_code="MISSING_EVIDENCE_DIGEST",
            safe_message="Evidence digest is missing.",
        )
    return compute_evidence_digest(record) == record.integrity.digest


def _evidence_type(intent: EvidenceIntent) -> QualificationEvidenceType:
    if intent.reconciliation_required:
        return QualificationEvidenceType.QUALIFICATION_RECONCILIATION_REQUIRED
    if intent.result in {QualificationResult.PASSED, QualificationResult.FAILED}:
        return QualificationEvidenceType.QUALIFICATION_TERMINAL_RESULT
    if intent.diagnostic:
        if intent.reason_code == "IDEMPOTENCY_CONFLICT":
            return QualificationEvidenceType.QUALIFICATION_IDEMPOTENCY_CONFLICT
        if intent.reason_code.startswith("GUARD_"):
            return QualificationEvidenceType.QUALIFICATION_GUARD_FAILED
        return QualificationEvidenceType.QUALIFICATION_TRANSITION_REJECTED
    return QualificationEvidenceType.QUALIFICATION_TRANSITION_ACCEPTED


def _evidence_id(
    *,
    schema_version: str,
    evidence_type: QualificationEvidenceType,
    intent: EvidenceIntent,
) -> str:
    identity = {
        "command_id": intent.command_id,
        "destination_state": intent.destination_state.value,
        "evidence_type": evidence_type.value,
        "next_revision": intent.next_revision,
        "previous_revision": intent.previous_revision,
        "qualification_run_id": intent.qualification_run_id,
        "replayed": intent.replayed,
        "schema_version": schema_version,
        "source_state": intent.source_state.value,
        "transition_id": intent.transition_id,
    }
    serialized = json.dumps(
        identity,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    )
    return f"qe-{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


def _normalize_timestamp(value: datetime) -> str:
    if not isinstance(value, datetime):
        raise EvidenceValidationError(
            reason_code="INVALID_EVIDENCE_TIMESTAMP",
            safe_message="Evidence timestamp must be a datetime.",
        )
    if value.tzinfo is None:
        raise EvidenceValidationError(
            reason_code="NAIVE_EVIDENCE_TIMESTAMP",
            safe_message="Evidence timestamp must be timezone-aware.",
        )
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _normalize_environment(value: str) -> str:
    normalized = value.strip().upper()
    if normalized != "PAPER":
        raise EvidenceValidationError(
            reason_code="UNSUPPORTED_EVIDENCE_ENVIRONMENT",
            safe_message="Only Paper qualification evidence is supported.",
        )
    return normalized


def _sanitize_optional_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    if _looks_like_absolute_path(value):
        raise EvidenceRedactionError(
            reason_code="UNSAFE_EVIDENCE_IDENTIFIER",
            safe_message="Evidence identifier contains a local path.",
        )
    return value


def _normalize_metadata(
    metadata: MetadataInput,
) -> tuple[MappingProxyType[str, MetadataValue], tuple[str, ...]]:
    normalized: dict[str, MetadataValue] = {}
    redacted: list[str] = []
    for key, value in metadata:
        normalized_key = _normalize_metadata_key(key)
        lowered = normalized_key.lower()
        if lowered in _PROHIBITED_METADATA_KEYS:
            raise EvidenceRedactionError(
                reason_code="UNSAFE_EVIDENCE_METADATA",
                safe_message="Evidence metadata contains prohibited raw payload fields.",
            )
        _validate_metadata_value(value)
        if any(term in lowered for term in _SECRET_METADATA_TERMS):
            normalized[normalized_key] = REDACTED_VALUE
            redacted.append(normalized_key)
        else:
            normalized[normalized_key] = _normalize_metadata_value(value)
    return MappingProxyType(dict(sorted(normalized.items()))), tuple(redacted)


def _normalize_metadata_key(key: str) -> str:
    if not isinstance(key, str) or not key.strip():
        raise EvidenceValidationError(
            reason_code="INVALID_METADATA_KEY",
            safe_message="Evidence metadata key cannot be empty.",
        )
    if len(key) > _MAX_METADATA_KEY_LENGTH or any(ord(ch) < 32 for ch in key):
        raise EvidenceValidationError(
            reason_code="INVALID_METADATA_KEY",
            safe_message="Evidence metadata key is not safe.",
        )
    return key.strip().lower()


def _validate_metadata_value(value: object) -> None:
    if isinstance(value, (str, int, bool)) or value is None:
        if isinstance(value, str) and _looks_like_absolute_path(value):
            raise EvidenceRedactionError(
                reason_code="UNSAFE_EVIDENCE_METADATA",
                safe_message="Evidence metadata contains a local path.",
            )
        return
    if isinstance(value, tuple):
        for item in value:
            if not (isinstance(item, (str, int, bool)) or item is None) or isinstance(
                item, bytes
            ):
                raise EvidenceValidationError(
                    reason_code="UNSUPPORTED_METADATA_VALUE",
                    safe_message="Evidence metadata contains unsupported values.",
                )
        return
    raise EvidenceValidationError(
        reason_code="UNSUPPORTED_METADATA_VALUE",
        safe_message="Evidence metadata contains unsupported values.",
    )


def _normalize_metadata_value(value: MetadataValue) -> MetadataValue:
    if isinstance(value, tuple):
        return tuple(value)
    return value


def _metadata_to_dict(
    metadata: MappingProxyType[str, MetadataValue],
) -> dict[str, CanonicalValue]:
    return {
        key: list(value) if isinstance(value, tuple) else value
        for key, value in sorted(metadata.items())
    }


def _sanitize_message(message: str) -> tuple[str, tuple[str, ...]]:
    if not isinstance(message, str) or not message.strip():
        raise EvidenceValidationError(
            reason_code="INVALID_EVIDENCE_MESSAGE",
            safe_message="Evidence safe message cannot be empty.",
        )
    if len(message) > _MAX_MESSAGE_LENGTH or "\n" in message or "\r" in message:
        raise EvidenceRedactionError(
            reason_code="UNSAFE_EVIDENCE_MESSAGE",
            safe_message="Evidence safe message is not audit-safe.",
        )
    if "Traceback" in message or "Authorization:" in message:
        raise EvidenceRedactionError(
            reason_code="UNSAFE_EVIDENCE_MESSAGE",
            safe_message="Evidence safe message contains unsafe diagnostic text.",
        )
    lowered = message.lower()
    if any(marker in lowered for marker in _MESSAGE_SECRET_MARKERS):
        return (REDACTED_VALUE, ("safe_operator_message",))
    return (message, ())


def _looks_like_absolute_path(value: str) -> bool:
    return value.startswith("/") or value.startswith("\\") or value[1:3] == ":\\"
