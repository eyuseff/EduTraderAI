"""Shared identity validation for Paper execution value objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Self

from volcanoes.application.execution.fingerprints import (
    fingerprint_payload,
    validate_fingerprint,
)


@dataclass(frozen=True, slots=True)
class _FingerprintIdentity:
    """Immutable prefixed SHA-256 identity base."""

    value: str

    prefix: ClassVar[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", validate_fingerprint(self.value, self.prefix))

    @classmethod
    def from_seed(cls, *parts: object) -> Self:
        """Build a deterministic identity from safe canonical seed parts."""

        return cls(fingerprint_payload(cls.prefix, parts))

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.value!r})"

    def to_primitive(self) -> str:
        return self.value
