"""Central deterministic serialization for Paper execution contracts."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import is_dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from volcanoes.application.execution.errors import (
    PaperExecutionSerializationError,
)

Primitive = (
    str
    | int
    | bool
    | None
    | tuple["Primitive", ...]
    | tuple[tuple[str, "Primitive"], ...]
)


def normalize_text(value: str, field_name: str = "text") -> str:
    """Normalize non-empty text with stable Unicode representation."""

    if not isinstance(value, str):
        raise PaperExecutionSerializationError(
            "INVALID_TEXT",
            f"{field_name} must be text.",
        )
    normalized = unicodedata.normalize("NFC", value.strip())
    if not normalized:
        raise PaperExecutionSerializationError(
            "EMPTY_TEXT",
            f"{field_name} cannot be empty.",
        )
    return normalized


def normalize_decimal(value: Decimal, field_name: str = "decimal") -> str:
    """Return a stable JSON-safe decimal string."""

    if not isinstance(value, Decimal):
        raise PaperExecutionSerializationError(
            "INVALID_DECIMAL",
            f"{field_name} must be a Decimal.",
        )
    if value.is_nan() or value.is_infinite():
        raise PaperExecutionSerializationError(
            "NON_FINITE_DECIMAL",
            f"{field_name} must be finite.",
        )
    try:
        normalized = value.normalize()
    except InvalidOperation as error:
        raise PaperExecutionSerializationError(
            "INVALID_DECIMAL",
            f"{field_name} cannot be normalized.",
        ) from error
    if normalized == Decimal("-0"):
        normalized = Decimal("0")
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def normalize_datetime(value: datetime, field_name: str = "datetime") -> str:
    """Return a stable UTC ISO-8601 timestamp."""

    if not isinstance(value, datetime):
        raise PaperExecutionSerializationError(
            "INVALID_DATETIME",
            f"{field_name} must be a datetime.",
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise PaperExecutionSerializationError(
            "NAIVE_DATETIME",
            f"{field_name} must be timezone-aware.",
        )
    return (
        value.astimezone(UTC)
        .isoformat(timespec="microseconds")
        .replace(
            "+00:00",
            "Z",
        )
    )


def canonicalize(value: Any) -> Any:
    """Convert supported values into deterministic JSON-safe primitives."""

    if value is None or isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        raise PaperExecutionSerializationError(
            "FLOAT_UNSUPPORTED",
            "Floats are not accepted in execution contracts.",
        )
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, Decimal):
        return normalize_decimal(value)
    if isinstance(value, datetime):
        return normalize_datetime(value)
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "to_primitive") and callable(value.to_primitive):
        return canonicalize(value.to_primitive())
    if is_dataclass(value):
        raise PaperExecutionSerializationError(
            "DATACLASS_WITHOUT_PRIMITIVE",
            "Dataclasses must expose to_primitive for canonical execution output.",
        )
    if isinstance(value, tuple | list):
        return tuple(canonicalize(item) for item in value)
    if isinstance(value, frozenset | set):
        raise PaperExecutionSerializationError(
            "SET_UNSUPPORTED",
            "Sets are not accepted because ordering is nondeterministic.",
        )
    if isinstance(value, dict):
        normalized_items: list[tuple[str, Any]] = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise PaperExecutionSerializationError(
                    "NON_TEXT_MAPPING_KEY",
                    "Canonical mapping keys must be text.",
                )
            normalized_items.append((unicodedata.normalize("NFC", key), item))
        return {
            key: canonicalize(item)
            for key, item in sorted(normalized_items, key=lambda entry: entry[0])
        }
    raise PaperExecutionSerializationError(
        "UNSUPPORTED_CANONICAL_TYPE",
        f"Unsupported canonical value type: {type(value).__name__}.",
    )


def canonical_json_text(value: Any) -> str:
    """Return deterministic compact JSON text."""

    return json.dumps(
        canonicalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes."""

    return canonical_json_text(value).encode("utf-8")
