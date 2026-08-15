from __future__ import annotations

from dataclasses import replace

import pytest

from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionLifecycleState as State,
    PaperExecutionReconciliationOutcome as Outcome,
)
from volcanoes.application.execution.reconciliation import (
    ReconciliationFacts,
    compare_reconciliation_facts,
    reconciliation_evidence_fingerprint,
)


_BASE = ReconciliationFacts(
    local_present=True,
    broker_present=True,
    local_state=State.BROKER_ACKNOWLEDGED,
    broker_state=State.BROKER_ACKNOWLEDGED,
    local_broker_reference="paper-adr006-final",
    broker_reference="paper-adr006-final",
)


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("cancellation_ambiguous", "CANCELLATION_AMBIGUITY"),
        ("replacement_ambiguous", "REPLACEMENT_AMBIGUITY"),
        ("revision_conflict", "REVISION_CONFLICT"),
        ("observation_conflict", "CONFLICTING_EVIDENCE"),
    ],
)
def test_adr006_ambiguities_fail_closed_to_operator_reconciliation(
    field: str, reason: str
) -> None:
    facts = replace(_BASE, **{field: True})

    decision = compare_reconciliation_facts(facts)

    assert decision.outcome is Outcome.OPERATOR_ACTION_REQUIRED
    assert decision.reason == reason
    assert decision.proposed_state is State.RECONCILIATION_REQUIRED
    assert decision.operator_action_required is True


@pytest.mark.parametrize(
    "field",
    [
        "cancellation_ambiguous",
        "replacement_ambiguous",
        "revision_conflict",
        "observation_conflict",
    ],
)
def test_adr006_ambiguity_is_bound_into_durable_evidence_identity(field: str) -> None:
    clean_decision = compare_reconciliation_facts(_BASE)
    clean_fingerprint = reconciliation_evidence_fingerprint(_BASE, clean_decision)

    ambiguous = replace(_BASE, **{field: True})
    ambiguous_decision = compare_reconciliation_facts(ambiguous)
    ambiguous_fingerprint = reconciliation_evidence_fingerprint(
        ambiguous, ambiguous_decision
    )

    assert ambiguous_fingerprint != clean_fingerprint


def test_proven_non_ambiguous_match_remains_consistent() -> None:
    decision = compare_reconciliation_facts(_BASE)

    assert decision.outcome is Outcome.CONSISTENT
    assert decision.proposed_state is State.BROKER_ACKNOWLEDGED
    assert decision.operator_action_required is False
