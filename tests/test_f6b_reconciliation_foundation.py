from decimal import Decimal

import pytest

from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionLifecycleState as State,
    PaperExecutionReconciliationOutcome as Outcome,
)
from volcanoes.application.execution.reconciliation import (
    RECOVERY_DESTINATIONS,
    ReconciliationFacts,
    reconcile,
)


def test_exact_match_is_consistent_and_non_mutating_proposal() -> None:
    facts = ReconciliationFacts(
        local_present=True,
        broker_present=True,
        local_state=State.FILLED,
        broker_state=State.FILLED,
        local_filled_quantity=Decimal("2"),
        broker_filled_quantity=Decimal("2"),
        local_broker_reference="paper-123",
        broker_reference="paper-123",
    )

    decision = reconcile(facts)

    assert decision.outcome is Outcome.CONSISTENT
    assert decision.proposed_state is State.FILLED
    assert decision.operator_action_required is False


def test_outcome_unknown_can_propose_proven_broker_state() -> None:
    decision = reconcile(
        ReconciliationFacts(
            local_present=True,
            broker_present=True,
            local_state=State.OUTCOME_UNKNOWN,
            broker_state=State.BROKER_ACKNOWLEDGED,
            local_broker_reference="paper-123",
            broker_reference="paper-123",
        )
    )

    assert decision.outcome is Outcome.BROKER_AHEAD
    assert decision.proposed_state is State.BROKER_ACKNOWLEDGED
    assert decision.operator_action_required is False


@pytest.mark.parametrize(
    "facts, expected",
    [
        (
            ReconciliationFacts(local_present=False, broker_present=True),
            Outcome.MISSING_LOCALLY,
        ),
        (
            ReconciliationFacts(local_present=True, broker_present=False),
            Outcome.MISSING_AT_BROKER,
        ),
        (
            ReconciliationFacts(local_present=False, broker_present=False),
            Outcome.UNRESOLVED,
        ),
    ],
)
def test_missing_order_gaps_never_invent_state(
    facts: ReconciliationFacts, expected: Outcome
) -> None:
    decision = reconcile(facts)

    assert decision.outcome is expected
    assert decision.proposed_state is State.RECONCILIATION_REQUIRED
    assert decision.operator_action_required is True


def test_reference_conflict_requires_operator_action() -> None:
    decision = reconcile(
        ReconciliationFacts(
            local_present=True,
            broker_present=True,
            local_state=State.BROKER_ACKNOWLEDGED,
            broker_state=State.BROKER_ACKNOWLEDGED,
            local_broker_reference="paper-one",
            broker_reference="paper-two",
        )
    )

    assert decision.outcome is Outcome.OPERATOR_ACTION_REQUIRED
    assert decision.reason == "BROKER_REFERENCE_CONFLICT"


def test_fill_quantity_conflict_requires_operator_action() -> None:
    decision = reconcile(
        ReconciliationFacts(
            local_present=True,
            broker_present=True,
            local_state=State.PARTIALLY_FILLED,
            broker_state=State.PARTIALLY_FILLED,
            local_filled_quantity=Decimal("1"),
            broker_filled_quantity=Decimal("2"),
        )
    )

    assert decision.outcome is Outcome.OPERATOR_ACTION_REQUIRED
    assert decision.reason == "FILL_QUANTITY_CONFLICT"


def test_incomplete_or_explicitly_conflicting_evidence_fails_closed() -> None:
    incomplete = reconcile(
        ReconciliationFacts(
            local_present=True,
            broker_present=True,
            evidence_complete=False,
        )
    )
    conflicting = reconcile(
        ReconciliationFacts(
            local_present=True,
            broker_present=True,
            observation_conflict=True,
        )
    )

    assert incomplete.outcome is Outcome.UNRESOLVED
    assert conflicting.outcome is Outcome.OPERATOR_ACTION_REQUIRED
    assert incomplete.proposed_state is State.RECONCILIATION_REQUIRED
    assert conflicting.proposed_state is State.RECONCILIATION_REQUIRED


def test_recovery_destinations_match_adr006_bounded_set() -> None:
    assert RECOVERY_DESTINATIONS == {
        State.BROKER_ACKNOWLEDGED,
        State.PARTIALLY_FILLED,
        State.FILLED,
        State.CANCELLED,
        State.BROKER_REJECTED,
        State.FAILED_TERMINAL,
        State.RECONCILIATION_REQUIRED,
    }


def test_negative_fill_quantity_is_rejected() -> None:
    with pytest.raises(ValueError, match="filled quantity cannot be negative"):
        ReconciliationFacts(
            local_present=True,
            broker_present=True,
            local_filled_quantity=Decimal("-1"),
        )
