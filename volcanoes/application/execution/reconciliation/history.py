"""Durable-history preparation for read-first Paper reconciliation.

This module only derives deterministic identities and storage-neutral
ExecutionReconciliationRecord values from already-observed reconciliation facts.
It performs no broker I/O, no retry, no dispatch, and no commit.
"""

from __future__ import annotations

from datetime import datetime

from volcanoes.application.execution.fingerprints import fingerprint_payload
from volcanoes.application.execution.identities import (
    PaperExecutionAggregateId,
    PaperExecutionRevision,
)
from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionLifecycleState,
)
from volcanoes.application.execution.persistence.contracts import (
    ExecutionReconciliationRecord,
)
from volcanoes.application.execution.persistence.enums import (
    ExecutionReconciliationResultClassification,
)

from .model import ReconciliationDecision, ReconciliationFacts


def reconciliation_evidence_fingerprint(
    facts: ReconciliationFacts,
    decision: ReconciliationDecision,
) -> str:
    """Bind all comparison inputs and the bounded decision into one fingerprint."""

    return fingerprint_payload(
        "prf",
        {
            "broker_filled_quantity": facts.broker_filled_quantity,
            "broker_present": facts.broker_present,
            "broker_reference": facts.broker_reference,
            "broker_state": facts.broker_state,
            "cancellation_ambiguous": facts.cancellation_ambiguous,
            "decision_operator_action_required": decision.operator_action_required,
            "decision_outcome": decision.outcome,
            "decision_proposed_state": decision.proposed_state,
            "decision_reason": decision.reason,
            "evidence_complete": facts.evidence_complete,
            "local_broker_reference": facts.local_broker_reference,
            "local_filled_quantity": facts.local_filled_quantity,
            "local_present": facts.local_present,
            "local_state": facts.local_state,
            "observation_conflict": facts.observation_conflict,
            "ownership_conflict": facts.ownership_conflict,
            "replacement_ambiguous": facts.replacement_ambiguous,
            "revision_conflict": facts.revision_conflict,
        },
    )


def deterministic_reconciliation_id(
    aggregate_id: PaperExecutionAggregateId,
    starting_revision: PaperExecutionRevision,
    evidence_fingerprint: str,
) -> str:
    """Return a stable identity for the same aggregate/revision/evidence tuple."""

    digest = fingerprint_payload(
        "pri",
        {
            "aggregate_id": aggregate_id,
            "evidence_fingerprint": evidence_fingerprint,
            "starting_revision": starting_revision,
        },
    ).rsplit("-", 1)[-1]
    return "recon-" + digest[:48]


def build_reconciliation_history_record(
    *,
    aggregate_id: PaperExecutionAggregateId,
    starting_revision: PaperExecutionRevision,
    starting_state: PaperExecutionLifecycleState,
    facts: ReconciliationFacts,
    decision: ReconciliationDecision,
    recorded_at: datetime,
    schema_version: int,
) -> ExecutionReconciliationRecord:
    """Build the append-only durable record for one read-first comparison."""

    evidence_fingerprint = reconciliation_evidence_fingerprint(facts, decision)
    reconciliation_id = deterministic_reconciliation_id(
        aggregate_id,
        starting_revision,
        evidence_fingerprint,
    )
    references = tuple(
        dict.fromkeys(
            value
            for value in (
                evidence_fingerprint,
                facts.local_broker_reference,
                facts.broker_reference,
            )
            if value is not None
        )
    )
    return ExecutionReconciliationRecord(
        reconciliation_id=reconciliation_id,
        aggregate_id=aggregate_id,
        starting_local_revision=starting_revision,
        starting_lifecycle_state=starting_state,
        broker_observation_references=references,
        result_classification=ExecutionReconciliationResultClassification(
            decision.outcome.value
        ),
        operator_action_required=decision.operator_action_required,
        unresolved=decision.outcome.value in {"UNRESOLVED", "OPERATOR_ACTION_REQUIRED"},
        safe_reason_code=decision.reason,
        recorded_at=recorded_at,
        schema_version=schema_version,
    )


__all__ = [
    "build_reconciliation_history_record",
    "deterministic_reconciliation_id",
    "reconciliation_evidence_fingerprint",
]
