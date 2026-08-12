"""Validation helpers for immutable Paper execution contracts."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TypeAlias

from volcanoes.application.execution._canonical import (
    normalize_datetime,
    normalize_decimal,
    normalize_text,
)
from volcanoes.application.execution.errors import (
    PaperExecutionInvariantError,
    PaperExecutionSerializationError,
)

MetadataScalar: TypeAlias = str | int | bool | None
MetadataValue: TypeAlias = MetadataScalar | tuple[MetadataScalar, ...]
SafeMetadata: TypeAlias = tuple[tuple[str, MetadataValue], ...]

SENSITIVE_TERMS = (
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "authorization",
    "auth_header",
    "cookie",
    "private_key",
    "session_token",
    "bearer",
    "client_secret",
)


def normalize_code(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise PaperExecutionInvariantError(
            "INVALID_CODE",
            f"{field_name} must be text.",
        )
    text = normalize_text(value, field_name).upper()
    if not re.fullmatch(r"[A-Z0-9_:-]{1,80}", text):
        raise PaperExecutionInvariantError(
            "INVALID_CODE",
            f"{field_name} contains unsupported characters.",
        )
    return text


def normalize_alias(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise PaperExecutionInvariantError(
            "INVALID_ALIAS",
            f"{field_name} must be text.",
        )
    try:
        text = normalize_text(value, field_name)
    except PaperExecutionSerializationError as error:
        raise PaperExecutionInvariantError(
            error.reason_code,
            error.safe_message,
        ) from error
    if len(text) > 120 or not re.fullmatch(r"[A-Za-z0-9_.:@/-]+", text):
        raise PaperExecutionInvariantError(
            "INVALID_ALIAS",
            f"{field_name} contains unsupported characters.",
        )
    _reject_sensitive_text(text, field_name)
    return text


def normalize_symbol(value: str) -> str:
    try:
        text = normalize_text(value, "symbol").upper()
    except PaperExecutionSerializationError as error:
        raise PaperExecutionInvariantError(
            error.reason_code,
            error.safe_message,
        ) from error
    if len(text) > 16 or not re.fullmatch(r"[A-Z][A-Z0-9.:-]{0,15}", text):
        raise PaperExecutionInvariantError(
            "INVALID_SYMBOL",
            "Symbol contains unsupported characters.",
        )
    return text


def require_decimal(value: Decimal, field_name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise PaperExecutionInvariantError(
            "INVALID_DECIMAL",
            f"{field_name} must be a Decimal.",
        )
    try:
        normalize_decimal(value, field_name)
    except PaperExecutionSerializationError as error:
        raise PaperExecutionInvariantError(
            error.reason_code,
            error.safe_message,
        ) from error
    return value


def require_positive_decimal(value: Decimal, field_name: str) -> Decimal:
    decimal_value = require_decimal(value, field_name)
    if decimal_value <= Decimal("0"):
        raise PaperExecutionInvariantError(
            "NON_POSITIVE_DECIMAL",
            f"{field_name} must be positive.",
        )
    return decimal_value


def require_datetime(value: datetime, field_name: str) -> datetime:
    normalize_datetime(value, field_name)
    return value


def normalize_metadata(metadata: SafeMetadata) -> SafeMetadata:
    if not isinstance(metadata, tuple):
        raise PaperExecutionInvariantError(
            "INVALID_METADATA",
            "Metadata must be an immutable tuple.",
        )
    normalized: list[tuple[str, MetadataValue]] = []
    seen: set[str] = set()
    for key, value in metadata:
        normalized_key = normalize_alias(key, "metadata key")
        lower_key = normalized_key.lower()
        if lower_key in seen:
            raise PaperExecutionInvariantError(
                "DUPLICATE_METADATA_KEY",
                "Metadata keys must be unique.",
            )
        seen.add(lower_key)
        if _contains_sensitive(lower_key):
            raise PaperExecutionInvariantError(
                "SENSITIVE_METADATA_KEY",
                "Metadata key is sensitive.",
            )
        normalized.append((normalized_key, _normalize_metadata_value(value)))
    return tuple(sorted(normalized, key=lambda item: item[0]))


def validate_no_sensitive_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise PaperExecutionInvariantError(
            "INVALID_SAFE_TEXT",
            f"{field_name} must be text.",
        )
    text = unicodedata.normalize("NFC", value)
    _reject_sensitive_text(text, field_name)
    return text


def enum_values(values: tuple[Enum, ...]) -> tuple[str, ...]:
    return tuple(value.value for value in values)


def _normalize_metadata_value(value: MetadataValue) -> MetadataValue:
    if isinstance(value, tuple):
        return tuple(_normalize_metadata_scalar(item) for item in value)
    return _normalize_metadata_scalar(value)


def _normalize_metadata_scalar(value: MetadataScalar) -> MetadataScalar:
    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, str):
        normalized = normalize_text(value, "metadata value")
        _reject_sensitive_text(normalized, "metadata value")
        return normalized
    raise PaperExecutionInvariantError(
        "INVALID_METADATA_VALUE",
        "Metadata value must be a primitive immutable value.",
    )


def _reject_sensitive_text(value: str, field_name: str) -> None:
    if _contains_sensitive(value.lower()):
        raise PaperExecutionInvariantError(
            "SENSITIVE_TEXT",
            f"{field_name} cannot contain sensitive terms.",
        )


def _contains_sensitive(value: str) -> bool:
    return any(term in value for term in SENSITIVE_TERMS)
