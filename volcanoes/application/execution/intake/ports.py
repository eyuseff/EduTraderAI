"""Application ports for transactional execution intake."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from volcanoes.application.execution.persistence import ExecutionUnitOfWork


@runtime_checkable
class ExecutionUnitOfWorkProvider(Protocol):
    """Provide a fresh short-lived execution unit of work."""

    def unit_of_work(self) -> ExecutionUnitOfWork:
        """Return a unit of work without starting external effects."""
