"""Canonical, dependency-free serialization for operational events."""

from __future__ import annotations

import json
from dataclasses import fields
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import TypeAlias

from volcanoes.events.models import DomainEvent

SerializedValue: TypeAlias = (
    str | int | bool | None | list["SerializedValue"] | dict[str, "SerializedValue"]
)


def event_to_dict(event: DomainEvent) -> dict[str, SerializedValue]:
    """Return a canonical primitive representation of one event."""

    if not isinstance(event, DomainEvent):
        raise TypeError("event must be a DomainEvent instance.")

    payload: dict[str, SerializedValue] = {
        "event_type": type(event).__name__,
    }
    for event_field in fields(event):
        payload[event_field.name] = _serialize_value(getattr(event, event_field.name))
    return payload


def serialize_event(event: DomainEvent) -> str:
    """Serialize an event deterministically as compact sorted JSON."""

    return json.dumps(
        event_to_dict(event),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _serialize_value(value: object) -> SerializedValue:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, Enum):
        return _serialize_value(value.value)
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    raise TypeError(f"Unsupported event value: {type(value).__name__}.")
