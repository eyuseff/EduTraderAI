"""Narrow storage-neutral and effect ports for controlled Paper submission."""

from __future__ import annotations

from typing import Protocol

from volcanoes.application.execution.persistence import ExecutionUnitOfWork
from volcanoes.application.execution.submission.contracts import (
    ControlledPaperOrder,
    PaperDispatchFailure,
    PaperDispatchObservation,
)


class DispatchClaimUnitOfWorkProvider(Protocol):
    def unit_of_work(self) -> ExecutionUnitOfWork: ...


class OneShotPaperDispatchBoundary(Protocol):
    def __call__(
        self, order: ControlledPaperOrder
    ) -> PaperDispatchObservation | PaperDispatchFailure: ...
