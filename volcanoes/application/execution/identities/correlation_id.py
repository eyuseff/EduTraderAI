"""Paper execution correlation identity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from volcanoes.application.execution.identities._base import _FingerprintIdentity


@dataclass(frozen=True, slots=True, repr=False)
class PaperExecutionCorrelationId(_FingerprintIdentity):
    """Trace identity spanning related Paper execution facts."""

    prefix: ClassVar[str] = "pcr"
