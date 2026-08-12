"""Paper execution revision identity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from volcanoes.application.execution.errors import PaperExecutionRevisionError


@dataclass(frozen=True, slots=True, order=True)
class PaperExecutionRevision:
    """Optimistic revision for the execution aggregate only."""

    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise PaperExecutionRevisionError(
                "INVALID_EXECUTION_REVISION",
                "Execution revision must be a non-negative integer.",
            )
        if self.value < 0:
            raise PaperExecutionRevisionError(
                "NEGATIVE_EXECUTION_REVISION",
                "Execution revision cannot be negative.",
            )

    @classmethod
    def initial(cls) -> Self:
        """Return the initial execution revision."""

        return cls(0)

    def next(self) -> Self:
        """Return the next immutable execution revision."""

        return type(self)(self.value + 1)

    def to_primitive(self) -> int:
        return self.value

    def __int__(self) -> int:
        return self.value

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.value})"
