"""Unit-of-work ports for Paper execution persistence contracts."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self, runtime_checkable

from volcanoes.application.execution.persistence.contracts import (
    AggregateSaveResult,
    CommandRegistrationResult,
    ExecutionAggregateRecord,
    ExecutionCommandRecord,
    ExecutionFailureRecord,
    ExecutionIdempotencyRecord,
    ExecutionReceiptRecord,
    ExecutionTransitionRecord,
    IdempotencyReservationResult,
    RecordLoadResult,
    TransitionAppendResult,
    UnitOfWorkCommitResult,
    DispatchOutcomeWriteSet,
)
from volcanoes.application.execution.persistence.ports import (
    ExecutionAggregateRepository,
    ExecutionApprovalRepository,
    ExecutionBrokerReferenceRepository,
    ExecutionCommandRepository,
    ExecutionFailureRepository,
    ExecutionIdempotencyRepository,
    ExecutionReceiptRepository,
    ExecutionReconciliationRepository,
    ExecutionRestartDiscoveryRepository,
    ExecutionTransitionJournal,
    ExecutionDispatchAuthorizationRepository,
    ExecutionDispatchClaimRepository,
    ExecutionDispatchControlRepository,
    ExecutionDispatchResolutionRepository,
)
from volcanoes.application.execution.identities import PaperExecutionRevision


@runtime_checkable
class ExecutionUnitOfWork(Protocol):
    """Explicit transaction-owner contract for execution persistence."""

    aggregates: ExecutionAggregateRepository
    commands: ExecutionCommandRepository
    idempotency: ExecutionIdempotencyRepository
    transitions: ExecutionTransitionJournal
    broker_references: ExecutionBrokerReferenceRepository
    receipts: ExecutionReceiptRepository
    failures: ExecutionFailureRepository
    approvals: ExecutionApprovalRepository
    reconciliations: ExecutionReconciliationRepository
    restart_discovery: ExecutionRestartDiscoveryRepository
    dispatch_control: ExecutionDispatchControlRepository
    dispatch_claims: ExecutionDispatchClaimRepository
    dispatch_authorizations: ExecutionDispatchAuthorizationRepository
    dispatch_resolutions: ExecutionDispatchResolutionRepository

    def __enter__(self) -> Self:
        """Enter an explicit unit-of-work scope without committing."""

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Leave the scope; implementations must not hide an automatic commit."""

    def commit(self) -> UnitOfWorkCommitResult:
        """Commit explicit local transaction work."""

    def rollback(self) -> None:
        """Roll back explicit local transaction work."""

    def record_dispatch_outcome(
        self, write_set: DispatchOutcomeWriteSet
    ) -> RecordLoadResult:
        """Validate and stage one complete dispatch outcome write set."""


@runtime_checkable
class ExecutionPersistenceSession(Protocol):
    """Small atomic-operation surface for future command intake."""

    def register_command(
        self,
        command: ExecutionCommandRecord,
    ) -> CommandRegistrationResult:
        """Register a command without embedding lifecycle decisions."""

    def reserve_idempotency(
        self,
        reservation: ExecutionIdempotencyRecord,
    ) -> IdempotencyReservationResult:
        """Reserve a logical operation before any dispatch boundary."""

    def load_aggregate(
        self,
        aggregate: ExecutionAggregateRecord,
    ) -> RecordLoadResult:
        """Load the current aggregate reference."""

    def append_transition(
        self,
        transition: ExecutionTransitionRecord,
    ) -> TransitionAppendResult:
        """Append an accepted transition record."""

    def save_aggregate(
        self,
        aggregate: ExecutionAggregateRecord,
        *,
        expected_revision: PaperExecutionRevision,
    ) -> AggregateSaveResult:
        """Save aggregate state with exact expected revision."""

    def record_receipt(
        self,
        receipt: ExecutionReceiptRecord,
    ) -> RecordLoadResult:
        """Record a normalized receipt snapshot."""

    def record_failure(
        self,
        failure: ExecutionFailureRecord,
    ) -> RecordLoadResult:
        """Record a normalized failure snapshot."""
