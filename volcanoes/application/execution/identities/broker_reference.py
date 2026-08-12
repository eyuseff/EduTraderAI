"""Paper broker order reference."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from volcanoes.application.execution.identities._base import _FingerprintIdentity


@dataclass(frozen=True, slots=True, repr=False)
class PaperBrokerOrderReference(_FingerprintIdentity):
    """Redacted normalized reference to an opaque broker Paper order."""

    prefix: ClassVar[str] = "pbr"
