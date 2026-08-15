"""Transactional unit of work for the process-local in-memory adapter.

This reference implementation stores only in memory. It does not survive adapter
disposal or process restart, is not safe across multiple processes, and is not
a production execution source of truth. It exists to validate persistence
contracts without executing or contacting anything.
"""

from __future__ import annotations

from _thread import LockType, allocate_lock
from dataclasses import replace
import json
from types import TracebackType
from typing import Self

from volcanoes.application.execution.identities import PaperExecutionRevision
from volcanoes.application.execution._canonical import canonical_json_text
from volcanoes.application.execution.fingerprints import (
    command_payload_fingerprint,
    fingerprint_payload,
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
    ExecutionPersistenceConflict,
    ExecutionReceiptRecord,
    ExecutionReconciliationRecord,
    ExecutionTransitionRecord,
    ExecutionTimestamp,
    ExecutionDispatchAuthorizationRecord,
    ExecutionDispatchClaimRecord,
    ExecutionDispatchClaim,
    ExecutionDispatchControlRecord,
    ExecutionDispatchResolutionRecord,
    IdempotencyReservationResult,
    RecordLoadResult,
    TransitionAppendResult,
    UnitOfWorkCommitResult,
    DispatchClaimResult,
    ExecutionDispatchClaimAttempt,
    DispatchOutcomeWriteSet,
)
from volcanoes.application.execution.persistence.enums import (
    DispatchClaimStatus,
    DispatchResolutionStatus,
    ExecutionPersistenceConflictKind,
    ExecutionPersistenceConflictSeverity,
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
    InMemoryExecutionDispatchAuthorizationRepository,
    InMemoryExecutionDispatchClaimRepository,
    InMemoryExecutionDispatchControlRepository,
    InMemoryExecutionDispatchResolutionRepository,
    _aggregate_save_result,
    _dispatch_outcome_aggregate_save_result,
    _broker_reference_result,
    _command_registration_result,
    _fact_result,
    _idempotency_result,
    _record_result_for_unique_identity,
    _transition_result,
)
from volcanoes.application.execution.persistence.in_memory.state import (
    InMemoryExecutionPersistenceState,
)


class InMemoryExecutionUnitOfWork:
    """Deterministic process-local transaction over one state container."""

    def __init__(
        self, state: InMemoryExecutionPersistenceState, lock: LockType | None = None
    ) -> None:
        self._base_state = state
        self._lock = lock or allocate_lock()
        self.transaction_state = state.snapshot()
        self._closed = False
        self._committed = False
        self._rolled_back = False
        self._staged_aggregate_saves: list[
            tuple[ExecutionAggregateRecord, PaperExecutionRevision, int]
        ] = []
        self._staged_commands: list[ExecutionCommandRecord] = []
        self._staged_idempotency: list[ExecutionIdempotencyRecord] = []
        self._staged_transitions: list[ExecutionTransitionRecord] = []
        self._staged_broker_references: list[ExecutionBrokerReferenceRecord] = []
        self._staged_receipts: list[ExecutionReceiptRecord] = []
        self._staged_failures: list[ExecutionFailureRecord] = []
        self._staged_approvals: list[ExecutionApprovalRecord] = []
        self._staged_reconciliations: list[ExecutionReconciliationRecord] = []
        self._staged_dispatch_controls: list[ExecutionDispatchControlRecord] = []
        self._staged_dispatch_claims: list[ExecutionDispatchClaimRecord] = []
        self._staged_dispatch_authorizations: list[
            ExecutionDispatchAuthorizationRecord
        ] = []
        self._staged_dispatch_resolutions: list[ExecutionDispatchResolutionRecord] = []
        self._staged_dispatch_outcomes: list[DispatchOutcomeWriteSet] = []
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
        self.dispatch_control = InMemoryExecutionDispatchControlRepository(self)
        self.dispatch_claims = InMemoryExecutionDispatchClaimRepository(self)
        self.dispatch_authorizations = InMemoryExecutionDispatchAuthorizationRepository(
            self
        )
        self.dispatch_resolutions = InMemoryExecutionDispatchResolutionRepository(self)

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
        *,
        revision_increment: int = 1,
    ) -> None:
        self._staged_aggregate_saves.append(
            (record, expected_revision, revision_increment)
        )

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

    def stage_dispatch_control(self, record: ExecutionDispatchControlRecord) -> None:
        self._staged_dispatch_controls.append(record)

    def stage_dispatch_claim(self, record: ExecutionDispatchClaimRecord) -> None:
        self._staged_dispatch_claims.append(record)

    def stage_dispatch_authorization(
        self, record: ExecutionDispatchAuthorizationRecord
    ) -> None:
        self._staged_dispatch_authorizations.append(record)

    def stage_dispatch_resolution(
        self, record: ExecutionDispatchResolutionRecord
    ) -> None:
        self._staged_dispatch_resolutions.append(record)

    def commit(self) -> UnitOfWorkCommitResult:
        if self._committed:
            return UnitOfWorkCommitResult(
                status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
                committed=False,
                schema_version=SCHEMA_VERSION,
            )
        self.ensure_active()
        with self._lock:
            validation_state = self._base_state.snapshot()
            conflict = self._blocking_conflict or self._validate_and_apply(
                validation_state
            )
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

    def record_dispatch_outcome(
        self, write_set: DispatchOutcomeWriteSet
    ) -> RecordLoadResult:
        before_state = self.transaction_state.snapshot()
        before_counts = self._dispatch_outcome_counts()
        before_conflict = self._blocking_conflict
        try:
            return self._record_dispatch_outcome_staged(write_set)
        except BaseException:
            self._restore_dispatch_outcome(before_state, before_counts, before_conflict)
            raise

    def _record_dispatch_outcome_staged(
        self, write_set: DispatchOutcomeWriteSet
    ) -> RecordLoadResult:
        before_state = self.transaction_state.snapshot()
        before_counts = self._dispatch_outcome_counts()
        before_conflict = self._blocking_conflict
        if not _valid_latest_outcome(write_set, self.transaction_state):
            return self._abort_dispatch_outcome(
                before_state,
                before_counts,
                before_conflict,
                RecordLoadResult(
                    ExecutionPersistenceResultStatus.COMMAND_CONFLICT, SCHEMA_VERSION
                ),
            )
        claim = self.dispatch_claims.get(write_set.claim.claim_token)
        authorization = self.dispatch_authorizations.get(write_set.claim.claim_token)
        if (
            claim is None
            or claim.to_public() != write_set.claim
            or authorization != write_set.authorization
            or not _valid_public_client_order_id(write_set.claim)
        ):
            return self._abort_dispatch_outcome(
                before_state,
                before_counts,
                before_conflict,
                RecordLoadResult(
                    ExecutionPersistenceResultStatus.COMMAND_CONFLICT, SCHEMA_VERSION
                ),
            )
        if write_set.broker_reference is not None:
            owned = self.broker_references.register(write_set.broker_reference)
            if owned.status is not ExecutionPersistenceResultStatus.CREATED:
                return self._abort_dispatch_outcome(
                    before_state, before_counts, before_conflict, owned
                )
        evidence_result = (
            self.receipts.record(write_set.evidence)
            if isinstance(write_set.evidence, ExecutionReceiptRecord)
            else self.failures.record(write_set.evidence)
        )
        if evidence_result.status is not ExecutionPersistenceResultStatus.CREATED:
            return self._abort_dispatch_outcome(
                before_state, before_counts, before_conflict, evidence_result
            )
        for transition in write_set.transitions:
            appended = self.transitions.append(transition)
            if appended.status is not ExecutionPersistenceResultStatus.APPENDED:
                return self._abort_dispatch_outcome(
                    before_state,
                    before_counts,
                    before_conflict,
                    RecordLoadResult(appended.status, SCHEMA_VERSION),
                )
        aggregate = self.aggregates._save_dispatch_outcome(
            write_set.aggregate,
            expected_revision=write_set.expected_revision,
            revision_increment=len(write_set.transitions),
        )
        if aggregate.status is not ExecutionPersistenceResultStatus.SAVED:
            return self._abort_dispatch_outcome(
                before_state,
                before_counts,
                before_conflict,
                RecordLoadResult(aggregate.status, SCHEMA_VERSION),
            )
        resolution = self.dispatch_resolutions.record(write_set.resolution)
        if resolution.status is not ExecutionPersistenceResultStatus.CREATED:
            return self._abort_dispatch_outcome(
                before_state, before_counts, before_conflict, resolution
            )
        self._staged_dispatch_outcomes.append(write_set)
        return resolution

    def _abort_dispatch_outcome(
        self,
        before_state: InMemoryExecutionPersistenceState,
        counts: tuple[int, int, int, int, int, int, int],
        conflict: ExecutionPersistenceConflict | None,
        result: RecordLoadResult,
    ) -> RecordLoadResult:
        self._restore_dispatch_outcome(before_state, counts, conflict)
        return result

    def _dispatch_outcome_counts(self) -> tuple[int, int, int, int, int, int, int]:
        return (
            len(self._staged_broker_references),
            len(self._staged_receipts),
            len(self._staged_failures),
            len(self._staged_transitions),
            len(self._staged_aggregate_saves),
            len(self._staged_dispatch_resolutions),
            len(self._staged_dispatch_outcomes),
        )

    def _restore_dispatch_outcome(
        self,
        before_state: InMemoryExecutionPersistenceState,
        counts: tuple[int, int, int, int, int, int, int],
        conflict: ExecutionPersistenceConflict | None,
    ) -> None:
        self.transaction_state = before_state
        del self._staged_broker_references[counts[0] :]
        del self._staged_receipts[counts[1] :]
        del self._staged_failures[counts[2] :]
        del self._staged_transitions[counts[3] :]
        del self._staged_aggregate_saves[counts[4] :]
        del self._staged_dispatch_resolutions[counts[5] :]
        del self._staged_dispatch_outcomes[counts[6] :]
        self._blocking_conflict = conflict

    def _validate_and_apply(
        self,
        validation_state: InMemoryExecutionPersistenceState,
    ) -> ExecutionPersistenceConflict | None:
        for write_set in self._staged_dispatch_outcomes:
            if not _valid_latest_outcome(write_set, validation_state):
                return _dispatch_conflict("DISPATCH_OUTCOME_CONFLICT")
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

        for (
            aggregate,
            expected_revision,
            revision_increment,
        ) in self._staged_aggregate_saves:
            existing_aggregate = validation_state._aggregates.get(
                aggregate.aggregate_id
            )
            aggregate_result = (
                _aggregate_save_result(aggregate, existing_aggregate, expected_revision)
                if revision_increment == 1
                else _dispatch_outcome_aggregate_save_result(
                    aggregate,
                    existing_aggregate,
                    expected_revision,
                    revision_increment,
                )
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
                validation_state._transitions_by_aggregate_revision.get(
                    (transition.aggregate_id, transition.next_revision)
                ),
                validation_state._transitions_by_aggregate_transition_id.get(
                    (transition.aggregate_id, transition.transition_id)
                ),
            )
            if transition_result.conflict is not None:
                return transition_result.conflict
            if transition_result.status is ExecutionPersistenceResultStatus.APPENDED:
                validation_state._transitions_by_id[transition.transition_record_id] = (
                    transition
                )
                validation_state._transitions_by_aggregate_revision[
                    (transition.aggregate_id, transition.next_revision)
                ] = transition
                validation_state._transitions_by_aggregate_transition_id[
                    (transition.aggregate_id, transition.transition_id)
                ] = transition
                validation_state._transition_order = (
                    *validation_state._transition_order,
                    transition.transition_record_id,
                )

        for reference in self._staged_broker_references:
            existing = validation_state._broker_references.get(
                reference.broker_reference
            )
            active_owner = next(
                (
                    candidate
                    for candidate in validation_state._broker_references.values()
                    if candidate.aggregate_id == reference.aggregate_id
                    and candidate.active
                ),
                None,
            )
            broker_reference_result = _broker_reference_result(
                reference, existing, active_owner
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
            identity = receipt.receipt.receipt_fingerprint
            receipt_result = _fact_result(
                receipt.record_fingerprint,
                validation_state._receipts.get(identity),
                code="RECEIPT_CONFLICT",
                safe_message="Receipt record fingerprint conflict.",
                aggregate_id=receipt.receipt.aggregate_id,
                command_id=receipt.receipt.command_id,
            )
            if receipt_result.conflict is not None:
                return receipt_result.conflict
            if receipt_result.status is ExecutionPersistenceResultStatus.CREATED:
                validation_state._receipts[identity] = receipt

        for failure in self._staged_failures:
            identity = failure.failure.failure_fingerprint
            failure_result = _fact_result(
                failure.record_fingerprint,
                validation_state._failures.get(identity),
                code="FAILURE_CONFLICT",
                safe_message="Failure record fingerprint conflict.",
                aggregate_id=failure.failure.aggregate_id,
                command_id=failure.failure.command_id,
            )
            if failure_result.conflict is not None:
                return failure_result.conflict
            if failure_result.status is ExecutionPersistenceResultStatus.CREATED:
                validation_state._failures[identity] = failure

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

        for control in self._staged_dispatch_controls:
            current = validation_state._dispatch_control
            if current is not None and control.generation != current.generation + 1:
                return _dispatch_conflict("STALE_CONTROL_GENERATION")
            validation_state._dispatch_control = control
        for claim in self._staged_dispatch_claims:
            if not _valid_latest_claim(claim, validation_state):
                return _dispatch_conflict("DISPATCH_CLAIM_AUTHORITY_CHANGED")
            if any(
                existing.claim_token == claim.claim_token
                or existing.submission_id == claim.submission_id
                or existing.command_id == claim.command_id
                or existing.idempotency_key == claim.idempotency_key
                or existing.client_order_id == claim.client_order_id
                or existing.capability_verifier == claim.capability_verifier
                for existing in validation_state._dispatch_claims.values()
            ):
                return _dispatch_conflict("DISPATCH_CLAIM_CONFLICT")
            validation_state._dispatch_claims[claim.claim_token] = claim
        for authorization in self._staged_dispatch_authorizations:
            authorized_claim = validation_state._dispatch_claims.get(
                authorization.claim_token
            )
            if (
                authorized_claim is None
                or not _valid_latest_claim(authorized_claim, validation_state)
                or authorization.control_generation
                != authorized_claim.control_generation
                or authorization.claim_token
                in validation_state._dispatch_authorizations
            ):
                return _dispatch_conflict("DISPATCH_AUTHORIZATION_CONFLICT")
            validation_state._dispatch_authorizations[authorization.claim_token] = (
                authorization
            )
        for resolution in self._staged_dispatch_resolutions:
            resolved_claim = validation_state._dispatch_claims.get(
                resolution.claim_token
            )
            resolved_authorization = validation_state._dispatch_authorizations.get(
                resolution.claim_token
            )
            if (
                resolved_claim is None
                or resolution.claim_token in validation_state._dispatch_resolutions
                or (
                    resolution.effect_phase.value != "PRE_EFFECT"
                    and resolved_authorization is None
                )
            ):
                return _dispatch_conflict("DISPATCH_RESOLUTION_CONFLICT")
            validation_state._dispatch_resolutions[resolution.claim_token] = resolution

        return None


def _valid_latest_claim(
    claim: ExecutionDispatchClaimRecord,
    state: InMemoryExecutionPersistenceState,
) -> bool:
    control = state._dispatch_control
    command = state._commands.get(claim.command_id)
    aggregate = state._aggregates.get(claim.aggregate_id)
    reservation = state._idempotency.get(claim.idempotency_key)
    approval = state._approvals.get(claim.approval_fingerprint)
    if (
        control is None
        or not control.permits_dispatch
        or control.generation != claim.control_generation
        or command is None
        or command.aggregate_id != claim.aggregate_id
        or command.correlation_id != claim.correlation_id
        or command.idempotency_key != claim.idempotency_key
        or command.record_fingerprint != claim.command_record_fingerprint
        or command.canonical_payload_fingerprint != claim.canonical_payload_fingerprint
        or command.approval_fingerprint != claim.approval_fingerprint
        or command.policy_fingerprint != claim.policy_fingerprint
        or command.canonical_command_json != claim.canonical_order_json
        or aggregate is None
        or aggregate.correlation_id != claim.correlation_id
        or aggregate.lifecycle_state.value != "DISPATCH_PENDING"
        or aggregate.execution_revision != claim.expected_execution_revision
        or reservation is None
        or reservation.command_id != claim.command_id
        or reservation.aggregate_id != claim.aggregate_id
        or approval is None
        or approval.bound_fingerprint != claim.canonical_payload_fingerprint
        or approval.mode.value != "PAPER"
        or approval.revocation_reference is not None
        or (approval.expires_at is not None and approval.expires_at < claim.claimed_at)
        or not _valid_capability_verifier(claim.capability_verifier)
        or claim.client_order_id != _client_order_id(claim)
    ):
        return False
    try:
        payload = json.loads(
            claim.canonical_order_json,
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (TypeError, ValueError):
        return False
    return (
        isinstance(payload, dict)
        and canonical_json_text(payload) == claim.canonical_order_json
        and command_payload_fingerprint(payload) == claim.canonical_payload_fingerprint
    )


def _valid_latest_outcome(
    write_set: DispatchOutcomeWriteSet,
    state: InMemoryExecutionPersistenceState,
) -> bool:
    private_claim = state._dispatch_claims.get(write_set.claim.claim_token)
    current_aggregate = state._aggregates.get(write_set.claim.aggregate_id)
    approval = state._approvals.get(write_set.claim.approval_fingerprint)
    if (
        private_claim is None
        or private_claim.to_public() != write_set.claim
        or not _valid_latest_claim(private_claim, state)
        or state._dispatch_authorizations.get(write_set.claim.claim_token)
        != write_set.authorization
        or write_set.authorization.control_generation
        != write_set.claim.control_generation
        or current_aggregate is None
        or current_aggregate.execution_revision != write_set.expected_revision
        or current_aggregate.lifecycle_state
        is not write_set.transitions[0].source_state
        or current_aggregate.lifecycle_state.value != "DISPATCH_PENDING"
        or write_set.expected_revision != write_set.claim.expected_execution_revision
        or write_set.claim.claim_token in state._dispatch_resolutions
        or approval is None
        or (
            approval.expires_at is not None
            and approval.expires_at < write_set.resolution.resolved_at
        )
    ):
        return False
    if (
        write_set.resolution.status
        is DispatchResolutionStatus.BROKER_REFERENCE_CONFLICT
    ):
        observed = write_set.resolution.broker_reference
        if observed is None:
            return False
        owner = next(
            (
                candidate
                for key, candidate in state._broker_references.items()
                if str(key) == observed
            ),
            None,
        )
        return bool(
            owner is not None
            and owner.aggregate_id
            == write_set.resolution.conflicting_owner_aggregate_id
            and owner.command_id == write_set.resolution.conflicting_owner_command_id
            and owner.record_fingerprint
            == write_set.resolution.conflicting_owner_record_fingerprint
            and owner.aggregate_id != write_set.claim.aggregate_id
            and owner.command_id != write_set.claim.command_id
        )
    reference = write_set.broker_reference
    if reference is None:
        return True
    existing = state._broker_references.get(reference.broker_reference)
    if existing is not None and existing != reference:
        return False
    return not any(
        candidate.aggregate_id == reference.aggregate_id
        and candidate.active
        and candidate.broker_reference != reference.broker_reference
        for candidate in state._broker_references.values()
    )


def _valid_capability_verifier(value: str) -> bool:
    return (
        len(value) == 68
        and value.startswith("pcv-")
        and all(character in "0123456789abcdef" for character in value[4:])
    )


def _client_order_id(
    claim: ExecutionDispatchClaimRecord | ExecutionDispatchClaim,
) -> str:
    digest = fingerprint_payload(
        "pci",
        {
            "domain": "paper-client-order-v1",
            "inputs": {
                "canonical_payload_fingerprint": claim.canonical_payload_fingerprint,
                "command_id": claim.command_id,
                "idempotency_key": claim.idempotency_key,
                "submission_id": claim.submission_id,
            },
        },
    ).rsplit("-", 1)[-1]
    return "paper-" + digest[:42]


def _valid_public_client_order_id(claim: ExecutionDispatchClaim) -> bool:
    return claim.client_order_id == _client_order_id(claim)


def _reject_duplicate_json_keys(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


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


def _dispatch_conflict(code: str) -> ExecutionPersistenceConflict:
    return ExecutionPersistenceConflict(
        kind=ExecutionPersistenceConflictKind.RECORD_VERSION_CONFLICT,
        severity=ExecutionPersistenceConflictSeverity.ERROR,
        code=code,
        safe_message="Concurrent dispatch state changed before commit.",
        schema_version=SCHEMA_VERSION,
    )


class InMemoryExecutionPersistence:
    """Factory for isolated in-memory execution persistence units of work."""

    def __init__(self) -> None:
        self._state = InMemoryExecutionPersistenceState()
        self._lock = allocate_lock()

    def unit_of_work(self) -> InMemoryExecutionUnitOfWork:
        return InMemoryExecutionUnitOfWork(self._state, self._lock)

    def acquire_and_authorize_dispatch(
        self,
        attempt: ExecutionDispatchClaimAttempt,
        *,
        claimed_at: ExecutionTimestamp,
        authorized_at: ExecutionTimestamp,
    ) -> DispatchClaimResult:
        with self.unit_of_work() as first:
            result = first.dispatch_claims.acquire(attempt, claimed_at=claimed_at)
            grant = first.dispatch_claims._take_winner_grant()
            if result.status is not DispatchClaimStatus.ACQUIRED:
                first.rollback()
                return result
            if grant is None or not first.commit().committed or result.claim is None:
                return DispatchClaimResult(
                    DispatchClaimStatus.BLOCKED,
                    None,
                    SCHEMA_VERSION,
                    "CLAIM_COMMIT_FAILED",
                )
        with self.unit_of_work() as second:
            authorization = second.dispatch_claims._authorize_private(
                result.claim, grant, authorized_at=authorized_at
            )
            aggregate = second.aggregates.load_record(result.claim.aggregate_id)
            if (
                authorization is None
                or aggregate is None
                or not second.commit().committed
            ):
                return DispatchClaimResult(
                    DispatchClaimStatus.BLOCKED,
                    result.claim,
                    SCHEMA_VERSION,
                    "FINAL_GUARD_BLOCKED",
                )
            return replace(
                result,
                reason_code="AUTHORIZED_WINNER",
                authorized=True,
                authorization=authorization,
                aggregate=aggregate,
            )

    def snapshot(self) -> InMemoryExecutionPersistenceState:
        """Return an isolated state copy for deterministic test inspection."""

        with self._lock:
            return self._state.snapshot()


__all__ = [
    "InMemoryExecutionPersistence",
    "InMemoryExecutionUnitOfWork",
]
