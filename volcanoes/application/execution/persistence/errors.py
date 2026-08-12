"""Typed errors for Paper execution persistence contracts."""

from __future__ import annotations

from volcanoes.application.execution.errors import PaperExecutionContractError


class ExecutionPersistenceError(PaperExecutionContractError):
    """Base error for structural persistence-contract misuse."""


class ExecutionPersistenceContractError(ExecutionPersistenceError):
    """Raised when a persistence contract receives invalid structure."""


class ExecutionPersistenceInvariantError(ExecutionPersistenceError):
    """Raised when a persistence contract invariant is violated."""


class ExecutionPersistenceTransactionError(ExecutionPersistenceError):
    """Raised by future adapters for transaction-level infrastructure failure."""
