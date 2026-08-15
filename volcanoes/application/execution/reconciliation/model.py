"""Pure deterministic reconciliation model for Paper execution.

This module compares already-observed local and broker facts.  It performs no
broker I/O, persistence mutation, retries, dispatch, or runtime wiring.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionLifecycleState,
    PaperExecutionReconciliationOutcome,
)


RECOVERY_DESTINATIONS = frozenset(
    {
        PaperExecutionLifecycleState.BROKER_ACKNOWLEDGED,
        PaperExecutionLifecycleState.PARTIALLY_FILLED,
        PaperExecutionLifecycleState.FILLED,
        PaperExecutionLifecycleState.CANCELLED,
        PaperExecutionLifecycleState.BROKER_REJECTED,
        PaperExecutionLifecycleState.FAILED_TERMINAL,
        PaperExecutionLifecycleState.RECONCILIATION_REQUIRED,
    }
)


@dataclass(frozen=True, slots=True)
class ReconciliationFacts:
    """Immutable facts available to one reconciliation comparison."""

    local_present: bool
    broker_present: bool
    local_state: PaperExecutionLifecycleState | None = None
    broker_state: PaperExecutionLifecycleState | None = None
    local_filled_quantity: Decimal | None = None
    broker_filled_quantity: Decimal | None = None
    local_broker_reference: str | None = None
    broker_reference: str | None = None
    observation_conflict: bool = False
    ownership_conflict: bool = False
    cancellation_ambiguous: bool = False
    replacement_ambiguous: bool = False
    revision_conflict: bool = False
    evidence_complete: bool = True

    def __post_init__(self) -> None:
        if not self.local_present and self.local_state is not None:
            raise ValueError("local state requires local presence")
        if not self.broker_present and self.broker_state is not None:
            raise ValueError("broker state requires broker presence")
        for quantity in (self.local_filled_quantity, self.broker_filled_quantity):
            if quantity is not None and quantity < 0:
                raise ValueError("filled quantity cannot be negative")


@dataclass(frozen=True, slots=True)
class ReconciliationDecision:
    """Read-only comparison result and bounded recovery proposal."""

    outcome: PaperExecutionReconciliationOutcome
    reason: str
    proposed_state: PaperExecutionLifecycleState
    operator_action_required: bool

    def __post_init__(self) -> None:
        if self.proposed_state not in RECOVERY_DESTINATIONS:
            raise ValueError("reconciliation recovery destination is not permitted")
        if not self.reason:
            raise ValueError("reconciliation decision requires a reason")


def compare_reconciliation_facts(facts: ReconciliationFacts) -> ReconciliationDecision:
    """Compare local and broker evidence without mutating either side."""

    if not facts.evidence_complete:
        return _unresolved("EVIDENCE_INCOMPLETE")
    if facts.cancellation_ambiguous:
        return _operator("CANCELLATION_AMBIGUITY")
    if facts.replacement_ambiguous:
        return _operator("REPLACEMENT_AMBIGUITY")
    if facts.revision_conflict:
        return _operator("REVISION_CONFLICT")
    if facts.observation_conflict or facts.ownership_conflict:
        return _operator("CONFLICTING_EVIDENCE")
    if not facts.local_present and not facts.broker_present:
        return _unresolved("ORDER_MISSING_ON_BOTH_SIDES")
    if not facts.local_present:
        return ReconciliationDecision(
            PaperExecutionReconciliationOutcome.MISSING_LOCALLY,
            "BROKER_ORDER_MISSING_LOCALLY",
            PaperExecutionLifecycleState.RECONCILIATION_REQUIRED,
            True,
        )
    if not facts.broker_present:
        return ReconciliationDecision(
            PaperExecutionReconciliationOutcome.MISSING_AT_BROKER,
            "LOCAL_ORDER_MISSING_AT_BROKER",
            PaperExecutionLifecycleState.RECONCILIATION_REQUIRED,
            True,
        )

    if _references_conflict(facts):
        return _operator("BROKER_REFERENCE_CONFLICT")
    if _fill_conflict(facts):
        return _operator("FILL_QUANTITY_CONFLICT")

    local_state = facts.local_state
    broker_state = facts.broker_state
    if local_state is None or broker_state is None:
        return _unresolved("STATE_EVIDENCE_INCOMPLETE")
    if local_state == broker_state:
        return ReconciliationDecision(
            PaperExecutionReconciliationOutcome.CONSISTENT,
            "LOCAL_AND_BROKER_STATE_MATCH",
            _bounded_state(broker_state),
            False,
        )

    if local_state in {
        PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
        PaperExecutionLifecycleState.RECONCILIATION_REQUIRED,
        PaperExecutionLifecycleState.DISPATCH_PENDING,
        PaperExecutionLifecycleState.DISPATCHED,
    } and broker_state in RECOVERY_DESTINATIONS - {
        PaperExecutionLifecycleState.RECONCILIATION_REQUIRED,
        PaperExecutionLifecycleState.FAILED_TERMINAL,
    }:
        return ReconciliationDecision(
            PaperExecutionReconciliationOutcome.BROKER_AHEAD,
            "BROKER_HAS_PROVABLE_LATER_STATE",
            broker_state,
            False,
        )

    if broker_state in {
        PaperExecutionLifecycleState.DISPATCH_PENDING,
        PaperExecutionLifecycleState.DISPATCHED,
        PaperExecutionLifecycleState.BROKER_ACKNOWLEDGED,
    } and local_state in {
        PaperExecutionLifecycleState.PARTIALLY_FILLED,
        PaperExecutionLifecycleState.FILLED,
        PaperExecutionLifecycleState.CANCELLED,
        PaperExecutionLifecycleState.BROKER_REJECTED,
    }:
        return ReconciliationDecision(
            PaperExecutionReconciliationOutcome.LOCAL_AHEAD,
            "LOCAL_HAS_PROVABLE_LATER_STATE",
            local_state,
            True,
        )

    return _operator("STATE_CONFLICT")


def _bounded_state(state: PaperExecutionLifecycleState) -> PaperExecutionLifecycleState:
    if state in RECOVERY_DESTINATIONS:
        return state
    return PaperExecutionLifecycleState.RECONCILIATION_REQUIRED


def _references_conflict(facts: ReconciliationFacts) -> bool:
    return (
        facts.local_broker_reference is not None
        and facts.broker_reference is not None
        and facts.local_broker_reference != facts.broker_reference
    )


def _fill_conflict(facts: ReconciliationFacts) -> bool:
    return (
        facts.local_filled_quantity is not None
        and facts.broker_filled_quantity is not None
        and facts.local_filled_quantity != facts.broker_filled_quantity
    )


def _unresolved(reason: str) -> ReconciliationDecision:
    return ReconciliationDecision(
        PaperExecutionReconciliationOutcome.UNRESOLVED,
        reason,
        PaperExecutionLifecycleState.RECONCILIATION_REQUIRED,
        True,
    )


def _operator(reason: str) -> ReconciliationDecision:
    return ReconciliationDecision(
        PaperExecutionReconciliationOutcome.OPERATOR_ACTION_REQUIRED,
        reason,
        PaperExecutionLifecycleState.RECONCILIATION_REQUIRED,
        True,
    )
