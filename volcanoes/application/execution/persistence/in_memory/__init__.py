"""Process-local in-memory reference adapter for execution persistence.

This package implements the F5E1A persistence ports with deterministic,
transactional in-memory state. It is non-durable, process-local, and intended
for contract validation only. It is not approved for broker execution and does
not execute, contact, publish, or store outside the adapter instance.
"""

from volcanoes.application.execution.persistence.in_memory.errors import (
    InMemoryCommitInvariantError,
    InMemoryExecutionPersistenceError,
    InMemoryUnitOfWorkClosedError,
    InMemoryUnitOfWorkStateError,
)
from volcanoes.application.execution.persistence.in_memory.repositories import (
    InMemoryExecutionAggregateRepository,
    InMemoryExecutionApprovalRepository,
    InMemoryExecutionBrokerReferenceRepository,
    InMemoryExecutionCommandRepository,
    InMemoryExecutionFailureRepository,
    InMemoryExecutionIdempotencyRepository,
    InMemoryExecutionReceiptRepository,
    InMemoryExecutionReconciliationRepository,
    InMemoryExecutionRestartDiscoveryRepository,
    InMemoryExecutionTransitionJournal,
    InMemoryExecutionDispatchAuthorizationRepository,
    InMemoryExecutionDispatchClaimRepository,
    InMemoryExecutionDispatchControlRepository,
    InMemoryExecutionDispatchResolutionRepository,
)
from volcanoes.application.execution.persistence.in_memory.state import (
    InMemoryExecutionPersistenceState,
)
from volcanoes.application.execution.persistence.in_memory.unit_of_work import (
    InMemoryExecutionPersistence,
    InMemoryExecutionUnitOfWork,
)

__all__ = [
    "InMemoryCommitInvariantError",
    "InMemoryExecutionAggregateRepository",
    "InMemoryExecutionDispatchAuthorizationRepository",
    "InMemoryExecutionDispatchClaimRepository",
    "InMemoryExecutionDispatchControlRepository",
    "InMemoryExecutionDispatchResolutionRepository",
    "InMemoryExecutionApprovalRepository",
    "InMemoryExecutionBrokerReferenceRepository",
    "InMemoryExecutionCommandRepository",
    "InMemoryExecutionFailureRepository",
    "InMemoryExecutionIdempotencyRepository",
    "InMemoryExecutionPersistence",
    "InMemoryExecutionPersistenceError",
    "InMemoryExecutionPersistenceState",
    "InMemoryExecutionReceiptRepository",
    "InMemoryExecutionReconciliationRepository",
    "InMemoryExecutionRestartDiscoveryRepository",
    "InMemoryExecutionTransitionJournal",
    "InMemoryExecutionUnitOfWork",
    "InMemoryUnitOfWorkClosedError",
    "InMemoryUnitOfWorkStateError",
]
