"""Paper execution command identity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from volcanoes.application.execution.identities._base import _FingerprintIdentity


@dataclass(frozen=True, slots=True, repr=False)
class PaperExecutionCommandId(_FingerprintIdentity):
    """Identity for one immutable command envelope."""

    prefix: ClassVar[str] = "pec"
