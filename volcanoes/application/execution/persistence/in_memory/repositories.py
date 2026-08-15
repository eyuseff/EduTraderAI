"""Repository implementations for the process-local in-memory adapter."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import TYPE_CHECKING

from volcanoes.application.execution.fingerprints import (
    command_payload_fingerprint,
    fingerprint_payload,
)
from volcanoes.application.execution._canonical import canonical_json_text

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
    ExecutionPersistenceConflict,
    ExecutionReceiptRecord,
    ExecutionReconciliationRecord,
    ExecutionRestartDiscoveryQuery,
    ExecutionTransitionRecord,
    ExecutionTimestamp,
    IdempotencyReservationResult,
    RecordLoadResult,
    ReplayLookupResult,
    RestartDiscoveryResult,
    TransitionAppendResult,
    DispatchClaimResult,
    DispatchWinnerGrant,
    new_dispatch_capability,
    dispatch_capability_verifier,
    ExecutionDispatchClaimAttempt,
    ExecutionDispatchAuthorizationRecord,
    ExecutionDispatchClaimRecord,
    ExecutionDispatchClaim,
    ExecutionDispatchControlRecord,
    ExecutionDispatchResolutionRecord,
)
from volcanoes.application.execution.persistence.enums import (
    ExecutionPersistenceConflictKind,
    ExecutionPersistenceConflictSeverity,
    ExecutionPersistenceResultStatus,
    ExecutionReplayKind,
    DispatchClaimStatus,
)

if TYPE_CHECKING:
    from volcanoes.application.execution.persistence.in_memory.unit_of_work import (
        InMemoryExecutionUnitOfWork,
    )

SCHEMA_VERSION = 4


def _conflict(
    *,
    kind: ExecutionPersistenceConflictKind,
    code: str,
    safe_message: str,
    aggregate_id: PaperExecutionAggregateId | None = None,
    command_id: PaperExecutionCommandId | None = None,
    idempotency_key: PaperExecutionIdempotencyKey | None = None,
    expected_revision: PaperExecutionRevision | None = None,
    actual_revision: PaperExecutionRevision | None = None,
) -> ExecutionPersistenceConflict:
    return ExecutionPersistenceConflict(
        kind=kind,
        severity=ExecutionPersistenceConflictSeverity.ERROR,
        code=code,
        safe_message=safe_message,
        schema_version=SCHEMA_VERSION,
        aggregate_id=aggregate_id,
        command_id=command_id,
        idempotency_key=idempotency_key,
        expected_revision=expected_revision,
        actual_revision=actual_revision,
    )


class _RepositoryBase:
    def __init__(self, unit_of_work: "InMemoryExecutionUnitOfWork") -> None:
        self._unit_of_work = unit_of_work

    def _ensure_active(self) -> None:
        self._unit_of_work.ensure_active()


class InMemoryExecutionAggregateRepository(_RepositoryBase):
    """In-memory aggregate repository implementing explicit revision checks."""

    def get(self, aggregate_id: PaperExecutionAggregateId) -> RecordLoadResult:
        self._ensure_active()
        record = self._unit_of_work.transaction_state._aggregates.get(aggregate_id)
        if record is None:
            return RecordLoadResult(
                status=ExecutionPersistenceResultStatus.NOT_FOUND,
                schema_version=SCHEMA_VERSION,
            )
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.LOADED,
            record_fingerprint=record.record_fingerprint,
            schema_version=SCHEMA_VERSION,
        )

    def load_record(
        self,
        aggregate_id: PaperExecutionAggregateId,
    ) -> ExecutionAggregateRecord | None:
        self._ensure_active()
        return self._unit_of_work.transaction_state._aggregates.get(aggregate_id)

    def save(
        self,
        record: ExecutionAggregateRecord,
        *,
        expected_revision: PaperExecutionRevision,
    ) -> AggregateSaveResult:
        self._ensure_active()
        existing = self._unit_of_work.transaction_state._aggregates.get(
            record.aggregate_id
        )
        result = _aggregate_save_result(record, existing, expected_revision)
        if result.conflict is not None:
            self._unit_of_work.stage_conflict(result.conflict)
        if result.conflict is None and result.status in {
            ExecutionPersistenceResultStatus.CREATED,
            ExecutionPersistenceResultStatus.SAVED,
        }:
            self._unit_of_work.transaction_state._aggregates[record.aggregate_id] = (
                record
            )
            self._unit_of_work.stage_aggregate_save(record, expected_revision)
        return result

    def _save_dispatch_outcome(
        self,
        record: ExecutionAggregateRecord,
        *,
        expected_revision: PaperExecutionRevision,
        revision_increment: int,
    ) -> AggregateSaveResult:
        """Stage one final CAS for a previously validated transition chain."""
        self._ensure_active()
        existing = self._unit_of_work.transaction_state._aggregates.get(
            record.aggregate_id
        )
        result = _dispatch_outcome_aggregate_save_result(
            record, existing, expected_revision, revision_increment
        )
        if result.conflict is not None:
            self._unit_of_work.stage_conflict(result.conflict)
        elif result.status is ExecutionPersistenceResultStatus.SAVED:
            self._unit_of_work.transaction_state._aggregates[record.aggregate_id] = (
                record
            )
            self._unit_of_work.stage_aggregate_save(
                record, expected_revision, revision_increment=revision_increment
            )
        return result

    def records(self) -> tuple[ExecutionAggregateRecord, ...]:
        self._ensure_active()
        return self._unit_of_work.transaction_state.aggregate_records()


class InMemoryExecutionCommandRepository(_RepositoryBase):
    """In-memory immutable command repository."""

    def get(self, command_id: PaperExecutionCommandId) -> RecordLoadResult:
        self._ensure_active()
        record = self._unit_of_work.transaction_state._commands.get(command_id)
        if record is None:
            return RecordLoadResult(
                status=ExecutionPersistenceResultStatus.NOT_FOUND,
                schema_version=SCHEMA_VERSION,
            )
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.LOADED,
            record_fingerprint=record.record_fingerprint,
            schema_version=SCHEMA_VERSION,
        )

    def load_record(
        self,
        command_id: PaperExecutionCommandId,
    ) -> ExecutionCommandRecord | None:
        self._ensure_active()
        return self._unit_of_work.transaction_state._commands.get(command_id)

    def register(
        self,
        record: ExecutionCommandRecord,
    ) -> CommandRegistrationResult:
        self._ensure_active()
        existing = self._unit_of_work.transaction_state._commands.get(record.command_id)
        result = _command_registration_result(record, existing)
        if result.conflict is not None:
            self._unit_of_work.stage_conflict(result.conflict)
        if result.status is ExecutionPersistenceResultStatus.CREATED:
            self._unit_of_work.transaction_state._commands[record.command_id] = record
            self._unit_of_work.stage_command(record)
        return result

    def lookup_replay(
        self,
        command_id: PaperExecutionCommandId,
        payload_fingerprint: str,
    ) -> ReplayLookupResult:
        self._ensure_active()
        existing = self._unit_of_work.transaction_state._commands.get(command_id)
        if existing is None:
            return ReplayLookupResult(
                status=ExecutionPersistenceResultStatus.NOT_FOUND,
                replay_kind=ExecutionReplayKind.NONE,
                schema_version=SCHEMA_VERSION,
            )
        if existing.canonical_payload_fingerprint == payload_fingerprint:
            return ReplayLookupResult(
                status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
                replay_kind=ExecutionReplayKind.EXACT_COMMAND,
                original_command_id=existing.command_id,
                original_result_fingerprint=existing.record_fingerprint,
                schema_version=SCHEMA_VERSION,
            )
        return ReplayLookupResult(
            status=ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
            replay_kind=ExecutionReplayKind.NONE,
            conflict=_conflict(
                kind=ExecutionPersistenceConflictKind.COMMAND_PAYLOAD_CONFLICT,
                code="COMMAND_PAYLOAD_CONFLICT",
                safe_message="Command identity already exists with different payload.",
                aggregate_id=existing.aggregate_id,
                command_id=command_id,
            ),
            schema_version=SCHEMA_VERSION,
        )

    def records(self) -> tuple[ExecutionCommandRecord, ...]:
        self._ensure_active()
        return self._unit_of_work.transaction_state.command_records()


class InMemoryExecutionIdempotencyRepository(_RepositoryBase):
    """In-memory logical idempotency reservation repository."""

    def get(self, key: PaperExecutionIdempotencyKey) -> RecordLoadResult:
        self._ensure_active()
        record = self._unit_of_work.transaction_state._idempotency.get(key)
        if record is None:
            return RecordLoadResult(
                status=ExecutionPersistenceResultStatus.NOT_FOUND,
                schema_version=SCHEMA_VERSION,
            )
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.LOADED,
            record_fingerprint=record.record_fingerprint,
            schema_version=SCHEMA_VERSION,
        )

    def load_record(
        self,
        key: PaperExecutionIdempotencyKey,
    ) -> ExecutionIdempotencyRecord | None:
        self._ensure_active()
        return self._unit_of_work.transaction_state._idempotency.get(key)

    def reserve(
        self,
        record: ExecutionIdempotencyRecord,
    ) -> IdempotencyReservationResult:
        self._ensure_active()
        existing = self._unit_of_work.transaction_state._idempotency.get(
            record.idempotency_key
        )
        result = _idempotency_result(record, existing)
        if result.conflict is not None:
            self._unit_of_work.stage_conflict(result.conflict)
        if result.status is ExecutionPersistenceResultStatus.CREATED:
            self._unit_of_work.transaction_state._idempotency[
                record.idempotency_key
            ] = record
            self._unit_of_work.stage_idempotency(record)
        return result

    def records(self) -> tuple[ExecutionIdempotencyRecord, ...]:
        self._ensure_active()
        return self._unit_of_work.transaction_state.idempotency_records()


class InMemoryExecutionTransitionJournal(_RepositoryBase):
    """In-memory append-only accepted transition journal."""

    def append(
        self,
        record: ExecutionTransitionRecord,
    ) -> TransitionAppendResult:
        self._ensure_active()
        existing = self._unit_of_work.transaction_state._transitions_by_id.get(
            record.transition_record_id
        )
        existing_revision = (
            self._unit_of_work.transaction_state._transitions_by_aggregate_revision.get(
                (record.aggregate_id, record.next_revision)
            )
        )
        existing_transition_id = self._unit_of_work.transaction_state._transitions_by_aggregate_transition_id.get(
            (record.aggregate_id, record.transition_id)
        )
        result = _transition_result(
            record,
            existing,
            existing_revision,
            existing_transition_id,
        )
        if result.conflict is not None:
            self._unit_of_work.stage_conflict(result.conflict)
        if result.status is ExecutionPersistenceResultStatus.APPENDED:
            self._unit_of_work.transaction_state._transitions_by_id[
                record.transition_record_id
            ] = record
            self._unit_of_work.transaction_state._transitions_by_aggregate_revision[
                (record.aggregate_id, record.next_revision)
            ] = record
            self._unit_of_work.transaction_state._transitions_by_aggregate_transition_id[
                (record.aggregate_id, record.transition_id)
            ] = record
            self._unit_of_work.transaction_state._transition_order = (
                *self._unit_of_work.transaction_state._transition_order,
                record.transition_record_id,
            )
            self._unit_of_work.stage_transition(record)
        return result

    def history(
        self,
        aggregate_id: PaperExecutionAggregateId,
    ) -> tuple[ExecutionTransitionRecord, ...]:
        self._ensure_active()
        return tuple(
            record
            for record in self._unit_of_work.transaction_state.transition_records()
            if record.aggregate_id == aggregate_id
        )

    def records(self) -> tuple[ExecutionTransitionRecord, ...]:
        self._ensure_active()
        return self._unit_of_work.transaction_state.transition_records()


class InMemoryExecutionBrokerReferenceRepository(_RepositoryBase):
    """In-memory normalized broker-reference fact repository."""

    def get(self, reference: PaperBrokerOrderReference) -> RecordLoadResult:
        self._ensure_active()
        record = self._unit_of_work.transaction_state._broker_references.get(reference)
        if record is None:
            return RecordLoadResult(
                status=ExecutionPersistenceResultStatus.NOT_FOUND,
                schema_version=SCHEMA_VERSION,
            )
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.LOADED,
            record_fingerprint=record.record_fingerprint,
            schema_version=SCHEMA_VERSION,
        )

    def load_record(
        self,
        reference: PaperBrokerOrderReference,
    ) -> ExecutionBrokerReferenceRecord | None:
        self._ensure_active()
        return self._unit_of_work.transaction_state._broker_references.get(reference)

    def register(
        self,
        record: ExecutionBrokerReferenceRecord,
    ) -> RecordLoadResult:
        self._ensure_active()
        existing = self._unit_of_work.transaction_state._broker_references.get(
            record.broker_reference
        )
        active_owner = next(
            (
                candidate
                for candidate in self._unit_of_work.transaction_state._broker_references.values()
                if candidate.aggregate_id == record.aggregate_id and candidate.active
            ),
            None,
        )
        result = _broker_reference_result(record, existing, active_owner)
        if result.conflict is not None:
            self._unit_of_work.stage_conflict(result.conflict)
        if result.status is ExecutionPersistenceResultStatus.CREATED:
            self._unit_of_work.transaction_state._broker_references[
                record.broker_reference
            ] = record
            self._unit_of_work.stage_broker_reference(record)
        return result

    def records(self) -> tuple[ExecutionBrokerReferenceRecord, ...]:
        self._ensure_active()
        return self._unit_of_work.transaction_state.broker_reference_records()


class InMemoryExecutionReceiptRepository(_RepositoryBase):
    """In-memory receipt fact repository."""

    def record(self, receipt: ExecutionReceiptRecord) -> RecordLoadResult:
        self._ensure_active()
        identity = receipt.receipt.receipt_fingerprint
        existing = self._unit_of_work.transaction_state._receipts.get(identity)
        result = _fact_result(
            receipt.record_fingerprint,
            existing,
            code="RECEIPT_CONFLICT",
            safe_message="Receipt record fingerprint conflict.",
            aggregate_id=receipt.receipt.aggregate_id,
            command_id=receipt.receipt.command_id,
        )
        if result.conflict is not None:
            self._unit_of_work.stage_conflict(result.conflict)
        if result.status is ExecutionPersistenceResultStatus.CREATED:
            self._unit_of_work.transaction_state._receipts[identity] = receipt
            self._unit_of_work.stage_receipt(receipt)
        return result

    def records(self) -> tuple[ExecutionReceiptRecord, ...]:
        self._ensure_active()
        return self._unit_of_work.transaction_state.receipt_records()


class InMemoryExecutionFailureRepository(_RepositoryBase):
    """In-memory failure fact repository."""

    def record(self, failure: ExecutionFailureRecord) -> RecordLoadResult:
        self._ensure_active()
        identity = failure.failure.failure_fingerprint
        existing = self._unit_of_work.transaction_state._failures.get(identity)
        result = _fact_result(
            failure.record_fingerprint,
            existing,
            code="FAILURE_CONFLICT",
            safe_message="Failure record fingerprint conflict.",
            aggregate_id=failure.failure.aggregate_id,
            command_id=failure.failure.command_id,
        )
        if result.conflict is not None:
            self._unit_of_work.stage_conflict(result.conflict)
        if result.status is ExecutionPersistenceResultStatus.CREATED:
            self._unit_of_work.transaction_state._failures[identity] = failure
            self._unit_of_work.stage_failure(failure)
        return result

    def records(self) -> tuple[ExecutionFailureRecord, ...]:
        self._ensure_active()
        return self._unit_of_work.transaction_state.failure_records()


class InMemoryExecutionApprovalRepository(_RepositoryBase):
    """In-memory approval reference repository."""

    def record(self, approval: ExecutionApprovalRecord) -> RecordLoadResult:
        self._ensure_active()
        existing = self._unit_of_work.transaction_state._approvals.get(
            approval.approval_fingerprint
        )
        result = _record_result_for_unique_identity(
            approval.record_fingerprint,
            existing.record_fingerprint if existing is not None else None,
            conflict_kind=ExecutionPersistenceConflictKind.RECORD_VERSION_CONFLICT,
            conflict_status=ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
            code="APPROVAL_CONFLICT",
            safe_message="Approval identity already exists with different content.",
        )
        if result.conflict is not None:
            self._unit_of_work.stage_conflict(result.conflict)
        if result.status is ExecutionPersistenceResultStatus.CREATED:
            self._unit_of_work.transaction_state._approvals[
                approval.approval_fingerprint
            ] = approval
            self._unit_of_work.stage_approval(approval)
        return result

    def records(self) -> tuple[ExecutionApprovalRecord, ...]:
        self._ensure_active()
        return self._unit_of_work.transaction_state.approval_records()


class InMemoryExecutionReconciliationRepository(_RepositoryBase):
    """In-memory append-only reconciliation fact repository."""

    def record(
        self,
        reconciliation: ExecutionReconciliationRecord,
    ) -> RecordLoadResult:
        self._ensure_active()
        existing = self._unit_of_work.transaction_state._reconciliations.get(
            reconciliation.reconciliation_id
        )
        result = _record_result_for_unique_identity(
            reconciliation.record_fingerprint,
            existing.record_fingerprint if existing is not None else None,
            conflict_kind=ExecutionPersistenceConflictKind.RECORD_VERSION_CONFLICT,
            conflict_status=ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
            code="RECONCILIATION_CONFLICT",
            safe_message="Reconciliation identity already exists with different content.",
            aggregate_id=reconciliation.aggregate_id,
        )
        if result.conflict is not None:
            self._unit_of_work.stage_conflict(result.conflict)
        if result.status is ExecutionPersistenceResultStatus.CREATED:
            self._unit_of_work.transaction_state._reconciliations[
                reconciliation.reconciliation_id
            ] = reconciliation
            self._unit_of_work.stage_reconciliation(reconciliation)
        return result

    def records(self) -> tuple[ExecutionReconciliationRecord, ...]:
        self._ensure_active()
        return self._unit_of_work.transaction_state.reconciliation_records()


class InMemoryExecutionRestartDiscoveryRepository(_RepositoryBase):
    """In-memory process-local restart-discovery query repository."""

    def discover(
        self,
        query: ExecutionRestartDiscoveryQuery,
    ) -> RestartDiscoveryResult:
        self._ensure_active()
        candidates = tuple(
            record
            for record in self._unit_of_work.transaction_state.aggregate_records()
            if _matches_restart_query(record, query)
        )
        offset = _cursor_offset(query.cursor, query, len(candidates))
        limited = candidates[offset:]
        next_cursor = None
        complete = True
        if query.limit is not None and len(limited) > query.limit:
            limited = limited[: query.limit]
            next_cursor = _cursor_token(query, offset + query.limit)
            complete = False
        return RestartDiscoveryResult(
            aggregates=limited,
            complete=complete,
            next_cursor=next_cursor,
            query_fingerprint=query.query_fingerprint,
            schema_version=SCHEMA_VERSION,
        )


class InMemoryExecutionDispatchControlRepository(_RepositoryBase):
    def get(self) -> ExecutionDispatchControlRecord:
        self._ensure_active()
        record = self._unit_of_work.transaction_state._dispatch_control
        if record is None:
            raise RuntimeError("Durable dispatch control is unavailable.")
        return record

    def save(
        self, record: ExecutionDispatchControlRecord, *, expected_generation: int
    ) -> RecordLoadResult:
        self._ensure_active()
        current = self._unit_of_work.transaction_state._dispatch_control
        if current is not None and (
            current.generation != expected_generation
            or record.generation != expected_generation + 1
        ):
            return RecordLoadResult(
                status=ExecutionPersistenceResultStatus.STALE_REVISION,
                schema_version=record.schema_version,
                record_fingerprint=current.record_fingerprint,
            )
        self._unit_of_work.stage_dispatch_control(record)
        self._unit_of_work.transaction_state._dispatch_control = record
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.SAVED,
            schema_version=record.schema_version,
            record_fingerprint=record.record_fingerprint,
        )


class InMemoryExecutionDispatchClaimRepository(_RepositoryBase):
    def get(self, claim_token: str) -> ExecutionDispatchClaimRecord | None:
        self._ensure_active()
        return self._unit_of_work.transaction_state._dispatch_claims.get(claim_token)

    def acquire(
        self, attempt: ExecutionDispatchClaimAttempt, *, claimed_at: ExecutionTimestamp
    ) -> DispatchClaimResult:
        self._ensure_active()
        state = self._unit_of_work.transaction_state
        existing = next(
            (
                item
                for item in state._dispatch_claims.values()
                if item.command_id == attempt.command_id
                or item.idempotency_key == attempt.idempotency_key
                or item.submission_id == attempt.submission_id
            ),
            None,
        )
        if existing is not None:
            exact = (
                existing.request_fingerprint == attempt.attempt_fingerprint
                and existing.submission_id == attempt.submission_id
                and existing.command_id == attempt.command_id
                and existing.idempotency_key == attempt.idempotency_key
            )
            return DispatchClaimResult(
                (
                    DispatchClaimStatus.EXACT_REPLAY
                    if exact
                    else DispatchClaimStatus.ALREADY_CLAIMED
                ),
                existing.to_public(),
                SCHEMA_VERSION,
                "EXACT_CLAIM_REPLAY" if exact else "CLAIM_ALREADY_OWNED",
            )
        control = state._dispatch_control
        if control is None or not control.enabled or control.legacy_authority_active:
            return DispatchClaimResult(
                DispatchClaimStatus.GUARD_DISABLED,
                None,
                SCHEMA_VERSION,
                "GUARD_DISABLED",
            )
        if control.emergency_stop_active:
            return DispatchClaimResult(
                DispatchClaimStatus.EMERGENCY_STOP,
                None,
                SCHEMA_VERSION,
                "EMERGENCY_STOP",
            )
        command = state._commands.get(attempt.command_id)
        reservation = state._idempotency.get(attempt.idempotency_key)
        aggregate = (
            None if command is None else state._aggregates.get(command.aggregate_id)
        )
        approval = (
            None
            if command is None
            else state._approvals.get(command.approval_fingerprint)
        )
        if (
            command is None
            or reservation is None
            or aggregate is None
            or approval is None
        ):
            return DispatchClaimResult(
                DispatchClaimStatus.BLOCKED,
                None,
                SCHEMA_VERSION,
                "DURABLE_AUTHORITY_INCOMPLETE",
            )
        if aggregate.lifecycle_state.value != "DISPATCH_PENDING":
            return DispatchClaimResult(
                DispatchClaimStatus.BLOCKED,
                None,
                SCHEMA_VERSION,
                "DISPATCH_PENDING_REQUIRED",
            )
        if (
            command.operation.value != "SUBMIT"
            or command.idempotency_key != attempt.idempotency_key
            or reservation.command_id != attempt.command_id
            or reservation.aggregate_id != command.aggregate_id
            or command.correlation_id != aggregate.correlation_id
            or approval.revocation_reference is not None
            or approval.bound_fingerprint != command.canonical_payload_fingerprint
            or (approval.expires_at is not None and approval.expires_at < claimed_at)
        ):
            return DispatchClaimResult(
                DispatchClaimStatus.IDENTITY_CONFLICT,
                None,
                SCHEMA_VERSION,
                "DURABLE_IDENTITY_CONFLICT",
            )
        try:
            payload = json.loads(
                command.canonical_command_json,
                object_pairs_hook=_reject_duplicate_json_keys,
            )
        except (TypeError, ValueError):
            return DispatchClaimResult(
                DispatchClaimStatus.BLOCKED,
                None,
                SCHEMA_VERSION,
                "INVALID_CANONICAL_COMMAND",
            )
        if (
            not isinstance(payload, dict)
            or canonical_json_text(payload) != command.canonical_command_json
            or command_payload_fingerprint(payload)
            != command.canonical_payload_fingerprint
        ):
            return DispatchClaimResult(
                DispatchClaimStatus.BLOCKED,
                None,
                SCHEMA_VERSION,
                "INVALID_CANONICAL_COMMAND",
            )
        digest = fingerprint_payload(
            "pci",
            {
                "domain": "paper-client-order-v1",
                "inputs": {
                    "canonical_payload_fingerprint": command.canonical_payload_fingerprint,
                    "command_id": attempt.command_id,
                    "idempotency_key": attempt.idempotency_key,
                    "submission_id": attempt.submission_id,
                },
            },
        ).rsplit("-", 1)[-1]
        token = (
            "claim-"
            + fingerprint_payload(
                "pcl",
                {"domain": "paper-dispatch-claim-v1", "inputs": attempt.to_primitive()},
            ).rsplit("-", 1)[-1]
        )
        capability = new_dispatch_capability()
        record = ExecutionDispatchClaimRecord(
            claim_token=token,
            submission_id=attempt.submission_id,
            command_id=attempt.command_id,
            aggregate_id=command.aggregate_id,
            correlation_id=command.correlation_id,
            idempotency_key=attempt.idempotency_key,
            expected_execution_revision=aggregate.execution_revision,
            request_fingerprint=attempt.attempt_fingerprint,
            command_record_fingerprint=command.record_fingerprint,
            canonical_payload_fingerprint=command.canonical_payload_fingerprint,
            approval_fingerprint=command.approval_fingerprint,
            policy_fingerprint=command.policy_fingerprint,
            client_order_id="paper-" + digest[:42],
            capability_verifier=dispatch_capability_verifier(capability),
            canonical_order_json=command.canonical_command_json,
            control_generation=control.generation,
            claimed_at=claimed_at,
            schema_version=SCHEMA_VERSION,
        )
        claims = self._unit_of_work.transaction_state._dispatch_claims.values()
        existing = next(
            (
                item
                for item in claims
                if item.command_id == record.command_id
                or item.idempotency_key == record.idempotency_key
                or item.submission_id == record.submission_id
            ),
            None,
        )
        if existing is not None:
            exact = (
                existing.request_fingerprint == attempt.attempt_fingerprint
                and existing.submission_id == attempt.submission_id
                and existing.command_id == attempt.command_id
                and existing.idempotency_key == attempt.idempotency_key
            )
            return DispatchClaimResult(
                status=(
                    DispatchClaimStatus.EXACT_REPLAY
                    if exact
                    else DispatchClaimStatus.ALREADY_CLAIMED
                ),
                claim=existing.to_public(),
                schema_version=record.schema_version,
                reason_code="EXACT_CLAIM_REPLAY" if exact else "CLAIM_ALREADY_OWNED",
            )
        self._unit_of_work.stage_dispatch_claim(record)
        self._unit_of_work.transaction_state._dispatch_claims[record.claim_token] = (
            record
        )
        grant = DispatchWinnerGrant(
            record.claim_token,
            capability,
            record.record_fingerprint,
        )
        self._winner_grant = grant
        return DispatchClaimResult(
            status=DispatchClaimStatus.ACQUIRED,
            claim=record.to_public(),
            schema_version=record.schema_version,
            reason_code="CLAIM_ACQUIRED",
        )

    def _take_winner_grant(self) -> DispatchWinnerGrant | None:
        grant = getattr(self, "_winner_grant", None)
        if hasattr(self, "_winner_grant"):
            del self._winner_grant
        return grant

    def _authorize_private(
        self,
        claim: ExecutionDispatchClaim,
        grant: DispatchWinnerGrant,
        *,
        authorized_at: ExecutionTimestamp,
    ) -> ExecutionDispatchAuthorizationRecord | None:
        state = self._unit_of_work.transaction_state
        current = state._dispatch_claims.get(claim.claim_token)
        control = state._dispatch_control
        command = state._commands.get(claim.command_id)
        aggregate = state._aggregates.get(claim.aggregate_id)
        reservation = state._idempotency.get(claim.idempotency_key)
        approval = state._approvals.get(claim.approval_fingerprint)
        if (
            current is None
            or current.to_public() != claim
            or not grant.authenticates(current)
            or control is None
            or not control.permits_dispatch
            or control.generation != claim.control_generation
            or command is None
            or command.record_fingerprint != claim.command_record_fingerprint
            or command.canonical_payload_fingerprint
            != claim.canonical_payload_fingerprint
            or command.canonical_command_json != claim.canonical_order_json
            or command.approval_fingerprint != claim.approval_fingerprint
            or command.policy_fingerprint != claim.policy_fingerprint
            or aggregate is None
            or aggregate.lifecycle_state.value != "DISPATCH_PENDING"
            or aggregate.execution_revision != claim.expected_execution_revision
            or reservation is None
            or reservation.command_id != claim.command_id
            or reservation.aggregate_id != claim.aggregate_id
            or approval is None
            or approval.bound_fingerprint != claim.canonical_payload_fingerprint
            or approval.mode.value != "PAPER"
            or approval.revocation_reference is not None
            or (approval.expires_at is not None and approval.expires_at < authorized_at)
        ):
            return None
        record = ExecutionDispatchAuthorizationRecord(
            claim.claim_token, control.generation, authorized_at, SCHEMA_VERSION
        )
        saved = self._unit_of_work.dispatch_authorizations.record(record)
        return (
            record if saved.status is ExecutionPersistenceResultStatus.CREATED else None
        )


def _reject_duplicate_json_keys(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


class InMemoryExecutionDispatchAuthorizationRepository(_RepositoryBase):
    def get(self, claim_token: str) -> ExecutionDispatchAuthorizationRecord | None:
        self._ensure_active()
        return self._unit_of_work.transaction_state._dispatch_authorizations.get(
            claim_token
        )

    def record(self, record: ExecutionDispatchAuthorizationRecord) -> RecordLoadResult:
        self._ensure_active()
        existing = self.get(record.claim_token)
        if existing is not None:
            status = (
                ExecutionPersistenceResultStatus.EXACT_REPLAY
                if existing == record
                else ExecutionPersistenceResultStatus.COMMAND_CONFLICT
            )
            return RecordLoadResult(
                status=status,
                schema_version=record.schema_version,
                record_fingerprint=existing.record_fingerprint,
            )
        self._unit_of_work.stage_dispatch_authorization(record)
        self._unit_of_work.transaction_state._dispatch_authorizations[
            record.claim_token
        ] = record
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.CREATED,
            schema_version=record.schema_version,
            record_fingerprint=record.record_fingerprint,
        )


class InMemoryExecutionDispatchResolutionRepository(_RepositoryBase):
    def get(self, claim_token: str) -> ExecutionDispatchResolutionRecord | None:
        self._ensure_active()
        return self._unit_of_work.transaction_state._dispatch_resolutions.get(
            claim_token
        )

    def record(self, record: ExecutionDispatchResolutionRecord) -> RecordLoadResult:
        self._ensure_active()
        existing = self.get(record.claim_token)
        if existing is not None:
            status = (
                ExecutionPersistenceResultStatus.EXACT_REPLAY
                if existing == record
                else ExecutionPersistenceResultStatus.COMMAND_CONFLICT
            )
            return RecordLoadResult(
                status=status,
                schema_version=record.schema_version,
                record_fingerprint=existing.record_fingerprint,
            )
        self._unit_of_work.stage_dispatch_resolution(record)
        self._unit_of_work.transaction_state._dispatch_resolutions[
            record.claim_token
        ] = record
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.CREATED,
            schema_version=record.schema_version,
            record_fingerprint=record.record_fingerprint,
        )


def _aggregate_save_result(
    record: ExecutionAggregateRecord,
    existing: ExecutionAggregateRecord | None,
    expected_revision: PaperExecutionRevision,
) -> AggregateSaveResult:
    if existing is None:
        if int(expected_revision) != 0 or int(record.execution_revision) != 0:
            return AggregateSaveResult(
                status=ExecutionPersistenceResultStatus.STALE_REVISION,
                aggregate_id=record.aggregate_id,
                expected_revision=expected_revision,
                current_revision=None,
                conflict=_conflict(
                    kind=ExecutionPersistenceConflictKind.STALE_REVISION,
                    code="AGGREGATE_NOT_FOUND_FOR_REVISION",
                    safe_message="Aggregate does not exist at expected revision.",
                    aggregate_id=record.aggregate_id,
                    expected_revision=expected_revision,
                    actual_revision=None,
                ),
                schema_version=SCHEMA_VERSION,
            )
        return AggregateSaveResult(
            status=ExecutionPersistenceResultStatus.CREATED,
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            current_revision=record.execution_revision,
            aggregate_fingerprint=record.record_fingerprint,
            schema_version=SCHEMA_VERSION,
        )
    if existing.aggregate_terminal:
        return AggregateSaveResult(
            status=ExecutionPersistenceResultStatus.ALREADY_TERMINAL,
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            current_revision=existing.execution_revision,
            conflict=_conflict(
                kind=ExecutionPersistenceConflictKind.TERMINAL_STATE_CONFLICT,
                code="AGGREGATE_TERMINAL",
                safe_message="Terminal aggregate cannot be updated.",
                aggregate_id=record.aggregate_id,
                expected_revision=expected_revision,
                actual_revision=existing.execution_revision,
            ),
            schema_version=SCHEMA_VERSION,
        )
    if existing.execution_revision != expected_revision:
        return AggregateSaveResult(
            status=ExecutionPersistenceResultStatus.STALE_REVISION,
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            current_revision=existing.execution_revision,
            conflict=_conflict(
                kind=ExecutionPersistenceConflictKind.STALE_REVISION,
                code="STALE_AGGREGATE_REVISION",
                safe_message="Aggregate revision changed before save.",
                aggregate_id=record.aggregate_id,
                expected_revision=expected_revision,
                actual_revision=existing.execution_revision,
            ),
            schema_version=SCHEMA_VERSION,
        )
    if existing.record_fingerprint == record.record_fingerprint:
        return AggregateSaveResult(
            status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            current_revision=existing.execution_revision,
            aggregate_fingerprint=existing.record_fingerprint,
            schema_version=SCHEMA_VERSION,
        )
    if int(record.execution_revision) != int(expected_revision) + 1:
        return AggregateSaveResult(
            status=ExecutionPersistenceResultStatus.STALE_REVISION,
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            current_revision=existing.execution_revision,
            conflict=_conflict(
                kind=ExecutionPersistenceConflictKind.STALE_REVISION,
                code="NON_SEQUENTIAL_AGGREGATE_REVISION",
                safe_message="Aggregate revision must advance by exactly one.",
                aggregate_id=record.aggregate_id,
                expected_revision=expected_revision,
                actual_revision=record.execution_revision,
            ),
            schema_version=SCHEMA_VERSION,
        )
    return AggregateSaveResult(
        status=ExecutionPersistenceResultStatus.SAVED,
        aggregate_id=record.aggregate_id,
        expected_revision=expected_revision,
        current_revision=record.execution_revision,
        aggregate_fingerprint=record.record_fingerprint,
        schema_version=SCHEMA_VERSION,
    )


def _dispatch_outcome_aggregate_save_result(
    record: ExecutionAggregateRecord,
    existing: ExecutionAggregateRecord | None,
    expected_revision: PaperExecutionRevision,
    revision_increment: int,
) -> AggregateSaveResult:
    if (
        existing is None
        or existing.execution_revision != expected_revision
        or revision_increment < 1
        or int(record.execution_revision) != int(expected_revision) + revision_increment
    ):
        actual_revision = None if existing is None else existing.execution_revision
        conflict = _conflict(
            kind=ExecutionPersistenceConflictKind.STALE_REVISION,
            code="DISPATCH_OUTCOME_AGGREGATE_REVISION_MISMATCH",
            safe_message="Dispatch outcome aggregate revision chain is invalid.",
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            actual_revision=actual_revision,
        )
        return AggregateSaveResult(
            status=ExecutionPersistenceResultStatus.STALE_REVISION,
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            current_revision=actual_revision,
            conflict=conflict,
            schema_version=SCHEMA_VERSION,
        )
    if existing.aggregate_terminal:
        return _aggregate_save_result(record, existing, expected_revision)
    return AggregateSaveResult(
        status=ExecutionPersistenceResultStatus.SAVED,
        aggregate_id=record.aggregate_id,
        expected_revision=expected_revision,
        current_revision=record.execution_revision,
        aggregate_fingerprint=record.record_fingerprint,
        schema_version=SCHEMA_VERSION,
    )


def _command_registration_result(
    record: ExecutionCommandRecord,
    existing: ExecutionCommandRecord | None,
) -> CommandRegistrationResult:
    if existing is None:
        return CommandRegistrationResult(
            status=ExecutionPersistenceResultStatus.CREATED,
            command_id=record.command_id,
            command_fingerprint=record.record_fingerprint,
            schema_version=SCHEMA_VERSION,
        )
    if existing.canonical_payload_fingerprint == record.canonical_payload_fingerprint:
        return CommandRegistrationResult(
            status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
            command_id=record.command_id,
            command_fingerprint=existing.record_fingerprint,
            original_command_id=existing.command_id,
            original_result_fingerprint=existing.record_fingerprint,
            schema_version=SCHEMA_VERSION,
        )
    return CommandRegistrationResult(
        status=ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
        command_id=record.command_id,
        conflict=_conflict(
            kind=ExecutionPersistenceConflictKind.COMMAND_PAYLOAD_CONFLICT,
            code="COMMAND_PAYLOAD_CONFLICT",
            safe_message="Command identity already exists with different payload.",
            aggregate_id=record.aggregate_id,
            command_id=record.command_id,
        ),
        schema_version=SCHEMA_VERSION,
    )


def _idempotency_result(
    record: ExecutionIdempotencyRecord,
    existing: ExecutionIdempotencyRecord | None,
) -> IdempotencyReservationResult:
    if existing is None:
        return IdempotencyReservationResult(
            status=ExecutionPersistenceResultStatus.CREATED,
            idempotency_key=record.idempotency_key,
            reservation_fingerprint=record.record_fingerprint,
            original_command_id=record.command_id,
            original_result_fingerprint=record.original_result_fingerprint,
            schema_version=SCHEMA_VERSION,
        )
    if existing.logical_operation_fingerprint == record.logical_operation_fingerprint:
        return IdempotencyReservationResult(
            status=ExecutionPersistenceResultStatus.LOGICAL_REPLAY,
            idempotency_key=record.idempotency_key,
            reservation_fingerprint=existing.record_fingerprint,
            original_command_id=existing.command_id,
            original_result_fingerprint=existing.original_result_fingerprint
            or existing.record_fingerprint,
            schema_version=SCHEMA_VERSION,
        )
    return IdempotencyReservationResult(
        status=ExecutionPersistenceResultStatus.IDEMPOTENCY_CONFLICT,
        idempotency_key=record.idempotency_key,
        conflict=_conflict(
            kind=ExecutionPersistenceConflictKind.IDEMPOTENCY_PAYLOAD_CONFLICT,
            code="IDEMPOTENCY_PAYLOAD_CONFLICT",
            safe_message="Idempotency key already refers to another operation.",
            aggregate_id=existing.aggregate_id,
            command_id=record.command_id,
            idempotency_key=record.idempotency_key,
        ),
        schema_version=SCHEMA_VERSION,
    )


def _transition_result(
    record: ExecutionTransitionRecord,
    existing: ExecutionTransitionRecord | None,
    existing_revision: ExecutionTransitionRecord | None = None,
    existing_transition_id: ExecutionTransitionRecord | None = None,
) -> TransitionAppendResult:
    if existing is not None:
        if existing.record_fingerprint == record.record_fingerprint:
            return TransitionAppendResult(
                status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
                aggregate_id=record.aggregate_id,
                previous_revision=record.previous_revision,
                next_revision=existing.next_revision,
                transition_fingerprint=existing.record_fingerprint,
                schema_version=SCHEMA_VERSION,
            )
        return _transition_conflict_result(
            record,
            existing,
            code="TRANSITION_RECORD_CONFLICT",
            safe_message="Transition record identity already exists with different content.",
        )
    if existing_revision is not None:
        return _transition_conflict_result(
            record,
            existing_revision,
            code="TRANSITION_REVISION_CONFLICT",
            safe_message="Transition revision is already owned by another record.",
        )
    if existing_transition_id is not None:
        return _transition_conflict_result(
            record,
            existing_transition_id,
            code="TRANSITION_ID_CONFLICT",
            safe_message="Transition identity is already owned by another record.",
        )
    return TransitionAppendResult(
        status=ExecutionPersistenceResultStatus.APPENDED,
        aggregate_id=record.aggregate_id,
        previous_revision=record.previous_revision,
        next_revision=record.next_revision,
        transition_fingerprint=record.record_fingerprint,
        schema_version=SCHEMA_VERSION,
    )


def _transition_conflict_result(
    record: ExecutionTransitionRecord,
    existing: ExecutionTransitionRecord,
    *,
    code: str,
    safe_message: str,
) -> TransitionAppendResult:
    return TransitionAppendResult(
        status=ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
        aggregate_id=record.aggregate_id,
        previous_revision=record.previous_revision,
        next_revision=None,
        conflict=_conflict(
            kind=ExecutionPersistenceConflictKind.TRANSITION_REVISION_CONFLICT,
            code=code,
            safe_message=safe_message,
            aggregate_id=record.aggregate_id,
            command_id=record.command_id,
            expected_revision=record.previous_revision,
            actual_revision=existing.next_revision,
        ),
        schema_version=SCHEMA_VERSION,
    )


def _record_result_for_unique_identity(
    incoming_fingerprint: str,
    existing_fingerprint: str | None,
    *,
    conflict_kind: ExecutionPersistenceConflictKind,
    conflict_status: ExecutionPersistenceResultStatus,
    code: str,
    safe_message: str,
    aggregate_id: PaperExecutionAggregateId | None = None,
    command_id: PaperExecutionCommandId | None = None,
) -> RecordLoadResult:
    if existing_fingerprint is None:
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.CREATED,
            record_fingerprint=incoming_fingerprint,
            schema_version=SCHEMA_VERSION,
        )
    if existing_fingerprint == incoming_fingerprint:
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
            record_fingerprint=existing_fingerprint,
            schema_version=SCHEMA_VERSION,
        )
    return RecordLoadResult(
        status=conflict_status,
        conflict=_conflict(
            kind=conflict_kind,
            code=code,
            safe_message=safe_message,
            aggregate_id=aggregate_id,
            command_id=command_id,
        ),
        schema_version=SCHEMA_VERSION,
    )


def _broker_reference_result(
    record: ExecutionBrokerReferenceRecord,
    existing: ExecutionBrokerReferenceRecord | None,
    active_owner: ExecutionBrokerReferenceRecord | None,
) -> RecordLoadResult:
    if (
        existing is not None
        and existing.record_fingerprint != record.record_fingerprint
    ):
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.DUPLICATE_BROKER_REFERENCE,
            conflict=_conflict(
                kind=ExecutionPersistenceConflictKind.BROKER_REFERENCE_CONFLICT,
                code="BROKER_REFERENCE_CONFLICT",
                safe_message="Broker reference is already bound to another record.",
                aggregate_id=existing.aggregate_id,
                command_id=existing.command_id,
            ),
            record_fingerprint=existing.record_fingerprint,
            schema_version=SCHEMA_VERSION,
        )
    identity_result = _record_result_for_unique_identity(
        record.record_fingerprint,
        existing.record_fingerprint if existing is not None else None,
        conflict_kind=ExecutionPersistenceConflictKind.BROKER_REFERENCE_CONFLICT,
        conflict_status=ExecutionPersistenceResultStatus.DUPLICATE_BROKER_REFERENCE,
        code="BROKER_REFERENCE_CONFLICT",
        safe_message="Broker reference is already bound to another record.",
        aggregate_id=record.aggregate_id,
        command_id=record.command_id,
    )
    if identity_result.status is not ExecutionPersistenceResultStatus.CREATED:
        return identity_result
    if record.active and active_owner is not None:
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.DUPLICATE_BROKER_REFERENCE,
            conflict=_conflict(
                kind=ExecutionPersistenceConflictKind.BROKER_REFERENCE_CONFLICT,
                code="ACTIVE_BROKER_REFERENCE_CONFLICT",
                safe_message="Aggregate already has an active broker reference.",
                aggregate_id=record.aggregate_id,
                command_id=record.command_id,
            ),
            schema_version=SCHEMA_VERSION,
        )
    return identity_result


def _fact_result(
    incoming_fingerprint: str,
    existing: ExecutionReceiptRecord | ExecutionFailureRecord | None,
    *,
    code: str,
    safe_message: str,
    aggregate_id: PaperExecutionAggregateId | None,
    command_id: PaperExecutionCommandId | None,
) -> RecordLoadResult:
    return _record_result_for_unique_identity(
        incoming_fingerprint,
        existing.record_fingerprint if existing is not None else None,
        conflict_kind=ExecutionPersistenceConflictKind.RECORD_VERSION_CONFLICT,
        conflict_status=ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
        code=code,
        safe_message=safe_message,
        aggregate_id=aggregate_id,
        command_id=command_id,
    )


def _insert_by_fingerprint(
    fingerprint: str,
    collection: Mapping[str, object],
    conflict_kind: ExecutionPersistenceConflictKind,
    code: str,
    safe_message: str,
) -> RecordLoadResult:
    existing = collection.get(fingerprint)
    if existing is None:
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.CREATED,
            record_fingerprint=fingerprint,
            schema_version=SCHEMA_VERSION,
        )
    return RecordLoadResult(
        status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
        record_fingerprint=fingerprint,
        schema_version=SCHEMA_VERSION,
    )


def _matches_restart_query(
    record: ExecutionAggregateRecord,
    query: ExecutionRestartDiscoveryQuery,
) -> bool:
    if record.lifecycle_state not in query.lifecycle_states:
        return False
    if not query.include_outcome_unknown and record.outcome_unknown:
        return False
    if not query.include_reconciliation_required and record.reconciliation_required:
        return False
    if (
        query.minimum_updated_at is not None
        and record.updated_at < query.minimum_updated_at
    ):
        return False
    if (
        query.maximum_updated_at is not None
        and record.updated_at > query.maximum_updated_at
    ):
        return False
    return True


def _cursor_scope(query: ExecutionRestartDiscoveryQuery) -> str:
    return fingerprint_payload(
        "pdc",
        {
            "include_outcome_unknown": query.include_outcome_unknown,
            "include_reconciliation_required": query.include_reconciliation_required,
            "lifecycle_states": tuple(
                sorted(state.value for state in query.lifecycle_states)
            ),
            "maximum_updated_at": query.maximum_updated_at,
            "minimum_updated_at": query.minimum_updated_at,
            "mode": query.mode,
            "schema_version": query.schema_version,
        },
    )


def _cursor_token(query: ExecutionRestartDiscoveryQuery, offset: int) -> str:
    return f"cursor-{_cursor_scope(query)}-{offset}"


def _cursor_offset(
    cursor: str | None,
    query: ExecutionRestartDiscoveryQuery,
    candidate_count: int,
) -> int:
    if cursor is None:
        return 0
    prefix = f"cursor-{_cursor_scope(query)}-"
    if not cursor.startswith(prefix):
        return 0
    try:
        offset = int(cursor[len(prefix) :])
    except ValueError:
        return 0
    if offset < 0 or offset > candidate_count:
        return 0
    return offset


__all__ = [
    "InMemoryExecutionDispatchAuthorizationRepository",
    "InMemoryExecutionDispatchClaimRepository",
    "InMemoryExecutionDispatchControlRepository",
    "InMemoryExecutionDispatchResolutionRepository",
    "InMemoryExecutionAggregateRepository",
    "InMemoryExecutionApprovalRepository",
    "InMemoryExecutionBrokerReferenceRepository",
    "InMemoryExecutionCommandRepository",
    "InMemoryExecutionFailureRepository",
    "InMemoryExecutionIdempotencyRepository",
    "InMemoryExecutionReceiptRepository",
    "InMemoryExecutionReconciliationRepository",
    "InMemoryExecutionRestartDiscoveryRepository",
    "InMemoryExecutionTransitionJournal",
]
