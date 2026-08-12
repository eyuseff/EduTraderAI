"""Paper execution aggregate identity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from volcanoes.application.execution.identities._base import _FingerprintIdentity


@dataclass(frozen=True, slots=True, repr=False)
class PaperExecutionAggregateId(_FingerprintIdentity):
    """Identity for one logical Paper order lifecycle."""

    prefix: ClassVar[str] = "pea"
