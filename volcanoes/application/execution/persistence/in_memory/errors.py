"""Narrow errors for the process-local in-memory execution persistence adapter."""

from __future__ import annotations

from volcanoes.application.execution.persistence.errors import (
    ExecutionPersistenceTransactionError,
)


class InMemoryExecutionPersistenceError(ExecutionPersistenceTransactionError):
    """Base error for the in-memory reference adapter."""


class InMemoryUnitOfWorkClosedError(InMemoryExecutionPersistenceError):
    """Raised when a closed unit of work receives another operation."""


class InMemoryUnitOfWorkStateError(InMemoryExecutionPersistenceError):
    """Raised when unit-of-work lifecycle rules are violated."""


class InMemoryCommitInvariantError(InMemoryExecutionPersistenceError):
    """Raised for adapter invariant defects, not expected business conflicts."""


__all__ = [
    "InMemoryCommitInvariantError",
    "InMemoryExecutionPersistenceError",
    "InMemoryUnitOfWorkClosedError",
    "InMemoryUnitOfWorkStateError",
]
