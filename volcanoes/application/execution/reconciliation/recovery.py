"""Durable operator-recovery command preparation for Paper reconciliation.

This module prepares only a local immutable command envelope. It performs no
broker I/O, dispatch, lifecycle mutation, commit, retry, or runtime wiring.
"""

from __future__ import annotations

from datetime import datetime

from volcanoes.application.execution._canonical import canonical_json_text
from volcanoes.application.execution.enums import PaperExecutionOperation
from volcanoes.application.execution.fingerprints import fingerprint_payload
from volcanoes.application.execution.identities import (
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionIdempotencyKey,
)
from volcanoes.application.execution.lifecycle.enums import PaperExecutionLifecycleState
from volcanoes.application.execution.persistence.contracts import (
    ExecutionCommandRecord,
    ExecutionReconciliationRecord,
)
from volcanoes.application.execution.persistence.enums import (
    ExecutionCommandProcessingOutcome,
)

from .model import RECOVERY_DESTINATIONS


def build_operator_recovery_command_record(
    *,
    reconciliation: ExecutionReconciliationRecord,
    destination: PaperExecutionLifecycleState,
    command_id: PaperExecutionCommandId,
    correlation_id: PaperExecutionCorrelationId,
    idempotency_key: PaperExecutionIdempotencyKey,
    approval_fingerprint: str,
    policy_fingerprint: str,
    received_at: datetime,
    schema_version: int,
) -> ExecutionCommandRecord:
    """Build a durable command envelope bound to one operator reconciliation.

    The caller must durably register this command before asking the lifecycle
    core to evaluate the separately authorized recovery transition.
    """

    if not reconciliation.operator_action_required:
        raise ValueError("operator recovery requires operator-action reconciliation")
    if not reconciliation.unresolved:
        raise ValueError("operator recovery requires unresolved reconciliation")
    if reconciliation.resulting_transition_id is not None or reconciliation.resulting_revision is not None:
        raise ValueError("reconciliation already records a resulting transition")
    if destination not in RECOVERY_DESTINATIONS:
        raise ValueError("recovery destination is not permitted")
    if destination is PaperExecutionLifecycleState.RECONCILIATION_REQUIRED:
        raise ValueError("operator recovery must advance to a resolved destination")

    payload = {
        "aggregate_id": reconciliation.aggregate_id,
        "destination": destination,
        "reconciliation_id": reconciliation.reconciliation_id,
        "reconciliation_record_fingerprint": reconciliation.record_fingerprint,
        "starting_local_revision": reconciliation.starting_local_revision,
    }
    canonical_command_json = canonical_json_text(payload)
    canonical_payload_fingerprint = fingerprint_payload("pcf", payload)

    return ExecutionCommandRecord(
        command_id=command_id,
        aggregate_id=reconciliation.aggregate_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        operation=PaperExecutionOperation.RECONCILE,
        expected_execution_revision=reconciliation.starting_local_revision,
        canonical_payload_fingerprint=canonical_payload_fingerprint,
        canonical_command_json=canonical_command_json,
        approval_fingerprint=approval_fingerprint,
        policy_fingerprint=policy_fingerprint,
        received_at=received_at,
        processing_outcome=ExecutionCommandProcessingOutcome.PENDING,
        schema_version=schema_version,
    )


__all__ = ["build_operator_recovery_command_record"]
