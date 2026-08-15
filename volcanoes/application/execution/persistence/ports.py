"""Repository ports for Paper execution persistence contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from volcanoes.application.execution.identities import (
    PaperBrokerOrderReference,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionIdempotencyKey,
    PaperExecutionRevision,
)
from volcanoes.application.execution.persistence.contracts import (
    AggregateSaveResult,
    CommandRegistrationResult,
    ExecutionAggregateRecord,
    ExecutionApprovalRecord,
    ExecutionBrokerReferenceRecord,
    ExecutionCommandRecord,
    ExecutionFailureRecord,
    ExecutionIdempotencyRecord,
    ExecutionReceiptRecord,
    ExecutionReconciliationRecord,
    ExecutionRestartDiscoveryQuery,
    ExecutionTransitionRecord,
    IdempotencyReservationResult,
    RecordLoadResult,
    ReplayLookupResult,
    RestartDiscoveryResult,
    TransitionAppendResult,
    DispatchClaimResult,
    ExecutionDispatchClaimAttempt,
    ExecutionDispatchAuthorizationRecord,
    ExecutionDispatchClaimRecord,
    ExecutionDispatchControlRecord,
    ExecutionDispatchResolutionRecord,
)


@runtime_checkable
class ExecutionAggregateRepository(Protocol):
    """Storage-neutral aggregate repository contract."""

    def get(self, aggregate_id: PaperExecutionAggregateId) -> RecordLoadResult:
        """Return a load result for one aggregate identity."""

    def load_record(
        self, aggregate_id: PaperExecutionAggregateId
    ) -> ExecutionAggregateRecord | None:
        """Load the immutable aggregate required for coordinated CAS updates."""

    def save(
        self,
        record: ExecutionAggregateRecord,
        *,
        expected_revision: PaperExecutionRevision,
    ) -> AggregateSaveResult:
        """Save a materialized aggregate with explicit revision checking."""


@runtime_checkable
class ExecutionCommandRepository(Protocol):
    """Storage-neutral command repository contract."""

    def get(self, command_id: PaperExecutionCommandId) -> RecordLoadResult:
        """Return a load result for one command identity."""

    def register(
        self,
        record: ExecutionCommandRecord,
    ) -> CommandRegistrationResult:
        """Register an immutable command record or return replay/conflict data."""

    def lookup_replay(
        self,
        command_id: PaperExecutionCommandId,
        payload_fingerprint: str,
    ) -> ReplayLookupResult:
        """Return deterministic exact replay or conflict status."""


@runtime_checkable
class ExecutionIdempotencyRepository(Protocol):
    """Storage-neutral idempotency repository contract."""

    def get(self, key: PaperExecutionIdempotencyKey) -> RecordLoadResult:
        """Return a load result for one idempotency key."""

    def reserve(
        self,
        record: ExecutionIdempotencyRecord,
    ) -> IdempotencyReservationResult:
        """Reserve a logical operation or return replay/conflict data."""


@runtime_checkable
class ExecutionTransitionJournal(Protocol):
    """Append-only transition journal contract."""

    def append(
        self,
        record: ExecutionTransitionRecord,
    ) -> TransitionAppendResult:
        """Append one accepted lifecycle transition record."""


@runtime_checkable
class ExecutionBrokerReferenceRepository(Protocol):
    """Broker-reference repository with one active reference per aggregate."""

    def get(
        self,
        reference: PaperBrokerOrderReference,
    ) -> RecordLoadResult:
        """Return a load result for one normalized broker reference."""

    def register(
        self,
        record: ExecutionBrokerReferenceRecord,
    ) -> RecordLoadResult:
        """Register or locate a normalized broker reference."""


@runtime_checkable
class ExecutionReceiptRepository(Protocol):
    """Receipt repository keyed by the embedded receipt fingerprint."""

    def record(self, receipt: ExecutionReceiptRecord) -> RecordLoadResult:
        """Record one normalized receipt snapshot."""


@runtime_checkable
class ExecutionFailureRepository(Protocol):
    """Failure repository keyed by the embedded failure fingerprint."""

    def record(self, failure: ExecutionFailureRecord) -> RecordLoadResult:
        """Record one normalized failure snapshot."""


@runtime_checkable
class ExecutionApprovalRepository(Protocol):
    """Storage-neutral approval repository contract."""

    def record(self, approval: ExecutionApprovalRecord) -> RecordLoadResult:
        """Record one approval reference."""


@runtime_checkable
class ExecutionReconciliationRepository(Protocol):
    """Storage-neutral reconciliation repository contract."""

    def record(
        self,
        reconciliation: ExecutionReconciliationRecord,
    ) -> RecordLoadResult:
        """Record one reconciliation fact."""


@runtime_checkable
class ExecutionRestartDiscoveryRepository(Protocol):
    """Identity-ordered restart discovery with filter-bound opaque cursors."""

    def discover(
        self,
        query: ExecutionRestartDiscoveryQuery,
    ) -> RestartDiscoveryResult:
        """Return a page; invalid or cross-filter cursors restart at page one."""


@runtime_checkable
class ExecutionDispatchControlRepository(Protocol):
    def get(self) -> ExecutionDispatchControlRecord: ...
    def save(
        self, record: ExecutionDispatchControlRecord, *, expected_generation: int
    ) -> RecordLoadResult: ...


@runtime_checkable
class ExecutionDispatchClaimRepository(Protocol):
    def get(self, claim_token: str) -> ExecutionDispatchClaimRecord | None: ...
    def acquire(
        self, attempt: ExecutionDispatchClaimAttempt, *, claimed_at: datetime
    ) -> DispatchClaimResult: ...


@runtime_checkable
class ExecutionDispatchAuthorizationRepository(Protocol):
    def get(self, claim_token: str) -> ExecutionDispatchAuthorizationRecord | None: ...
    def record(
        self, record: ExecutionDispatchAuthorizationRecord
    ) -> RecordLoadResult: ...


@runtime_checkable
class ExecutionDispatchResolutionRepository(Protocol):
    def get(self, claim_token: str) -> ExecutionDispatchResolutionRecord | None: ...
    def record(self, record: ExecutionDispatchResolutionRecord) -> RecordLoadResult: ...
