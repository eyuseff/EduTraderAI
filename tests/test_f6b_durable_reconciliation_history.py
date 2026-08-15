from datetime import UTC, datetime
from decimal import Decimal

from volcanoes.application.execution.identities import (
    PaperExecutionAggregateId,
    PaperExecutionRevision,
)
from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionLifecycleState as State,
    PaperExecutionReconciliationOutcome as Outcome,
)
from volcanoes.application.execution.reconciliation import (
    ReconciliationDecision,
    ReconciliationFacts,
    build_reconciliation_history_record,
    reconciliation_evidence_fingerprint,
)

AGGREGATE_ID = PaperExecutionAggregateId("pea-" + "a" * 64)
RECORDED_AT = datetime(2026, 8, 15, 18, 30, tzinfo=UTC)


def _facts() -> ReconciliationFacts:
    return ReconciliationFacts(
        local_present=True,
        broker_present=True,
        local_state=State.OUTCOME_UNKNOWN,
        broker_state=State.BROKER_ACKNOWLEDGED,
        local_filled_quantity=Decimal("0"),
        broker_filled_quantity=Decimal("0"),
        local_broker_reference="paper-abc",
        broker_reference="paper-abc",
    )


def _decision() -> ReconciliationDecision:
    return ReconciliationDecision(
        outcome=Outcome.BROKER_AHEAD,
        reason="BROKER_HAS_PROVABLE_LATER_STATE",
        proposed_state=State.BROKER_ACKNOWLEDGED,
        operator_action_required=False,
    )


def test_same_evidence_builds_exact_same_durable_identity_and_fingerprint() -> None:
    first = build_reconciliation_history_record(
        aggregate_id=AGGREGATE_ID,
        starting_revision=PaperExecutionRevision(7),
        starting_state=State.OUTCOME_UNKNOWN,
        facts=_facts(),
        decision=_decision(),
        recorded_at=RECORDED_AT,
        schema_version=4,
    )
    second = build_reconciliation_history_record(
        aggregate_id=AGGREGATE_ID,
        starting_revision=PaperExecutionRevision(7),
        starting_state=State.OUTCOME_UNKNOWN,
        facts=_facts(),
        decision=_decision(),
        recorded_at=RECORDED_AT,
        schema_version=4,
    )

    assert first == second
    assert first.reconciliation_id == second.reconciliation_id
    assert first.record_fingerprint == second.record_fingerprint


def test_changed_broker_fact_changes_evidence_and_reconciliation_identity() -> None:
    original = _facts()
    changed = ReconciliationFacts(
        local_present=True,
        broker_present=True,
        local_state=State.OUTCOME_UNKNOWN,
        broker_state=State.FILLED,
        local_filled_quantity=Decimal("0"),
        broker_filled_quantity=Decimal("1"),
        local_broker_reference="paper-abc",
        broker_reference="paper-abc",
    )

    assert reconciliation_evidence_fingerprint(original, _decision()) != (
        reconciliation_evidence_fingerprint(changed, _decision())
    )

    first = build_reconciliation_history_record(
        aggregate_id=AGGREGATE_ID,
        starting_revision=PaperExecutionRevision(7),
        starting_state=State.OUTCOME_UNKNOWN,
        facts=original,
        decision=_decision(),
        recorded_at=RECORDED_AT,
        schema_version=4,
    )
    second = build_reconciliation_history_record(
        aggregate_id=AGGREGATE_ID,
        starting_revision=PaperExecutionRevision(7),
        starting_state=State.OUTCOME_UNKNOWN,
        facts=changed,
        decision=_decision(),
        recorded_at=RECORDED_AT,
        schema_version=4,
    )

    assert first.reconciliation_id != second.reconciliation_id
    assert first.record_fingerprint != second.record_fingerprint


def test_changed_starting_revision_changes_durable_identity() -> None:
    first = build_reconciliation_history_record(
        aggregate_id=AGGREGATE_ID,
        starting_revision=PaperExecutionRevision(7),
        starting_state=State.OUTCOME_UNKNOWN,
        facts=_facts(),
        decision=_decision(),
        recorded_at=RECORDED_AT,
        schema_version=4,
    )
    second = build_reconciliation_history_record(
        aggregate_id=AGGREGATE_ID,
        starting_revision=PaperExecutionRevision(8),
        starting_state=State.OUTCOME_UNKNOWN,
        facts=_facts(),
        decision=_decision(),
        recorded_at=RECORDED_AT,
        schema_version=4,
    )

    assert first.reconciliation_id != second.reconciliation_id


def test_evidence_fingerprint_is_stored_with_broker_references() -> None:
    facts = _facts()
    decision = _decision()
    record = build_reconciliation_history_record(
        aggregate_id=AGGREGATE_ID,
        starting_revision=PaperExecutionRevision(7),
        starting_state=State.OUTCOME_UNKNOWN,
        facts=facts,
        decision=decision,
        recorded_at=RECORDED_AT,
        schema_version=4,
    )

    evidence = reconciliation_evidence_fingerprint(facts, decision)
    assert record.broker_observation_references[0] == evidence
    assert "paper-abc" in record.broker_observation_references
    assert record.result_classification.value == "BROKER_AHEAD"
    assert record.operator_action_required is False
    assert record.unresolved is False


def test_unresolved_decision_is_durably_fail_closed() -> None:
    decision = ReconciliationDecision(
        outcome=Outcome.UNRESOLVED,
        reason="EVIDENCE_INCOMPLETE",
        proposed_state=State.RECONCILIATION_REQUIRED,
        operator_action_required=True,
    )
    record = build_reconciliation_history_record(
        aggregate_id=AGGREGATE_ID,
        starting_revision=PaperExecutionRevision(7),
        starting_state=State.RECONCILIATION_REQUIRED,
        facts=ReconciliationFacts(
            local_present=True,
            broker_present=True,
            evidence_complete=False,
        ),
        decision=decision,
        recorded_at=RECORDED_AT,
        schema_version=4,
    )

    assert record.unresolved is True
    assert record.operator_action_required is True
    assert record.resulting_transition_id is None
    assert record.resulting_revision is None
