from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from volcanoes.application.execution import (
    ExecutionAggregateRecord,
    ExecutionPersistenceConflict,
    ExecutionPersistenceConflictKind,
    ExecutionPersistenceConflictSeverity,
    PaperExecutionAggregateId,
    PaperExecutionCorrelationId,
    PaperExecutionLifecycleState,
    PaperExecutionRevision,
    canonical_payload_text,
)
from volcanoes.application.execution._canonical import canonical_json_text
from volcanoes.application.execution.fingerprints import fingerprint_payload

NOW = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)
SCHEMA_VERSION = 1


def aggregate_record(symbol: str = "AAPL") -> ExecutionAggregateRecord:
    return ExecutionAggregateRecord(
        aggregate_id=PaperExecutionAggregateId.from_seed("aggregate", symbol),
        correlation_id=PaperExecutionCorrelationId.from_seed("correlation", symbol),
        lifecycle_state=PaperExecutionLifecycleState.CREATED,
        execution_revision=PaperExecutionRevision.initial(),
        cumulative_filled_quantity=Decimal("0"),
        outcome_unknown=False,
        reconciliation_required=False,
        command_terminal=False,
        aggregate_terminal=False,
        last_transition_id="PX-TRN-001",
        created_at=NOW,
        updated_at=NOW,
        schema_version=SCHEMA_VERSION,
    )


def test_canonical_payload_text_reuses_execution_canonicalization() -> None:
    value = {"b": Decimal("1.00"), "a": ("x", 1)}

    assert canonical_payload_text(value) == canonical_json_text(value)
    assert canonical_payload_text(value) == '{"a":["x",1],"b":"1"}'


def test_record_fingerprint_is_stable_for_identical_inputs() -> None:
    first = aggregate_record()
    second = aggregate_record()

    assert first.record_fingerprint == second.record_fingerprint
    assert first.to_primitive() == second.to_primitive()


def test_record_fingerprint_changes_when_authoritative_field_changes() -> None:
    first = aggregate_record("AAPL")
    second = aggregate_record("MSFT")

    assert first.record_fingerprint != second.record_fingerprint


def test_conflict_fingerprint_is_stable() -> None:
    first = ExecutionPersistenceConflict(
        kind=ExecutionPersistenceConflictKind.STALE_REVISION,
        severity=ExecutionPersistenceConflictSeverity.ERROR,
        code="STALE_REVISION",
        safe_message="State changed before this command.",
        schema_version=SCHEMA_VERSION,
        expected_revision=PaperExecutionRevision(1),
        actual_revision=PaperExecutionRevision(2),
    )
    second = ExecutionPersistenceConflict(
        kind=ExecutionPersistenceConflictKind.STALE_REVISION,
        severity=ExecutionPersistenceConflictSeverity.ERROR,
        code="STALE_REVISION",
        safe_message="State changed before this command.",
        schema_version=SCHEMA_VERSION,
        expected_revision=PaperExecutionRevision(1),
        actual_revision=PaperExecutionRevision(2),
    )

    assert first.conflict_fingerprint == second.conflict_fingerprint
    assert first.conflict_fingerprint.startswith("pco-")


@pytest.mark.parametrize(
    "prefix",
    [
        "par",
        "pcm",
        "plo",
        "pir",
        "ptr",
        "pbf",
        "prr",
        "pfr",
        "pav",
        "prn",
        "pco",
        "puw",
    ],
)
def test_public_fingerprint_prefixes_are_valid(prefix: str) -> None:
    assert fingerprint_payload(prefix, ("sample",)).startswith(f"{prefix}-")


def test_secret_terms_do_not_appear_in_safe_serialization() -> None:
    record_text = canonical_payload_text(aggregate_record().to_primitive()).lower()

    assert "secret" not in record_text
    assert "api_key" not in record_text
    assert "authorization" not in record_text
