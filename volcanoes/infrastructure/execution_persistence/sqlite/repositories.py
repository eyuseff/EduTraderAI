"""SQLite repositories for the first, intentionally incomplete Phase 2 slice."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
import sqlite3
from typing import TYPE_CHECKING

from volcanoes.application.execution.enums import (
    PaperExecutionFailureKind,
    PaperExecutionFailureSeverity,
    PaperExecutionMode,
    PaperExecutionOperation,
    PaperExecutionReceiptKind,
    PaperExecutionStatus,
)
from volcanoes.application.execution.contracts import (
    PaperExecutionFailure,
    PaperExecutionReceipt,
)
from volcanoes.application.execution.fingerprints import (
    command_payload_fingerprint,
    fingerprint_payload,
)
from volcanoes.application.execution._canonical import canonical_json_text
from volcanoes.application.execution.identities import (
    PaperBrokerOrderReference,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionIdempotencyKey,
    PaperExecutionRevision,
)
from volcanoes.application.execution.lifecycle import (
    PaperExecutionLifecycleEvidenceIntentKind,
    PaperExecutionLifecycleInputType,
    PaperExecutionLifecycleSideEffectIntentKind,
    PaperExecutionLifecycleState,
)
from volcanoes.application.execution.persistence.contracts import (
    AggregateSaveResult,
    CommandRegistrationResult,
    ExecutionAggregateRecord,
    ExecutionApprovalRecord,
    ExecutionBrokerReferenceRecord,
    ExecutionCommandRecord,
    ExecutionIdempotencyRecord,
    ExecutionFailureRecord,
    ExecutionReceiptRecord,
    ExecutionReconciliationRecord,
    ExecutionRestartDiscoveryQuery,
    ExecutionTransitionRecord,
    ExecutionPersistenceConflict,
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
    ExecutionBrokerReferenceStatus,
    ExecutionCommandProcessingOutcome,
    ExecutionIdempotencyReservationStatus,
    ExecutionPersistenceConflictKind,
    ExecutionPersistenceConflictSeverity,
    ExecutionPersistenceResultStatus,
    ExecutionReconciliationResultClassification,
    ExecutionReplayKind,
    DispatchClaimStatus,
    DispatchEffectPhase,
    DispatchResolutionStatus,
)
from volcanoes.infrastructure.execution_persistence.sqlite.migration import (
    CURRENT_SCHEMA_VERSION,
)

if TYPE_CHECKING:
    from volcanoes.infrastructure.execution_persistence.sqlite.unit_of_work import (
        _SqliteExecutionTransaction,
    )


def _reject_duplicate_json_keys(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _client_order_id(
    attempt: ExecutionDispatchClaimAttempt, payload_fingerprint: str
) -> str:
    digest = fingerprint_payload(
        "pci",
        {
            "domain": "paper-client-order-v1",
            "inputs": {
                "canonical_payload_fingerprint": payload_fingerprint,
                "command_id": attempt.command_id,
                "idempotency_key": attempt.idempotency_key,
                "submission_id": attempt.submission_id,
            },
        },
    ).rsplit("-", 1)[-1]
    return "paper-" + digest[:42]


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
        schema_version=CURRENT_SCHEMA_VERSION,
        aggregate_id=aggregate_id,
        command_id=command_id,
        idempotency_key=idempotency_key,
        expected_revision=expected_revision,
        actual_revision=actual_revision,
    )


class _RepositoryBase:
    def __init__(self, transaction: "_SqliteExecutionTransaction") -> None:
        self._transaction = transaction

    def _row(
        self, statement: str, parameters: tuple[object, ...]
    ) -> sqlite3.Row | None:
        return self._transaction.execute(statement, parameters).fetchone()


class SqliteExecutionDispatchControlRepository(_RepositoryBase):
    def get(self) -> ExecutionDispatchControlRecord:
        row = self._row(
            "SELECT * FROM execution_dispatch_controls WHERE control_id = 'PAPER_DISPATCH'",
            (),
        )
        if row is None:
            raise RuntimeError("Durable dispatch control is unavailable.")
        return ExecutionDispatchControlRecord(
            enabled=bool(row["enabled"]),
            emergency_stop_active=bool(row["emergency_stop_active"]),
            legacy_authority_active=bool(row["legacy_authority_active"]),
            generation=int(row["generation"]),
            updated_at=_parse_timestamp(row["updated_at"]),
            schema_version=int(row["schema_version"]),
        )

    def save(
        self, record: ExecutionDispatchControlRecord, *, expected_generation: int
    ) -> RecordLoadResult:
        if record.generation != expected_generation + 1:
            return RecordLoadResult(
                status=ExecutionPersistenceResultStatus.STALE_REVISION,
                schema_version=CURRENT_SCHEMA_VERSION,
            )
        cursor = self._transaction.execute(
            """UPDATE execution_dispatch_controls SET enabled=?, emergency_stop_active=?, legacy_authority_active=?, generation=?, updated_at=?, record_fingerprint=? WHERE control_id='PAPER_DISPATCH' AND generation=?""",
            (
                int(record.enabled),
                int(record.emergency_stop_active),
                int(record.legacy_authority_active),
                record.generation,
                _timestamp(record.updated_at),
                record.record_fingerprint,
                expected_generation,
            ),
        )
        return RecordLoadResult(
            status=(
                ExecutionPersistenceResultStatus.SAVED
                if cursor.rowcount == 1
                else ExecutionPersistenceResultStatus.STALE_REVISION
            ),
            schema_version=CURRENT_SCHEMA_VERSION,
            record_fingerprint=(
                record.record_fingerprint if cursor.rowcount == 1 else None
            ),
        )


class SqliteExecutionDispatchClaimRepository(_RepositoryBase):
    def get(self, claim_token: str) -> ExecutionDispatchClaimRecord | None:
        row = self._row(
            "SELECT * FROM execution_dispatch_claims WHERE claim_token = ?",
            (claim_token,),
        )
        return None if row is None else _dispatch_claim_from_row(row)

    def acquire(
        self, attempt: ExecutionDispatchClaimAttempt, *, claimed_at: datetime
    ) -> DispatchClaimResult:
        existing_row = self._row(
            "SELECT * FROM execution_dispatch_claims WHERE command_id=? OR idempotency_key=? OR submission_id=?",
            (
                str(attempt.command_id),
                str(attempt.idempotency_key),
                attempt.submission_id,
            ),
        )
        if existing_row is not None:
            existing = _dispatch_claim_from_row(existing_row)
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
                CURRENT_SCHEMA_VERSION,
                "EXACT_CLAIM_REPLAY" if exact else "CLAIM_ALREADY_OWNED",
            )
        control = self._row(
            "SELECT * FROM execution_dispatch_controls WHERE control_id='PAPER_DISPATCH'",
            (),
        )
        if (
            control is None
            or not bool(control["enabled"])
            or bool(control["legacy_authority_active"])
        ):
            return DispatchClaimResult(
                status=DispatchClaimStatus.GUARD_DISABLED,
                claim=None,
                schema_version=CURRENT_SCHEMA_VERSION,
                reason_code="GUARD_DISABLED",
            )
        if bool(control["emergency_stop_active"]):
            return DispatchClaimResult(
                status=DispatchClaimStatus.EMERGENCY_STOP,
                claim=None,
                schema_version=CURRENT_SCHEMA_VERSION,
                reason_code="EMERGENCY_STOP",
            )
        command = self._row(
            "SELECT * FROM execution_commands WHERE command_id=?",
            (str(attempt.command_id),),
        )
        idempotency = self._row(
            "SELECT * FROM execution_idempotency WHERE idempotency_key=?",
            (str(attempt.idempotency_key),),
        )
        aggregate = (
            None
            if command is None
            else self._row(
                "SELECT * FROM execution_aggregates WHERE aggregate_id=?",
                (command["aggregate_id"],),
            )
        )
        approval = (
            None
            if command is None
            else self._row(
                "SELECT * FROM execution_approvals WHERE approval_fingerprint=?",
                (command["approval_fingerprint"],),
            )
        )
        if (
            command is None
            or aggregate is None
            or idempotency is None
            or approval is None
        ):
            return DispatchClaimResult(
                status=DispatchClaimStatus.BLOCKED,
                claim=None,
                schema_version=CURRENT_SCHEMA_VERSION,
                reason_code="DURABLE_AUTHORITY_INCOMPLETE",
            )
        if aggregate["lifecycle_state"] != "DISPATCH_PENDING":
            return DispatchClaimResult(
                status=DispatchClaimStatus.BLOCKED,
                claim=None,
                schema_version=CURRENT_SCHEMA_VERSION,
                reason_code="DISPATCH_PENDING_REQUIRED",
            )
        exact = (
            command["operation"] == "SUBMIT"
            and command["mode"] == "PAPER"
            and aggregate["mode"] == "PAPER"
            and idempotency["mode"] == "PAPER"
            and approval["mode"] == "PAPER"
            and approval["bound_fingerprint"]
            == command["canonical_payload_fingerprint"]
            and command["idempotency_key"] == str(attempt.idempotency_key)
            and idempotency["command_id"] == str(attempt.command_id)
            and idempotency["aggregate_id"] == command["aggregate_id"]
            and command["correlation_id"] == aggregate["correlation_id"]
            and approval["revocation_reference"] is None
            and (
                approval["expires_at"] is None
                or _parse_timestamp(approval["expires_at"]) >= claimed_at
            )
        )
        if not exact:
            return DispatchClaimResult(
                status=DispatchClaimStatus.IDENTITY_CONFLICT,
                claim=None,
                schema_version=CURRENT_SCHEMA_VERSION,
                reason_code="DURABLE_IDENTITY_CONFLICT",
            )
        try:
            payload = json.loads(
                command["canonical_command_json"],
                object_pairs_hook=_reject_duplicate_json_keys,
            )
        except (TypeError, ValueError):
            return DispatchClaimResult(
                DispatchClaimStatus.BLOCKED,
                None,
                CURRENT_SCHEMA_VERSION,
                "INVALID_CANONICAL_COMMAND",
            )
        if (
            not isinstance(payload, dict)
            or canonical_json_text(payload) != command["canonical_command_json"]
            or command_payload_fingerprint(payload)
            != command["canonical_payload_fingerprint"]
        ):
            return DispatchClaimResult(
                DispatchClaimStatus.BLOCKED,
                None,
                CURRENT_SCHEMA_VERSION,
                "INVALID_CANONICAL_COMMAND",
            )
        client_id = _client_order_id(attempt, command["canonical_payload_fingerprint"])
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
            aggregate_id=command["aggregate_id"],
            correlation_id=command["correlation_id"],
            idempotency_key=attempt.idempotency_key,
            expected_execution_revision=PaperExecutionRevision(
                int(aggregate["execution_revision"])
            ),
            request_fingerprint=attempt.attempt_fingerprint,
            command_record_fingerprint=command["record_fingerprint"],
            canonical_payload_fingerprint=command["canonical_payload_fingerprint"],
            approval_fingerprint=command["approval_fingerprint"],
            policy_fingerprint=command["policy_fingerprint"],
            client_order_id=client_id,
            capability_verifier=dispatch_capability_verifier(capability),
            canonical_order_json=command["canonical_command_json"],
            control_generation=int(control["generation"]),
            claimed_at=claimed_at,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
        row = self._row(
            "SELECT * FROM execution_dispatch_claims WHERE command_id=? OR idempotency_key=? OR submission_id=?",
            (
                str(attempt.command_id),
                str(attempt.idempotency_key),
                attempt.submission_id,
            ),
        )
        if row is not None:
            existing = _dispatch_claim_from_row(row)
            same = (
                existing.submission_id == attempt.submission_id
                and existing.command_id == attempt.command_id
                and existing.idempotency_key == attempt.idempotency_key
                and existing.request_fingerprint == attempt.attempt_fingerprint
            )
            return DispatchClaimResult(
                status=(
                    DispatchClaimStatus.EXACT_REPLAY
                    if same
                    else DispatchClaimStatus.ALREADY_CLAIMED
                ),
                claim=existing.to_public(),
                schema_version=CURRENT_SCHEMA_VERSION,
                reason_code="EXACT_CLAIM_REPLAY" if same else "CLAIM_ALREADY_OWNED",
            )
        self._transaction.execute(
            """INSERT INTO execution_dispatch_claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                record.claim_token,
                record.submission_id,
                str(record.command_id),
                str(record.aggregate_id),
                str(record.correlation_id),
                str(record.idempotency_key),
                int(record.expected_execution_revision),
                record.request_fingerprint,
                record.command_record_fingerprint,
                record.canonical_payload_fingerprint,
                record.approval_fingerprint,
                record.policy_fingerprint,
                record.client_order_id,
                record.capability_verifier,
                record.canonical_order_json,
                record.control_generation,
                _timestamp(record.claimed_at),
                record.mode.value,
                str(record.schema_version),
                record.record_fingerprint,
            ),
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
            schema_version=CURRENT_SCHEMA_VERSION,
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
        authorized_at: datetime,
    ) -> ExecutionDispatchAuthorizationRecord | None:
        current = self.get(claim.claim_token)
        control = self._row(
            "SELECT * FROM execution_dispatch_controls WHERE control_id='PAPER_DISPATCH'",
            (),
        )
        command = self._row(
            "SELECT * FROM execution_commands WHERE command_id=?",
            (str(claim.command_id),),
        )
        aggregate = self._row(
            "SELECT * FROM execution_aggregates WHERE aggregate_id=?",
            (str(claim.aggregate_id),),
        )
        reservation = self._row(
            "SELECT * FROM execution_idempotency WHERE idempotency_key=?",
            (str(claim.idempotency_key),),
        )
        approval = self._row(
            "SELECT * FROM execution_approvals WHERE approval_fingerprint=?",
            (claim.approval_fingerprint,),
        )
        if (
            current is None
            or current.to_public() != claim
            or not grant.authenticates(current)
            or control is None
            or not bool(control["enabled"])
            or bool(control["emergency_stop_active"])
            or bool(control["legacy_authority_active"])
            or int(control["generation"]) != claim.control_generation
            or command is None
            or command["operation"] != "SUBMIT"
            or command["aggregate_id"] != str(claim.aggregate_id)
            or command["correlation_id"] != str(claim.correlation_id)
            or command["idempotency_key"] != str(claim.idempotency_key)
            or command["record_fingerprint"] != claim.command_record_fingerprint
            or command["canonical_payload_fingerprint"]
            != claim.canonical_payload_fingerprint
            or command["canonical_command_json"] != claim.canonical_order_json
            or command["approval_fingerprint"] != claim.approval_fingerprint
            or command["policy_fingerprint"] != claim.policy_fingerprint
            or aggregate is None
            or aggregate["correlation_id"] != str(claim.correlation_id)
            or aggregate["lifecycle_state"] != "DISPATCH_PENDING"
            or int(aggregate["execution_revision"])
            != int(claim.expected_execution_revision)
            or reservation is None
            or reservation["command_id"] != str(claim.command_id)
            or reservation["aggregate_id"] != str(claim.aggregate_id)
            or approval is None
            or approval["bound_fingerprint"] != claim.canonical_payload_fingerprint
            or approval["mode"] != "PAPER"
            or approval["revocation_reference"] is not None
            or claim.client_order_id != _dispatch_client_order_id(claim)
            or (
                approval["expires_at"] is not None
                and _parse_timestamp(approval["expires_at"]) < authorized_at
            )
        ):
            return None
        record = ExecutionDispatchAuthorizationRecord(
            claim.claim_token,
            int(control["generation"]),
            authorized_at,
            CURRENT_SCHEMA_VERSION,
        )
        saved = SqliteExecutionDispatchAuthorizationRepository(
            self._transaction
        ).record(record)
        return (
            record if saved.status is ExecutionPersistenceResultStatus.CREATED else None
        )


def _dispatch_client_order_id(
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


class SqliteExecutionDispatchAuthorizationRepository(_RepositoryBase):
    def get(self, claim_token: str) -> ExecutionDispatchAuthorizationRecord | None:
        row = self._row(
            "SELECT * FROM execution_dispatch_authorizations WHERE claim_token=?",
            (claim_token,),
        )
        return (
            None
            if row is None
            else ExecutionDispatchAuthorizationRecord(
                claim_token=row["claim_token"],
                control_generation=int(row["control_generation"]),
                authorized_at=_parse_timestamp(row["authorized_at"]),
                schema_version=int(row["schema_version"]),
            )
        )

    def record(self, record: ExecutionDispatchAuthorizationRecord) -> RecordLoadResult:
        existing = self.get(record.claim_token)
        if existing is not None:
            return RecordLoadResult(
                status=(
                    ExecutionPersistenceResultStatus.EXACT_REPLAY
                    if existing == record
                    else ExecutionPersistenceResultStatus.COMMAND_CONFLICT
                ),
                schema_version=CURRENT_SCHEMA_VERSION,
                record_fingerprint=existing.record_fingerprint,
            )
        self._transaction.execute(
            "INSERT INTO execution_dispatch_authorizations VALUES (?,?,?,?,?,?)",
            (
                record.claim_token,
                record.authorization_fingerprint,
                record.control_generation,
                _timestamp(record.authorized_at),
                str(record.schema_version),
                record.record_fingerprint,
            ),
        )
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.CREATED,
            schema_version=CURRENT_SCHEMA_VERSION,
            record_fingerprint=record.record_fingerprint,
        )


class SqliteExecutionDispatchResolutionRepository(_RepositoryBase):
    def get(self, claim_token: str) -> ExecutionDispatchResolutionRecord | None:
        row = self._row(
            "SELECT * FROM execution_dispatch_resolutions WHERE claim_token=?",
            (claim_token,),
        )
        return (
            None
            if row is None
            else ExecutionDispatchResolutionRecord(
                claim_token=row["claim_token"],
                status=DispatchResolutionStatus(row["resolution_status"]),
                effect_phase=DispatchEffectPhase(row["effect_phase"]),
                resolved_at=_parse_timestamp(row["resolved_at"]),
                broker_reference=row["broker_reference"],
                observation_fingerprint=row["observation_fingerprint"],
                conflicting_owner_aggregate_id=(
                    None
                    if row["conflicting_owner_aggregate_id"] is None
                    else PaperExecutionAggregateId(
                        row["conflicting_owner_aggregate_id"]
                    )
                ),
                conflicting_owner_command_id=(
                    None
                    if row["conflicting_owner_command_id"] is None
                    else PaperExecutionCommandId(row["conflicting_owner_command_id"])
                ),
                conflicting_owner_record_fingerprint=(
                    row["conflicting_owner_record_fingerprint"]
                ),
                result_fingerprint=row["result_fingerprint"],
                evidence_fingerprint=row["evidence_fingerprint"],
                evidence_record_fingerprint=row["evidence_record_fingerprint"],
                safe_reason_code=row["safe_reason_code"],
                reconciliation_required=bool(row["reconciliation_required"]),
                operator_action_required=bool(row["operator_action_required"]),
                automatic_retry=bool(row["automatic_retry"]),
                schema_version=int(row["schema_version"]),
            )
        )

    def record(self, record: ExecutionDispatchResolutionRecord) -> RecordLoadResult:
        existing = self.get(record.claim_token)
        if existing is not None:
            return RecordLoadResult(
                status=(
                    ExecutionPersistenceResultStatus.EXACT_REPLAY
                    if existing == record
                    else ExecutionPersistenceResultStatus.COMMAND_CONFLICT
                ),
                schema_version=CURRENT_SCHEMA_VERSION,
                record_fingerprint=existing.record_fingerprint,
            )
        self._transaction.execute(
            "INSERT INTO execution_dispatch_resolutions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                record.claim_token,
                record.status.value,
                record.effect_phase.value,
                _timestamp(record.resolved_at),
                record.broker_reference,
                record.observation_fingerprint,
                (
                    None
                    if record.conflicting_owner_aggregate_id is None
                    else str(record.conflicting_owner_aggregate_id)
                ),
                (
                    None
                    if record.conflicting_owner_command_id is None
                    else str(record.conflicting_owner_command_id)
                ),
                record.conflicting_owner_record_fingerprint,
                record.result_fingerprint,
                record.evidence_fingerprint,
                record.evidence_record_fingerprint,
                record.safe_reason_code,
                int(record.reconciliation_required),
                int(record.operator_action_required),
                0,
                str(record.schema_version),
                record.record_fingerprint,
            ),
        )
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.CREATED,
            schema_version=CURRENT_SCHEMA_VERSION,
            record_fingerprint=record.record_fingerprint,
        )


class SqliteExecutionAggregateRepository(_RepositoryBase):
    """SQLite implementation of aggregate load and exact-CAS save semantics."""

    def get(self, aggregate_id: PaperExecutionAggregateId) -> RecordLoadResult:
        record = self.load_record(aggregate_id)
        if record is None:
            return RecordLoadResult(
                status=ExecutionPersistenceResultStatus.NOT_FOUND,
                schema_version=CURRENT_SCHEMA_VERSION,
            )
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.LOADED,
            record_fingerprint=record.record_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )

    def load_record(
        self, aggregate_id: PaperExecutionAggregateId
    ) -> ExecutionAggregateRecord | None:
        row = self._row(
            "SELECT * FROM execution_aggregates WHERE aggregate_id = ?",
            (str(aggregate_id),),
        )
        return _aggregate_from_row(row) if row is not None else None

    def save(
        self,
        record: ExecutionAggregateRecord,
        *,
        expected_revision: PaperExecutionRevision,
    ) -> AggregateSaveResult:
        existing = self.load_record(record.aggregate_id)
        result = _aggregate_save_result(record, existing, expected_revision)
        if result.conflict is not None:
            self._transaction.mark_conflict(result.conflict)
            return result
        if result.status is ExecutionPersistenceResultStatus.CREATED:
            self._transaction.execute(_AGGREGATE_INSERT, _aggregate_values(record))
        elif result.status is ExecutionPersistenceResultStatus.SAVED:
            values = _aggregate_values(record)
            cursor = self._transaction.execute(
                _AGGREGATE_UPDATE,
                values[1:] + (values[0], int(expected_revision)),
            )
            if cursor.rowcount != 1:
                conflict = _conflict(
                    kind=ExecutionPersistenceConflictKind.STALE_REVISION,
                    code="STALE_AGGREGATE_REVISION",
                    safe_message="Aggregate revision changed before save.",
                    aggregate_id=record.aggregate_id,
                    expected_revision=expected_revision,
                )
                self._transaction.mark_conflict(conflict)
                return AggregateSaveResult(
                    status=ExecutionPersistenceResultStatus.STALE_REVISION,
                    aggregate_id=record.aggregate_id,
                    expected_revision=expected_revision,
                    current_revision=None,
                    conflict=conflict,
                    schema_version=CURRENT_SCHEMA_VERSION,
                )
        return result

    def _save_dispatch_outcome(
        self,
        record: ExecutionAggregateRecord,
        *,
        expected_revision: PaperExecutionRevision,
        revision_increment: int,
    ) -> AggregateSaveResult:
        """Persist the final snapshot for one validated transition chain."""
        existing = self.load_record(record.aggregate_id)
        if (
            existing is None
            or existing.execution_revision != expected_revision
            or existing.aggregate_terminal
            or revision_increment < 1
            or int(record.execution_revision)
            != int(expected_revision) + revision_increment
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
            self._transaction.mark_conflict(conflict)
            return AggregateSaveResult(
                status=ExecutionPersistenceResultStatus.STALE_REVISION,
                aggregate_id=record.aggregate_id,
                expected_revision=expected_revision,
                current_revision=actual_revision,
                conflict=conflict,
                schema_version=CURRENT_SCHEMA_VERSION,
            )
        values = _aggregate_values(record)
        cursor = self._transaction.execute(
            _AGGREGATE_UPDATE,
            values[1:] + (values[0], int(expected_revision)),
        )
        if cursor.rowcount != 1:
            conflict = _conflict(
                kind=ExecutionPersistenceConflictKind.STALE_REVISION,
                code="STALE_AGGREGATE_REVISION",
                safe_message="Aggregate revision changed before outcome save.",
                aggregate_id=record.aggregate_id,
                expected_revision=expected_revision,
            )
            self._transaction.mark_conflict(conflict)
            return AggregateSaveResult(
                status=ExecutionPersistenceResultStatus.STALE_REVISION,
                aggregate_id=record.aggregate_id,
                expected_revision=expected_revision,
                current_revision=None,
                conflict=conflict,
                schema_version=CURRENT_SCHEMA_VERSION,
            )
        return AggregateSaveResult(
            status=ExecutionPersistenceResultStatus.SAVED,
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            current_revision=record.execution_revision,
            aggregate_fingerprint=record.record_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )


class SqliteExecutionCommandRepository(_RepositoryBase):
    """SQLite implementation of immutable command registration and replay."""

    def get(self, command_id: PaperExecutionCommandId) -> RecordLoadResult:
        record = self.load_record(command_id)
        if record is None:
            return RecordLoadResult(
                status=ExecutionPersistenceResultStatus.NOT_FOUND,
                schema_version=CURRENT_SCHEMA_VERSION,
            )
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.LOADED,
            record_fingerprint=record.record_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )

    def load_record(
        self, command_id: PaperExecutionCommandId
    ) -> ExecutionCommandRecord | None:
        row = self._row(
            "SELECT * FROM execution_commands WHERE command_id = ?", (str(command_id),)
        )
        return _command_from_row(row) if row is not None else None

    def register(self, record: ExecutionCommandRecord) -> CommandRegistrationResult:
        existing = self.load_record(record.command_id)
        result = _command_result(record, existing)
        if result.conflict is not None:
            self._transaction.mark_conflict(result.conflict)
        elif result.status is ExecutionPersistenceResultStatus.CREATED:
            self._transaction.execute(_COMMAND_INSERT, _command_values(record))
        return result

    def lookup_replay(
        self, command_id: PaperExecutionCommandId, payload_fingerprint: str
    ) -> ReplayLookupResult:
        existing = self.load_record(command_id)
        if existing is None:
            return ReplayLookupResult(
                status=ExecutionPersistenceResultStatus.NOT_FOUND,
                replay_kind=ExecutionReplayKind.NONE,
                schema_version=CURRENT_SCHEMA_VERSION,
            )
        if existing.canonical_payload_fingerprint == payload_fingerprint:
            return ReplayLookupResult(
                status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
                replay_kind=ExecutionReplayKind.EXACT_COMMAND,
                original_command_id=existing.command_id,
                original_result_fingerprint=existing.record_fingerprint,
                schema_version=CURRENT_SCHEMA_VERSION,
            )
        conflict = _conflict(
            kind=ExecutionPersistenceConflictKind.COMMAND_PAYLOAD_CONFLICT,
            code="COMMAND_PAYLOAD_CONFLICT",
            safe_message="Command identity already exists with different payload.",
            aggregate_id=existing.aggregate_id,
            command_id=command_id,
        )
        return ReplayLookupResult(
            status=ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
            replay_kind=ExecutionReplayKind.NONE,
            conflict=conflict,
            schema_version=CURRENT_SCHEMA_VERSION,
        )


class SqliteExecutionIdempotencyRepository(_RepositoryBase):
    """SQLite implementation of permanent logical-operation reservations."""

    def get(self, key: PaperExecutionIdempotencyKey) -> RecordLoadResult:
        record = self.load_record(key)
        if record is None:
            return RecordLoadResult(
                status=ExecutionPersistenceResultStatus.NOT_FOUND,
                schema_version=CURRENT_SCHEMA_VERSION,
            )
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.LOADED,
            record_fingerprint=record.record_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )

    def load_record(
        self, key: PaperExecutionIdempotencyKey
    ) -> ExecutionIdempotencyRecord | None:
        row = self._row(
            "SELECT * FROM execution_idempotency WHERE idempotency_key = ?", (str(key),)
        )
        return _idempotency_from_row(row) if row is not None else None

    def reserve(
        self, record: ExecutionIdempotencyRecord
    ) -> IdempotencyReservationResult:
        existing = self.load_record(record.idempotency_key)
        result = _idempotency_result(record, existing)
        if result.conflict is not None:
            self._transaction.mark_conflict(result.conflict)
        elif result.status is ExecutionPersistenceResultStatus.CREATED:
            self._transaction.execute(_IDEMPOTENCY_INSERT, _idempotency_values(record))
        return result


class SqliteExecutionTransitionJournal(_RepositoryBase):
    """Append-only SQLite lifecycle transition journal."""

    def load_record(
        self, transition_record_id: str
    ) -> ExecutionTransitionRecord | None:
        row = self._row(
            "SELECT * FROM execution_transitions WHERE transition_record_id = ?",
            (transition_record_id,),
        )
        return _transition_from_row(row) if row is not None else None

    def append(self, record: ExecutionTransitionRecord) -> TransitionAppendResult:
        existing = self.load_record(record.transition_record_id)
        if existing is not None:
            if existing.record_fingerprint == record.record_fingerprint:
                return TransitionAppendResult(
                    status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
                    aggregate_id=record.aggregate_id,
                    previous_revision=record.previous_revision,
                    next_revision=record.next_revision,
                    transition_fingerprint=existing.record_fingerprint,
                    schema_version=CURRENT_SCHEMA_VERSION,
                )
            return self._blocked(
                record,
                existing,
                code="TRANSITION_RECORD_CONFLICT",
                safe_message="Transition record identity already exists with different content.",
            )
        revision_row = self._row(
            "SELECT * FROM execution_transitions WHERE aggregate_id = ? AND next_revision = ?",
            (str(record.aggregate_id), int(record.next_revision)),
        )
        if revision_row is not None:
            return self._blocked(
                record,
                _transition_from_row(revision_row),
                code="TRANSITION_REVISION_CONFLICT",
                safe_message="Transition revision is already owned by another record.",
            )
        identity_row = self._row(
            "SELECT * FROM execution_transitions WHERE aggregate_id = ? AND transition_id = ?",
            (str(record.aggregate_id), record.transition_id),
        )
        if identity_row is not None:
            return self._blocked(
                record,
                _transition_from_row(identity_row),
                code="TRANSITION_ID_CONFLICT",
                safe_message="Transition identity is already owned by another record.",
            )
        self._transaction.execute(_TRANSITION_INSERT, _transition_values(record))
        return TransitionAppendResult(
            status=ExecutionPersistenceResultStatus.APPENDED,
            aggregate_id=record.aggregate_id,
            previous_revision=record.previous_revision,
            next_revision=record.next_revision,
            transition_fingerprint=record.record_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )

    def _blocked(
        self,
        record: ExecutionTransitionRecord,
        existing: ExecutionTransitionRecord,
        *,
        code: str,
        safe_message: str,
    ) -> TransitionAppendResult:
        conflict = _conflict(
            kind=ExecutionPersistenceConflictKind.TRANSITION_REVISION_CONFLICT,
            code=code,
            safe_message=safe_message,
            aggregate_id=record.aggregate_id,
            command_id=record.command_id,
            expected_revision=record.previous_revision,
            actual_revision=existing.next_revision,
        )
        self._transaction.mark_conflict(conflict)
        return TransitionAppendResult(
            status=ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
            aggregate_id=record.aggregate_id,
            previous_revision=record.previous_revision,
            next_revision=None,
            conflict=conflict,
            schema_version=CURRENT_SCHEMA_VERSION,
        )


class SqliteExecutionBrokerReferenceRepository(_RepositoryBase):
    """SQLite broker-reference identity registry."""

    def load_record(
        self, reference: PaperBrokerOrderReference
    ) -> ExecutionBrokerReferenceRecord | None:
        row = self._row(
            "SELECT * FROM execution_broker_references WHERE broker_reference = ?",
            (str(reference),),
        )
        return _broker_reference_from_row(row) if row is not None else None

    def get(self, reference: PaperBrokerOrderReference) -> RecordLoadResult:
        return _load_result(self.load_record(reference))

    def register(self, record: ExecutionBrokerReferenceRecord) -> RecordLoadResult:
        existing = self.load_record(record.broker_reference)
        if existing is not None:
            return _immutable_record_result(
                self._transaction,
                record,
                existing,
                ExecutionPersistenceConflictKind.BROKER_REFERENCE_CONFLICT,
                ExecutionPersistenceResultStatus.DUPLICATE_BROKER_REFERENCE,
                "BROKER_REFERENCE_CONFLICT",
                "Broker reference is already bound to another record.",
                aggregate_id=existing.aggregate_id,
                command_id=existing.command_id,
            )
        if record.active:
            row = self._row(
                "SELECT * FROM execution_broker_references WHERE aggregate_id = ? AND active = 1",
                (str(record.aggregate_id),),
            )
            if row is not None:
                return _immutable_record_result(
                    self._transaction,
                    record,
                    _broker_reference_from_row(row),
                    ExecutionPersistenceConflictKind.BROKER_REFERENCE_CONFLICT,
                    ExecutionPersistenceResultStatus.DUPLICATE_BROKER_REFERENCE,
                    "ACTIVE_BROKER_REFERENCE_CONFLICT",
                    "Aggregate already has an active broker reference.",
                    aggregate_id=record.aggregate_id,
                    command_id=record.command_id,
                )
        self._transaction.execute(
            _BROKER_REFERENCE_INSERT, _broker_reference_values(record)
        )
        return _created_result(record.record_fingerprint)


class SqliteExecutionReceiptRepository(_RepositoryBase):
    def load_record(self, fingerprint: str) -> ExecutionReceiptRecord | None:
        row = self._row(
            "SELECT * FROM execution_receipts WHERE receipt_fingerprint = ?",
            (fingerprint,),
        )
        return _receipt_from_row(row) if row is not None else None

    def record(self, receipt: ExecutionReceiptRecord) -> RecordLoadResult:
        key = receipt.receipt.receipt_fingerprint
        existing = self.load_record(key)
        if existing is not None:
            return _immutable_record_result(
                self._transaction,
                receipt,
                existing,
                code="RECEIPT_CONFLICT",
                message="Receipt record fingerprint conflict.",
                aggregate_id=receipt.receipt.aggregate_id,
                command_id=receipt.receipt.command_id,
            )
        self._transaction.execute(_RECEIPT_INSERT, _receipt_values(receipt))
        return _created_result(receipt.record_fingerprint)


class SqliteExecutionFailureRepository(_RepositoryBase):
    def load_record(self, fingerprint: str) -> ExecutionFailureRecord | None:
        row = self._row(
            "SELECT * FROM execution_failures WHERE failure_fingerprint = ?",
            (fingerprint,),
        )
        return _failure_from_row(row) if row is not None else None

    def record(self, failure: ExecutionFailureRecord) -> RecordLoadResult:
        key = failure.failure.failure_fingerprint
        existing = self.load_record(key)
        if existing is not None:
            return _immutable_record_result(
                self._transaction,
                failure,
                existing,
                code="FAILURE_CONFLICT",
                message="Failure record fingerprint conflict.",
                aggregate_id=failure.failure.aggregate_id,
                command_id=failure.failure.command_id,
            )
        self._transaction.execute(_FAILURE_INSERT, _failure_values(failure))
        return _created_result(failure.record_fingerprint)


class SqliteExecutionApprovalRepository(_RepositoryBase):
    def load_record(self, fingerprint: str) -> ExecutionApprovalRecord | None:
        row = self._row(
            "SELECT * FROM execution_approvals WHERE approval_fingerprint = ?",
            (fingerprint,),
        )
        return _approval_from_row(row) if row is not None else None

    def record(self, approval: ExecutionApprovalRecord) -> RecordLoadResult:
        existing = self.load_record(approval.approval_fingerprint)
        if existing is not None:
            return _immutable_record_result(
                self._transaction,
                approval,
                existing,
                code="APPROVAL_CONFLICT",
                message="Approval identity already exists with different content.",
            )
        self._transaction.execute(_APPROVAL_INSERT, _approval_values(approval))
        return _created_result(approval.record_fingerprint)


class SqliteExecutionReconciliationRepository(_RepositoryBase):
    def load_record(
        self, reconciliation_id: str
    ) -> ExecutionReconciliationRecord | None:
        row = self._row(
            "SELECT * FROM execution_reconciliations WHERE reconciliation_id = ?",
            (reconciliation_id,),
        )
        return _reconciliation_from_row(row) if row is not None else None

    def record(self, reconciliation: ExecutionReconciliationRecord) -> RecordLoadResult:
        existing = self.load_record(reconciliation.reconciliation_id)
        if existing is not None:
            return _immutable_record_result(
                self._transaction,
                reconciliation,
                existing,
                code="RECONCILIATION_CONFLICT",
                message="Reconciliation identity already exists with different content.",
                aggregate_id=reconciliation.aggregate_id,
            )
        self._transaction.execute(
            _RECONCILIATION_INSERT, _reconciliation_values(reconciliation)
        )
        return _created_result(reconciliation.record_fingerprint)


class SqliteExecutionRestartDiscoveryRepository(_RepositoryBase):
    """Deterministic consequential aggregate discovery."""

    def discover(self, query: ExecutionRestartDiscoveryQuery) -> RestartDiscoveryResult:
        clauses = [
            "mode = ?",
            "lifecycle_state IN (%s)" % ", ".join("?" for _ in query.lifecycle_states),
        ]
        values: list[object] = [
            query.mode.value,
            *(state.value for state in query.lifecycle_states),
        ]
        if not query.include_outcome_unknown:
            clauses.append("outcome_unknown = 0")
        if not query.include_reconciliation_required:
            clauses.append("reconciliation_required = 0")
        if query.minimum_updated_at is not None:
            clauses.append("updated_at >= ?")
            values.append(_timestamp(query.minimum_updated_at))
        if query.maximum_updated_at is not None:
            clauses.append("updated_at <= ?")
            values.append(_timestamp(query.maximum_updated_at))
        statement = (
            "SELECT * FROM execution_aggregates WHERE "
            + " AND ".join(clauses)
            + " ORDER BY aggregate_id"
        )
        rows = self._transaction.execute(statement, tuple(values)).fetchall()
        offset = _cursor_offset(query.cursor, query, len(rows))
        remaining = rows[offset:]
        complete = query.limit is None or len(remaining) <= query.limit
        selected = remaining if query.limit is None else remaining[: query.limit]
        records = tuple(_aggregate_from_row(row) for row in selected)
        return RestartDiscoveryResult(
            aggregates=records,
            complete=complete,
            next_cursor=(
                None
                if complete or query.limit is None
                else _cursor_token(query, offset + query.limit)
            ),
            query_fingerprint=query.query_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )


def _aggregate_save_result(
    record: ExecutionAggregateRecord,
    existing: ExecutionAggregateRecord | None,
    expected_revision: PaperExecutionRevision,
) -> AggregateSaveResult:
    if existing is None:
        if int(expected_revision) != 0 or int(record.execution_revision) != 0:
            conflict = _conflict(
                kind=ExecutionPersistenceConflictKind.STALE_REVISION,
                code="AGGREGATE_NOT_FOUND_FOR_REVISION",
                safe_message="Aggregate does not exist at expected revision.",
                aggregate_id=record.aggregate_id,
                expected_revision=expected_revision,
            )
            return AggregateSaveResult(
                status=ExecutionPersistenceResultStatus.STALE_REVISION,
                aggregate_id=record.aggregate_id,
                expected_revision=expected_revision,
                current_revision=None,
                conflict=conflict,
                schema_version=CURRENT_SCHEMA_VERSION,
            )
        return AggregateSaveResult(
            status=ExecutionPersistenceResultStatus.CREATED,
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            current_revision=record.execution_revision,
            aggregate_fingerprint=record.record_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
    if existing.aggregate_terminal:
        conflict = _conflict(
            kind=ExecutionPersistenceConflictKind.TERMINAL_STATE_CONFLICT,
            code="AGGREGATE_TERMINAL",
            safe_message="Terminal aggregate cannot be updated.",
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            actual_revision=existing.execution_revision,
        )
        return AggregateSaveResult(
            status=ExecutionPersistenceResultStatus.ALREADY_TERMINAL,
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            current_revision=existing.execution_revision,
            conflict=conflict,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
    if existing.execution_revision != expected_revision:
        conflict = _conflict(
            kind=ExecutionPersistenceConflictKind.STALE_REVISION,
            code="STALE_AGGREGATE_REVISION",
            safe_message="Aggregate revision changed before save.",
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            actual_revision=existing.execution_revision,
        )
        return AggregateSaveResult(
            status=ExecutionPersistenceResultStatus.STALE_REVISION,
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            current_revision=existing.execution_revision,
            conflict=conflict,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
    if existing.record_fingerprint == record.record_fingerprint:
        return AggregateSaveResult(
            status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            current_revision=existing.execution_revision,
            aggregate_fingerprint=existing.record_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
    if int(record.execution_revision) != int(expected_revision) + 1:
        conflict = _conflict(
            kind=ExecutionPersistenceConflictKind.STALE_REVISION,
            code="NON_SEQUENTIAL_AGGREGATE_REVISION",
            safe_message="Aggregate revision must advance by exactly one.",
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            actual_revision=record.execution_revision,
        )
        return AggregateSaveResult(
            status=ExecutionPersistenceResultStatus.STALE_REVISION,
            aggregate_id=record.aggregate_id,
            expected_revision=expected_revision,
            current_revision=existing.execution_revision,
            conflict=conflict,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
    return AggregateSaveResult(
        status=ExecutionPersistenceResultStatus.SAVED,
        aggregate_id=record.aggregate_id,
        expected_revision=expected_revision,
        current_revision=record.execution_revision,
        aggregate_fingerprint=record.record_fingerprint,
        schema_version=CURRENT_SCHEMA_VERSION,
    )


def _command_result(
    record: ExecutionCommandRecord, existing: ExecutionCommandRecord | None
) -> CommandRegistrationResult:
    if existing is None:
        return CommandRegistrationResult(
            status=ExecutionPersistenceResultStatus.CREATED,
            command_id=record.command_id,
            command_fingerprint=record.record_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
    if existing.canonical_payload_fingerprint == record.canonical_payload_fingerprint:
        return CommandRegistrationResult(
            status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
            command_id=record.command_id,
            command_fingerprint=existing.record_fingerprint,
            original_command_id=existing.command_id,
            original_result_fingerprint=existing.record_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
    conflict = _conflict(
        kind=ExecutionPersistenceConflictKind.COMMAND_PAYLOAD_CONFLICT,
        code="COMMAND_PAYLOAD_CONFLICT",
        safe_message="Command identity already exists with different payload.",
        aggregate_id=existing.aggregate_id,
        command_id=record.command_id,
    )
    return CommandRegistrationResult(
        status=ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
        command_id=record.command_id,
        conflict=conflict,
        schema_version=CURRENT_SCHEMA_VERSION,
    )


def _idempotency_result(
    record: ExecutionIdempotencyRecord, existing: ExecutionIdempotencyRecord | None
) -> IdempotencyReservationResult:
    if existing is None:
        return IdempotencyReservationResult(
            status=ExecutionPersistenceResultStatus.CREATED,
            idempotency_key=record.idempotency_key,
            reservation_fingerprint=record.record_fingerprint,
            original_command_id=record.command_id,
            original_result_fingerprint=record.original_result_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
    if existing.logical_operation_fingerprint == record.logical_operation_fingerprint:
        return IdempotencyReservationResult(
            status=ExecutionPersistenceResultStatus.LOGICAL_REPLAY,
            idempotency_key=record.idempotency_key,
            reservation_fingerprint=existing.record_fingerprint,
            original_command_id=existing.command_id,
            original_result_fingerprint=existing.original_result_fingerprint
            or existing.record_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
    conflict = _conflict(
        kind=ExecutionPersistenceConflictKind.IDEMPOTENCY_PAYLOAD_CONFLICT,
        code="IDEMPOTENCY_PAYLOAD_CONFLICT",
        safe_message="Idempotency key already refers to another operation.",
        aggregate_id=existing.aggregate_id,
        command_id=record.command_id,
        idempotency_key=record.idempotency_key,
    )
    return IdempotencyReservationResult(
        status=ExecutionPersistenceResultStatus.IDEMPOTENCY_CONFLICT,
        idempotency_key=record.idempotency_key,
        conflict=conflict,
        schema_version=CURRENT_SCHEMA_VERSION,
    )


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _dispatch_claim_from_row(row: sqlite3.Row) -> ExecutionDispatchClaimRecord:
    return ExecutionDispatchClaimRecord(
        claim_token=row["claim_token"],
        submission_id=row["submission_id"],
        command_id=PaperExecutionCommandId(row["command_id"]),
        aggregate_id=PaperExecutionAggregateId(row["aggregate_id"]),
        correlation_id=PaperExecutionCorrelationId(row["correlation_id"]),
        idempotency_key=PaperExecutionIdempotencyKey(row["idempotency_key"]),
        expected_execution_revision=PaperExecutionRevision(
            row["expected_execution_revision"]
        ),
        request_fingerprint=row["request_fingerprint"],
        command_record_fingerprint=row["command_record_fingerprint"],
        canonical_payload_fingerprint=row["canonical_payload_fingerprint"],
        approval_fingerprint=row["approval_fingerprint"],
        policy_fingerprint=row["policy_fingerprint"],
        client_order_id=row["client_order_id"],
        capability_verifier=row["capability_verifier"],
        canonical_order_json=row["canonical_order_json"],
        control_generation=int(row["control_generation"]),
        claimed_at=_parse_timestamp(row["claimed_at"]),
        schema_version=int(row["schema_version"]),
    )


def _aggregate_values(record: ExecutionAggregateRecord) -> tuple[object, ...]:
    return (
        str(record.aggregate_id),
        str(record.correlation_id),
        record.lifecycle_state.value,
        int(record.execution_revision),
        str(record.cumulative_filled_quantity),
        None if record.requested_quantity is None else str(record.requested_quantity),
        (
            None
            if record.active_broker_reference is None
            else str(record.active_broker_reference)
        ),
        int(record.outcome_unknown),
        int(record.reconciliation_required),
        int(record.command_terminal),
        int(record.aggregate_terminal),
        record.last_transition_id,
        None if record.last_command_id is None else str(record.last_command_id),
        (
            None
            if record.last_idempotency_key is None
            else str(record.last_idempotency_key)
        ),
        record.last_receipt_fingerprint,
        record.last_failure_fingerprint,
        record.mode.value,
        _timestamp(record.created_at),
        _timestamp(record.updated_at),
        str(record.schema_version),
        record.record_fingerprint,
    )


def _command_values(record: ExecutionCommandRecord) -> tuple[object, ...]:
    return (
        str(record.command_id),
        str(record.aggregate_id),
        str(record.correlation_id),
        str(record.idempotency_key),
        record.operation.value,
        int(record.expected_execution_revision),
        record.canonical_payload_fingerprint,
        record.canonical_command_json,
        record.approval_fingerprint,
        record.policy_fingerprint,
        _timestamp(record.received_at),
        record.processing_outcome.value,
        record.mode.value,
        str(record.schema_version),
        record.record_fingerprint,
    )


def _idempotency_values(record: ExecutionIdempotencyRecord) -> tuple[object, ...]:
    return (
        str(record.idempotency_key),
        record.logical_operation_fingerprint,
        str(record.command_id),
        str(record.aggregate_id),
        record.reservation_status.value,
        record.original_result_fingerprint,
        _timestamp(record.created_at),
        None if record.resolved_at is None else _timestamp(record.resolved_at),
        int(record.conflict),
        record.mode.value,
        str(record.schema_version),
        record.record_fingerprint,
    )


def _aggregate_from_row(row: sqlite3.Row) -> ExecutionAggregateRecord:
    return ExecutionAggregateRecord(
        aggregate_id=PaperExecutionAggregateId(str(row["aggregate_id"])),
        correlation_id=PaperExecutionCorrelationId(str(row["correlation_id"])),
        lifecycle_state=PaperExecutionLifecycleState(str(row["lifecycle_state"])),
        execution_revision=PaperExecutionRevision(int(row["execution_revision"])),
        cumulative_filled_quantity=Decimal(str(row["cumulative_filled_quantity"])),
        requested_quantity=(
            None
            if row["requested_quantity"] is None
            else Decimal(str(row["requested_quantity"]))
        ),
        active_broker_reference=(
            None
            if row["active_broker_reference"] is None
            else PaperBrokerOrderReference(str(row["active_broker_reference"]))
        ),
        outcome_unknown=bool(row["outcome_unknown"]),
        reconciliation_required=bool(row["reconciliation_required"]),
        command_terminal=bool(row["command_terminal"]),
        aggregate_terminal=bool(row["aggregate_terminal"]),
        last_transition_id=str(row["last_transition_id"]),
        created_at=_parse_timestamp(str(row["created_at"])),
        updated_at=_parse_timestamp(str(row["updated_at"])),
        schema_version=int(str(row["schema_version"])),
        last_command_id=(
            None
            if row["last_command_id"] is None
            else PaperExecutionCommandId(str(row["last_command_id"]))
        ),
        last_idempotency_key=(
            None
            if row["last_idempotency_key"] is None
            else PaperExecutionIdempotencyKey(str(row["last_idempotency_key"]))
        ),
        last_receipt_fingerprint=row["last_receipt_fingerprint"],
        last_failure_fingerprint=row["last_failure_fingerprint"],
        mode=PaperExecutionMode(str(row["mode"])),
    )


def _command_from_row(row: sqlite3.Row) -> ExecutionCommandRecord:
    return ExecutionCommandRecord(
        command_id=PaperExecutionCommandId(str(row["command_id"])),
        aggregate_id=PaperExecutionAggregateId(str(row["aggregate_id"])),
        correlation_id=PaperExecutionCorrelationId(str(row["correlation_id"])),
        idempotency_key=PaperExecutionIdempotencyKey(str(row["idempotency_key"])),
        operation=PaperExecutionOperation(str(row["operation"])),
        expected_execution_revision=PaperExecutionRevision(
            int(row["expected_execution_revision"])
        ),
        canonical_payload_fingerprint=str(row["canonical_payload_fingerprint"]),
        canonical_command_json=str(row["canonical_command_json"]),
        approval_fingerprint=str(row["approval_fingerprint"]),
        policy_fingerprint=str(row["policy_fingerprint"]),
        received_at=_parse_timestamp(str(row["received_at"])),
        processing_outcome=ExecutionCommandProcessingOutcome(
            str(row["processing_outcome"])
        ),
        schema_version=int(str(row["schema_version"])),
        mode=PaperExecutionMode(str(row["mode"])),
    )


def _idempotency_from_row(row: sqlite3.Row) -> ExecutionIdempotencyRecord:
    return ExecutionIdempotencyRecord(
        idempotency_key=PaperExecutionIdempotencyKey(str(row["idempotency_key"])),
        logical_operation_fingerprint=str(row["logical_operation_fingerprint"]),
        command_id=PaperExecutionCommandId(str(row["command_id"])),
        aggregate_id=PaperExecutionAggregateId(str(row["aggregate_id"])),
        reservation_status=ExecutionIdempotencyReservationStatus(
            str(row["reservation_status"])
        ),
        original_result_fingerprint=row["original_result_fingerprint"],
        created_at=_parse_timestamp(str(row["created_at"])),
        resolved_at=(
            None
            if row["resolved_at"] is None
            else _parse_timestamp(str(row["resolved_at"]))
        ),
        conflict=bool(row["conflict"]),
        schema_version=int(str(row["schema_version"])),
        mode=PaperExecutionMode(str(row["mode"])),
    )


def _created_result(fingerprint: str) -> RecordLoadResult:
    return RecordLoadResult(
        status=ExecutionPersistenceResultStatus.CREATED,
        record_fingerprint=fingerprint,
        schema_version=CURRENT_SCHEMA_VERSION,
    )


def _load_result(record: object | None) -> RecordLoadResult:
    return RecordLoadResult(
        status=(
            ExecutionPersistenceResultStatus.NOT_FOUND
            if record is None
            else ExecutionPersistenceResultStatus.LOADED
        ),
        record_fingerprint=(
            None if record is None else str(getattr(record, "record_fingerprint"))
        ),
        schema_version=CURRENT_SCHEMA_VERSION,
    )


def _immutable_record_result(
    transaction: "_SqliteExecutionTransaction",
    record: object,
    existing: object,
    kind: ExecutionPersistenceConflictKind = ExecutionPersistenceConflictKind.RECORD_VERSION_CONFLICT,
    status: ExecutionPersistenceResultStatus = ExecutionPersistenceResultStatus.COMMAND_CONFLICT,
    code: str = "IMMUTABLE_RECORD_CONFLICT",
    message: str = "Record identity already exists with different content.",
    aggregate_id: PaperExecutionAggregateId | None = None,
    command_id: PaperExecutionCommandId | None = None,
) -> RecordLoadResult:
    existing_fingerprint = str(getattr(existing, "record_fingerprint"))
    if existing_fingerprint == str(getattr(record, "record_fingerprint")):
        return RecordLoadResult(
            status=ExecutionPersistenceResultStatus.EXACT_REPLAY,
            record_fingerprint=existing_fingerprint,
            schema_version=CURRENT_SCHEMA_VERSION,
        )
    conflict = _conflict(
        kind=kind,
        code=code,
        safe_message=message,
        aggregate_id=aggregate_id,
        command_id=command_id,
    )
    transaction.mark_conflict(conflict)
    return RecordLoadResult(
        status=status,
        conflict=conflict,
        record_fingerprint=existing_fingerprint,
        schema_version=CURRENT_SCHEMA_VERSION,
    )


def _enum_json(values: tuple[object, ...]) -> str:
    return json.dumps(
        [str(getattr(value, "value")) for value in values], separators=(",", ":")
    )


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


def _transition_values(record: ExecutionTransitionRecord) -> tuple[object, ...]:
    return (
        record.transition_record_id,
        str(record.aggregate_id),
        record.transition_id,
        record.source_state.value,
        record.destination_state.value,
        int(record.previous_revision),
        int(record.next_revision),
        record.lifecycle_input_kind.value,
        record.input_identity,
        str(record.command_id),
        str(record.correlation_id),
        str(record.idempotency_key),
        record.broker_observation_identity,
        record.receipt_fingerprint,
        record.failure_fingerprint,
        record.replay_indicator.value,
        _enum_json(record.side_effect_intent_kinds),
        _enum_json(record.evidence_intent_kinds),
        record.safe_reason_code,
        record.mode.value,
        _timestamp(record.recorded_at),
        str(record.schema_version),
        record.record_fingerprint,
    )


def _transition_from_row(row: sqlite3.Row) -> ExecutionTransitionRecord:
    return ExecutionTransitionRecord(
        transition_record_id=str(row["transition_record_id"]),
        aggregate_id=PaperExecutionAggregateId(str(row["aggregate_id"])),
        transition_id=str(row["transition_id"]),
        source_state=PaperExecutionLifecycleState(str(row["source_state"])),
        destination_state=PaperExecutionLifecycleState(str(row["destination_state"])),
        previous_revision=PaperExecutionRevision(int(row["previous_revision"])),
        next_revision=PaperExecutionRevision(int(row["next_revision"])),
        lifecycle_input_kind=PaperExecutionLifecycleInputType(
            str(row["lifecycle_input_kind"])
        ),
        input_identity=str(row["input_identity"]),
        command_id=PaperExecutionCommandId(str(row["command_id"])),
        correlation_id=PaperExecutionCorrelationId(str(row["correlation_id"])),
        idempotency_key=PaperExecutionIdempotencyKey(str(row["idempotency_key"])),
        replay_indicator=ExecutionReplayKind(str(row["replay_indicator"])),
        side_effect_intent_kinds=tuple(
            PaperExecutionLifecycleSideEffectIntentKind(value)
            for value in json.loads(str(row["side_effect_intent_kinds_json"]))
        ),
        evidence_intent_kinds=tuple(
            PaperExecutionLifecycleEvidenceIntentKind(value)
            for value in json.loads(str(row["evidence_intent_kinds_json"]))
        ),
        safe_reason_code=str(row["safe_reason_code"]),
        recorded_at=_parse_timestamp(str(row["recorded_at"])),
        schema_version=int(str(row["schema_version"])),
        broker_observation_identity=row["broker_observation_identity"],
        receipt_fingerprint=row["receipt_fingerprint"],
        failure_fingerprint=row["failure_fingerprint"],
        mode=PaperExecutionMode(str(row["mode"])),
    )


def _broker_reference_values(
    record: ExecutionBrokerReferenceRecord,
) -> tuple[object, ...]:
    return (
        str(record.broker_reference),
        str(record.aggregate_id),
        str(record.command_id),
        record.adapter_identity,
        record.reference_status.value,
        _timestamp(record.first_seen_at),
        _timestamp(record.last_seen_at),
        int(record.active),
        (
            None
            if record.replaced_by_reference is None
            else str(record.replaced_by_reference)
        ),
        record.mode.value,
        str(record.schema_version),
        record.record_fingerprint,
    )


def _broker_reference_from_row(row: sqlite3.Row) -> ExecutionBrokerReferenceRecord:
    return ExecutionBrokerReferenceRecord(
        broker_reference=PaperBrokerOrderReference(str(row["broker_reference"])),
        aggregate_id=PaperExecutionAggregateId(str(row["aggregate_id"])),
        command_id=PaperExecutionCommandId(str(row["command_id"])),
        adapter_identity=str(row["adapter_identity"]),
        reference_status=ExecutionBrokerReferenceStatus(str(row["reference_status"])),
        first_seen_at=_parse_timestamp(str(row["first_seen_at"])),
        last_seen_at=_parse_timestamp(str(row["last_seen_at"])),
        active=bool(row["active"]),
        schema_version=int(str(row["schema_version"])),
        replaced_by_reference=(
            None
            if row["replaced_by_reference"] is None
            else PaperBrokerOrderReference(str(row["replaced_by_reference"]))
        ),
        mode=PaperExecutionMode(str(row["mode"])),
    )


def _receipt_values(record: ExecutionReceiptRecord) -> tuple[object, ...]:
    value = record.receipt
    return (
        value.receipt_fingerprint,
        str(value.aggregate_id),
        str(value.command_id),
        str(value.correlation_id),
        value.operation.value,
        value.receipt_kind.value,
        value.status.value,
        int(value.observed_execution_revision),
        _timestamp(value.observed_at),
        value.message_code,
        (
            None
            if value.broker_order_reference is None
            else str(value.broker_order_reference)
        ),
        int(value.outcome_known),
        int(value.reconciliation_required),
        _timestamp(record.recorded_at),
        value.mode.value,
        str(record.schema_version),
        record.record_fingerprint,
    )


def _receipt_from_row(row: sqlite3.Row) -> ExecutionReceiptRecord:
    receipt = PaperExecutionReceipt(
        command_id=PaperExecutionCommandId(str(row["command_id"])),
        aggregate_id=PaperExecutionAggregateId(str(row["aggregate_id"])),
        correlation_id=PaperExecutionCorrelationId(str(row["correlation_id"])),
        operation=PaperExecutionOperation(str(row["operation"])),
        receipt_kind=PaperExecutionReceiptKind(str(row["receipt_kind"])),
        status=PaperExecutionStatus(str(row["status"])),
        observed_execution_revision=PaperExecutionRevision(
            int(row["observed_execution_revision"])
        ),
        observed_at=_parse_timestamp(str(row["observed_at"])),
        message_code=str(row["message_code"]),
        broker_order_reference=(
            None
            if row["broker_reference"] is None
            else PaperBrokerOrderReference(str(row["broker_reference"]))
        ),
        outcome_known=bool(row["outcome_known"]),
        reconciliation_required=bool(row["reconciliation_required"]),
        mode=PaperExecutionMode(str(row["mode"])),
    )
    return ExecutionReceiptRecord(
        receipt=receipt,
        recorded_at=_parse_timestamp(str(row["recorded_at"])),
        schema_version=int(str(row["schema_version"])),
    )


def _failure_values(record: ExecutionFailureRecord) -> tuple[object, ...]:
    value = record.failure
    return (
        value.failure_fingerprint,
        None if value.aggregate_id is None else str(value.aggregate_id),
        None if value.command_id is None else str(value.command_id),
        None if value.correlation_id is None else str(value.correlation_id),
        value.failure_kind.value,
        value.severity.value,
        value.code,
        value.safe_message,
        int(value.retryable),
        int(value.terminal),
        int(value.reconciliation_required),
        int(value.operator_action_required),
        int(value.authority_impacting),
        _timestamp(record.recorded_at),
        PaperExecutionMode.PAPER.value,
        str(record.schema_version),
        record.record_fingerprint,
    )


def _failure_from_row(row: sqlite3.Row) -> ExecutionFailureRecord:
    failure = PaperExecutionFailure(
        failure_kind=PaperExecutionFailureKind(str(row["failure_kind"])),
        severity=PaperExecutionFailureSeverity(str(row["severity"])),
        code=str(row["code"]),
        safe_message=str(row["safe_message"]),
        retryable=bool(row["retryable"]),
        terminal=bool(row["terminal"]),
        reconciliation_required=bool(row["reconciliation_required"]),
        operator_action_required=bool(row["operator_action_required"]),
        authority_impacting=bool(row["authority_impacting"]),
        aggregate_id=(
            None
            if row["aggregate_id"] is None
            else PaperExecutionAggregateId(str(row["aggregate_id"]))
        ),
        command_id=(
            None
            if row["command_id"] is None
            else PaperExecutionCommandId(str(row["command_id"]))
        ),
        correlation_id=(
            None
            if row["correlation_id"] is None
            else PaperExecutionCorrelationId(str(row["correlation_id"]))
        ),
    )
    return ExecutionFailureRecord(
        failure=failure,
        recorded_at=_parse_timestamp(str(row["recorded_at"])),
        schema_version=int(str(row["schema_version"])),
    )


def _approval_values(record: ExecutionApprovalRecord) -> tuple[object, ...]:
    return (
        record.approval_fingerprint,
        record.bound_fingerprint,
        record.approval_kind,
        record.approver_safe_reference,
        _timestamp(record.approved_at),
        None if record.expires_at is None else _timestamp(record.expires_at),
        record.revocation_reference,
        _timestamp(record.recorded_at),
        record.mode.value,
        str(record.schema_version),
        record.record_fingerprint,
    )


def _approval_from_row(row: sqlite3.Row) -> ExecutionApprovalRecord:
    return ExecutionApprovalRecord(
        approval_fingerprint=str(row["approval_fingerprint"]),
        bound_fingerprint=str(row["bound_fingerprint"]),
        approval_kind=str(row["approval_kind"]),
        approver_safe_reference=str(row["approver_safe_reference"]),
        approved_at=_parse_timestamp(str(row["approved_at"])),
        recorded_at=_parse_timestamp(str(row["recorded_at"])),
        schema_version=int(str(row["schema_version"])),
        expires_at=(
            None
            if row["expires_at"] is None
            else _parse_timestamp(str(row["expires_at"]))
        ),
        revocation_reference=row["revocation_reference"],
        mode=PaperExecutionMode(str(row["mode"])),
    )


def _reconciliation_values(record: ExecutionReconciliationRecord) -> tuple[object, ...]:
    return (
        record.reconciliation_id,
        str(record.aggregate_id),
        int(record.starting_local_revision),
        record.starting_lifecycle_state.value,
        json.dumps(list(record.broker_observation_references), separators=(",", ":")),
        record.result_classification.value,
        record.resulting_transition_id,
        None if record.resulting_revision is None else int(record.resulting_revision),
        int(record.operator_action_required),
        int(record.unresolved),
        record.safe_reason_code,
        _timestamp(record.recorded_at),
        record.mode.value,
        str(record.schema_version),
        record.record_fingerprint,
    )


def _reconciliation_from_row(row: sqlite3.Row) -> ExecutionReconciliationRecord:
    return ExecutionReconciliationRecord(
        reconciliation_id=str(row["reconciliation_id"]),
        aggregate_id=PaperExecutionAggregateId(str(row["aggregate_id"])),
        starting_local_revision=PaperExecutionRevision(
            int(row["starting_local_revision"])
        ),
        starting_lifecycle_state=PaperExecutionLifecycleState(
            str(row["starting_lifecycle_state"])
        ),
        broker_observation_references=tuple(
            json.loads(str(row["broker_observation_references_json"]))
        ),
        result_classification=ExecutionReconciliationResultClassification(
            str(row["result_classification"])
        ),
        operator_action_required=bool(row["operator_action_required"]),
        unresolved=bool(row["unresolved"]),
        safe_reason_code=str(row["safe_reason_code"]),
        recorded_at=_parse_timestamp(str(row["recorded_at"])),
        schema_version=int(str(row["schema_version"])),
        resulting_transition_id=row["resulting_transition_id"],
        resulting_revision=(
            None
            if row["resulting_revision"] is None
            else PaperExecutionRevision(int(row["resulting_revision"]))
        ),
        mode=PaperExecutionMode(str(row["mode"])),
    )


_AGGREGATE_COLUMNS = "aggregate_id, correlation_id, lifecycle_state, execution_revision, cumulative_filled_quantity, requested_quantity, active_broker_reference, outcome_unknown, reconciliation_required, command_terminal, aggregate_terminal, last_transition_id, last_command_id, last_idempotency_key, last_receipt_fingerprint, last_failure_fingerprint, mode, created_at, updated_at, schema_version, record_fingerprint"
_AGGREGATE_INSERT = f"INSERT INTO execution_aggregates ({_AGGREGATE_COLUMNS}) VALUES ({', '.join('?' for _ in range(21))})"
_AGGREGATE_UPDATE = "UPDATE execution_aggregates SET correlation_id=?, lifecycle_state=?, execution_revision=?, cumulative_filled_quantity=?, requested_quantity=?, active_broker_reference=?, outcome_unknown=?, reconciliation_required=?, command_terminal=?, aggregate_terminal=?, last_transition_id=?, last_command_id=?, last_idempotency_key=?, last_receipt_fingerprint=?, last_failure_fingerprint=?, mode=?, created_at=?, updated_at=?, schema_version=?, record_fingerprint=? WHERE aggregate_id=? AND execution_revision=?"
_AGGREGATE_UPDATE = _AGGREGATE_UPDATE.replace(
    "WHERE aggregate_id=?", "WHERE aggregate_id=?", 1
)
_COMMAND_INSERT = (
    "INSERT INTO execution_commands (command_id, aggregate_id, correlation_id, idempotency_key, operation, expected_execution_revision, canonical_payload_fingerprint, canonical_command_json, approval_fingerprint, policy_fingerprint, received_at, processing_outcome, mode, schema_version, record_fingerprint) VALUES ("
    + ", ".join("?" for _ in range(15))
    + ")"
)
_IDEMPOTENCY_INSERT = (
    "INSERT INTO execution_idempotency (idempotency_key, logical_operation_fingerprint, command_id, aggregate_id, reservation_status, original_result_fingerprint, created_at, resolved_at, conflict, mode, schema_version, record_fingerprint) VALUES ("
    + ", ".join("?" for _ in range(12))
    + ")"
)
_TRANSITION_INSERT = (
    "INSERT INTO execution_transitions (transition_record_id, aggregate_id, transition_id, source_state, destination_state, previous_revision, next_revision, lifecycle_input_kind, input_identity, command_id, correlation_id, idempotency_key, broker_observation_identity, receipt_fingerprint, failure_fingerprint, replay_indicator, side_effect_intent_kinds_json, evidence_intent_kinds_json, safe_reason_code, mode, recorded_at, schema_version, record_fingerprint) VALUES ("
    + ", ".join("?" for _ in range(23))
    + ")"
)
_BROKER_REFERENCE_INSERT = (
    "INSERT INTO execution_broker_references (broker_reference, aggregate_id, command_id, adapter_identity, reference_status, first_seen_at, last_seen_at, active, replaced_by_reference, mode, schema_version, record_fingerprint) VALUES ("
    + ", ".join("?" for _ in range(12))
    + ")"
)
_RECEIPT_INSERT = (
    "INSERT INTO execution_receipts (receipt_fingerprint, aggregate_id, command_id, correlation_id, operation, receipt_kind, status, observed_execution_revision, observed_at, message_code, broker_reference, outcome_known, reconciliation_required, recorded_at, mode, schema_version, record_fingerprint) VALUES ("
    + ", ".join("?" for _ in range(17))
    + ")"
)
_FAILURE_INSERT = (
    "INSERT INTO execution_failures (failure_fingerprint, aggregate_id, command_id, correlation_id, failure_kind, severity, code, safe_message, retryable, terminal, reconciliation_required, operator_action_required, authority_impacting, recorded_at, mode, schema_version, record_fingerprint) VALUES ("
    + ", ".join("?" for _ in range(17))
    + ")"
)
_APPROVAL_INSERT = (
    "INSERT INTO execution_approvals (approval_fingerprint, bound_fingerprint, approval_kind, approver_safe_reference, approved_at, expires_at, revocation_reference, recorded_at, mode, schema_version, record_fingerprint) VALUES ("
    + ", ".join("?" for _ in range(11))
    + ")"
)
_RECONCILIATION_INSERT = (
    "INSERT INTO execution_reconciliations (reconciliation_id, aggregate_id, starting_local_revision, starting_lifecycle_state, broker_observation_references_json, result_classification, resulting_transition_id, resulting_revision, operator_action_required, unresolved, safe_reason_code, recorded_at, mode, schema_version, record_fingerprint) VALUES ("
    + ", ".join("?" for _ in range(15))
    + ")"
)
