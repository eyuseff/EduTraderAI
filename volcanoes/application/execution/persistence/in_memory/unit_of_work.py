"""Transactional unit of work for the process-local in-memory adapter.

This reference implementation stores only in memory. It does not survive adapter
disposal or process restart, is not safe across multiple processes, and is not
a production execution source of truth. It exists to validate persistence
contracts without executing or contacting anything.
"""

from __future__ import annotations

from types import TracebackType
from typing import Self

from volcanoes.application.execution.identities import PaperExecutionRevision
from volcanoes.application.execution.persistence.contracts import (
    AggregateSaveResult,
    CommandRegistrationResult,
    ExecutionAggregateRecord,
    ExecutionApprovalRecord,
    ExecutionBrokerReferenceRecord,
    ExecutionCommandRecord,
    ExecutionFailureRecord,
    ExecutionIdempotencyRecord,
    ExecutionPersistenceConflict,
    ExecutionReceiptRecord,
    ExecutionReconciliationRecord,
    ExecutionTransitionRecord,
    IdempotencyReservationResult,
    RecordLoadResult,
    TransitionAppendResult,
    UnitOfWorkCommitResult,
)
from volcanoes.application.execution.persistence.enums import (
    ExecutionPersistenceConflictKind,
    ExecutionPersistenceResultStatus,
)
from volcanoes.application.execution.persistence.in_memory.errors import (
    InMemoryUnitOfWorkClosedError,
)
from volcanoes.application.execution.persistence.in_memory.repositories import (
    SCHEMA_VERSION,
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
    _aggregate_save_result,
    _command_registration_result,
    _idempotency_result,
    _record_result_for_unique_identity,
    _transition_result,
)
from volcanoes.application.execution.persistence.in_memory.state import (
    InMemoryExecutionPersistenceState,
)


class InMemoryExecutionUnitOfWork:
    """Deterministic process-local transaction over one state container."""

    def __init__(self, state: InMemoryExecutionPersistenceState) -> None:
        self._base_state = state
        self.transaction_state = state.snapshot()
        self._closed = False
        self._committed = False
        self._rolled_back = False
        self._staged_aggregate_saves: list[
            tuple[ExecutionAggregateRecord, PaperExecutionRevision]
        ] = []
        self._staged_commands: list[ExecutionCommandRecord] = []
        self._staged_idempotency: list[ExecutionIdempotencyRecord] = []
        self._staged_transitions: list[ExecutionTransitionRecord] = []
        self._staged_broker_references: list[ExecutionBrokerReferenceRecord] = []
        self._staged_receipts: list[ExecutionReceiptRecord] = []
        self._staged_failures: list[ExecutionFailureRecord] = []
        self._staged_approvals: list[ExecutionApprovalRecord] = []
        self._staged_reconciliations: list[ExecutionReconciliationRecord] = []
        self._blocking_conflict: ExecutionPersistenceConflict | None = None

        self.aggregates = InMemoryExecutionAggregateRepository(self)
        self.commands = InMemoryExecutionCommandRepository(self)
        self.idempotency = InMemoryExecutionIdempotencyRepository(self)
        self.transitions = InMemoryExecutionTransitionJournal(self)
        self.broker_references = InMemoryExecutionBrokerReferenceRepository(self)
        self.receipts = InMemoryExecutionReceiptRepository(self)
        self.failures = InMemoryExecutionFailureRepository(self)
        self.approvals = InMemoryExecutionApprovalRepository(self)
        self.reconciliations = InMemoryExecutionReconciliationRepository(self)
        self.restart_discovery = InMemoryExecutionRestartDiscoveryRepository(self)

    def __enter__(self) -> Self:
        self.ensure_active()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None and not self._closed:
            self.rollback()
        elif not self._closed:
            self.rollback()

    def ensure_active(self) -> None:
        if self._closed:
            raise InMemoryUnitOfWorkClosedError(
                "UNIT_OF_WORK_CLOSED",
                "In-memory unit of work is already closed.",
            )

    def stage_conflict(self, conflict: ExecutionPersistenceConflict) -> None:
        if self._blocking_conflict is None:
            self._blocking_conflict = conflict

    def stage_aggregate_save(
        self,
        record: ExecutionAggregateRecord,
        expected_revision: PaperExecutionRevision,
    ) -> None:
        self._staged_aggregate_saves.append((record, expected_revision))

    def stage_command(self, record: ExecutionCommandRecord) -> None:
        self._staged_commands.append(record)

    def stage_idempotency(self, record: ExecutionIdempotencyRecord) -> None:
        self._staged_idempotency.append(record)

    def stage_transition(self, record: ExecutionTransitionRecord) -> None:
        self._staged_transitions.append(record)

    def stage_broker_reference(self, record: ExecutionBrokerReferenceRecord) -> None:
        self._staged_broker_references.append(record)

    def stage_receipt(self, record: ExecutionReceiptRecord) -> None:
        self._staged_receipts.append(record)

    def stage_failure(self, record: ExecutionFailureRecord) -> None:
        self._staged_failures.append(record)

    def stage_approval(self, record: ExecutionApprovalRecord) -> None:
        self._staged_approvals.append(record)

    def stage_reconciliation(self, record: ExecutionReconciliationRecord) -> None:
        self._staged_reconciliations.append(record)

    def commit(self) -> UnitOfWorkCommitResult:
        if self._committed:
            return UnitOfWorkCommitResult(
                status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
                committed=False,
                schema_version=SCHEMA_VERSION,
            )
        self.ensure_active()
        validation_state = self._base_state.snapshot()
        conflict = self._blocking_conflict or self._validate_and_apply(validation_state)
        if conflict is not None:
            self._closed = True
            self._rolled_back = True
            return UnitOfWorkCommitResult(
                status=_status_for_conflict(conflict),
                committed=False,
                conflict=conflict,
                schema_version=SCHEMA_VERSION,
            )
        self._base_state.replace_from(validation_state)
        self._closed = True
        self._committed = True
        return UnitOfWorkCommitResult(
            status=ExecutionPersistenceResultStatus.SAVED,
            committed=True,
            schema_version=SCHEMA_VERSION,
        )

    def rollback(self) -> None:
        if self._committed:
            return
        if self._rolled_back:
            return
        self.transaction_state = self._base_state.snapshot()
        self._closed = True
        self._rolled_back = True

    def register_command(
        self,
        command: ExecutionCommandRecord,
    ) -> CommandRegistrationResult:
        return self.commands.register(command)

    def reserve_idempotency(
        self,
        reservation: ExecutionIdempotencyRecord,
    ) -> IdempotencyReservationResult:
        return self.idempotency.reserve(reservation)

    def load_aggregate(
        self,
        aggregate: ExecutionAggregateRecord,
    ) -> RecordLoadResult:
        return self.aggregates.get(aggregate.aggregate_id)

    def append_transition(
        self,
        transition: ExecutionTransitionRecord,
    ) -> TransitionAppendResult:
        return self.transitions.append(transition)

    def save_aggregate(
        self,
        aggregate: ExecutionAggregateRecord,
        *,
        expected_revision: PaperExecutionRevision,
    ) -> AggregateSaveResult:
        return self.aggregates.save(
            aggregate,
            expected_revision=expected_revision,
        )

    def record_receipt(self, receipt: ExecutionReceiptRecord) -> RecordLoadResult:
        return self.receipts.record(receipt)

    def record_failure(self, failure: ExecutionFailureRecord) -> RecordLoadResult:
        return self.failures.record(failure)

    def _validate_and_apply(
        self,
        validation_state: InMemoryExecutionPersistenceState,
    ) -> ExecutionPersistenceConflict | None:
        for command in self._staged_commands:
            command_result = _command_registration_result(
                command,
                validation_state._commands.get(command.command_id),
            )
            if command_result.conflict is not None:
                return command_result.conflict
            if command_result.status is ExecutionPersistenceResultStatus.CREATED:
                validation_state._commands[command.command_id] = command

        for reservation in self._staged_idempotency:
            reservation_result = _idempotency_result(
                reservation,
                validation_state._idempotency.get(reservation.idempotency_key),
            )
            if reservation_result.conflict is not None:
                return reservation_result.conflict
            if reservation_result.status is ExecutionPersistenceResultStatus.CREATED:
                validation_state._idempotency[reservation.idempotency_key] = reservation

        for aggregate, expected_revision in self._staged_aggregate_saves:
            aggregate_result = _aggregate_save_result(
                aggregate,
                validation_state._aggregates.get(aggregate.aggregate_id),
                expected_revision,
            )
            if aggregate_result.conflict is not None:
                return aggregate_result.conflict
            if aggregate_result.status in {
                ExecutionPersistenceResultStatus.CREATED,
                ExecutionPersistenceResultStatus.SAVED,
            }:
                validation_state._aggregates[aggregate.aggregate_id] = aggregate

        for transition in self._staged_transitions:
            transition_result = _transition_result(
                transition,
                validation_state._transitions_by_id.get(
                    transition.transition_record_id
                ),
            )
            if transition_result.conflict is not None:
                return transition_result.conflict
            if transition_result.status is ExecutionPersistenceResultStatus.APPENDED:
                validation_state._transitions_by_id[transition.transition_record_id] = (
                    transition
                )
                validation_state._transition_order = (
                    *validation_state._transition_order,
                    transition.transition_record_id,
                )

        for reference in self._staged_broker_references:
            existing = validation_state._broker_references.get(
                reference.broker_reference
            )
            broker_reference_result = _record_result_for_unique_identity(
                reference.record_fingerprint,
                existing.record_fingerprint if existing is not None else None,
                conflict_kind=ExecutionPersistenceConflictKind.BROKER_REFERENCE_CONFLICT,
                conflict_status=ExecutionPersistenceResultStatus.DUPLICATE_BROKER_REFERENCE,
                code="BROKER_REFERENCE_CONFLICT",
                safe_message="Broker reference is already bound to another record.",
                aggregate_id=reference.aggregate_id,
                command_id=reference.command_id,
            )
            if broker_reference_result.conflict is not None:
                return broker_reference_result.conflict
            if (
                broker_reference_result.status
                is ExecutionPersistenceResultStatus.CREATED
            ):
                validation_state._broker_references[reference.broker_reference] = (
                    reference
                )

        for receipt in self._staged_receipts:
            if receipt.record_fingerprint not in validation_state._receipts:
                validation_state._receipts[receipt.record_fingerprint] = receipt

        for failure in self._staged_failures:
            if failure.record_fingerprint not in validation_state._failures:
                validation_state._failures[failure.record_fingerprint] = failure

        for approval in self._staged_approvals:
            existing_approval = validation_state._approvals.get(
                approval.approval_fingerprint
            )
            approval_result = _record_result_for_unique_identity(
                approval.record_fingerprint,
                (
                    existing_approval.record_fingerprint
                    if existing_approval is not None
                    else None
                ),
                conflict_kind=ExecutionPersistenceConflictKind.RECORD_VERSION_CONFLICT,
                conflict_status=ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
                code="APPROVAL_CONFLICT",
                safe_message="Approval identity already exists with different content.",
            )
            if approval_result.conflict is not None:
                return approval_result.conflict
            if approval_result.status is ExecutionPersistenceResultStatus.CREATED:
                validation_state._approvals[approval.approval_fingerprint] = approval

        for reconciliation in self._staged_reconciliations:
            existing_reconciliation = validation_state._reconciliations.get(
                reconciliation.reconciliation_id
            )
            reconciliation_result = _record_result_for_unique_identity(
                reconciliation.record_fingerprint,
                (
                    existing_reconciliation.record_fingerprint
                    if existing_reconciliation is not None
                    else None
                ),
                conflict_kind=ExecutionPersistenceConflictKind.RECORD_VERSION_CONFLICT,
                conflict_status=ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
                code="RECONCILIATION_CONFLICT",
                safe_message="Reconciliation identity already exists with different content.",
                aggregate_id=reconciliation.aggregate_id,
            )
            if reconciliation_result.conflict is not None:
                return reconciliation_result.conflict
            if reconciliation_result.status is ExecutionPersistenceResultStatus.CREATED:
                validation_state._reconciliations[reconciliation.reconciliation_id] = (
                    reconciliation
                )

        return None


def _status_for_conflict(
    conflict: ExecutionPersistenceConflict,
) -> ExecutionPersistenceResultStatus:
    if conflict.kind is ExecutionPersistenceConflictKind.STALE_REVISION:
        return ExecutionPersistenceResultStatus.STALE_REVISION
    if conflict.kind is ExecutionPersistenceConflictKind.COMMAND_PAYLOAD_CONFLICT:
        return ExecutionPersistenceResultStatus.COMMAND_CONFLICT
    if conflict.kind is ExecutionPersistenceConflictKind.IDEMPOTENCY_PAYLOAD_CONFLICT:
        return ExecutionPersistenceResultStatus.IDEMPOTENCY_CONFLICT
    if conflict.kind is ExecutionPersistenceConflictKind.BROKER_REFERENCE_CONFLICT:
        return ExecutionPersistenceResultStatus.DUPLICATE_BROKER_REFERENCE
    return ExecutionPersistenceResultStatus.TRANSACTION_ABORTED


class InMemoryExecutionPersistence:
    """Factory for isolated in-memory execution persistence units of work."""

    def __init__(self) -> None:
        self._state = InMemoryExecutionPersistenceState()

    def unit_of_work(self) -> InMemoryExecutionUnitOfWork:
        return InMemoryExecutionUnitOfWork(self._state)

    def snapshot(self) -> InMemoryExecutionPersistenceState:
        """Return an isolated state copy for deterministic test inspection."""

        return self._state.snapshot()


__all__ = [
    "InMemoryExecutionPersistence",
    "InMemoryExecutionUnitOfWork",
]
