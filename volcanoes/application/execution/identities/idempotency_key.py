"""Paper execution idempotency identity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from volcanoes.application.execution.identities._base import _FingerprintIdentity


@dataclass(frozen=True, slots=True, repr=False)
class PaperExecutionIdempotencyKey(_FingerprintIdentity):
    """Identity for one logical state-changing Paper execution operation."""

    prefix: ClassVar[str] = "pik"
