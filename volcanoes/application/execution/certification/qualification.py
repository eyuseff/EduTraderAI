"""Deterministic offline state machine for Paper broker qualification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PaperQualificationState(str, Enum):
    CREATED = "CREATED"
    GUARDED = "GUARDED"
    OPERATOR_CONFIRMED = "OPERATOR_CONFIRMED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    STATUS_VERIFIED = "STATUS_VERIFIED"
    CANCELLED = "CANCELLED"
    PASSED = "PASSED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"

    @property
    def terminal(self) -> bool:
        return self in {
            PaperQualificationState.PASSED,
            PaperQualificationState.FAILED,
            PaperQualificationState.BLOCKED,
        }


class PaperQualificationEvent(str, Enum):
    GUARDS_PASSED = "GUARDS_PASSED"
    GUARDS_BLOCKED = "GUARDS_BLOCKED"
    OPERATOR_CONFIRMED = "OPERATOR_CONFIRMED"
    SUBMISSION_ACCEPTED = "SUBMISSION_ACCEPTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    ZERO_FILL_VERIFIED = "ZERO_FILL_VERIFIED"
    CANCEL_CONFIRMED = "CANCEL_CONFIRMED"
    CLEANUP_CONFIRMED = "CLEANUP_CONFIRMED"
    FAIL = "FAIL"


class PaperQualificationOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class PaperQualificationDecision:
    previous_state: PaperQualificationState
    next_state: PaperQualificationState
    event: PaperQualificationEvent
    accepted: bool
    reason_code: str

    @property
    def outcome(self) -> PaperQualificationOutcome | None:
        if self.next_state is PaperQualificationState.PASSED:
            return PaperQualificationOutcome.PASS
        if self.next_state is PaperQualificationState.FAILED:
            return PaperQualificationOutcome.FAIL
        if self.next_state is PaperQualificationState.BLOCKED:
            return PaperQualificationOutcome.BLOCKED
        return None


_TRANSITIONS: dict[
    tuple[PaperQualificationState, PaperQualificationEvent], PaperQualificationState
] = {
    (PaperQualificationState.CREATED, PaperQualificationEvent.GUARDS_PASSED): (
        PaperQualificationState.GUARDED
    ),
    (PaperQualificationState.CREATED, PaperQualificationEvent.GUARDS_BLOCKED): (
        PaperQualificationState.BLOCKED
    ),
    (PaperQualificationState.GUARDED, PaperQualificationEvent.OPERATOR_CONFIRMED): (
        PaperQualificationState.OPERATOR_CONFIRMED
    ),
    (
        PaperQualificationState.OPERATOR_CONFIRMED,
        PaperQualificationEvent.SUBMISSION_ACCEPTED,
    ): PaperQualificationState.SUBMITTED,
    (PaperQualificationState.SUBMITTED, PaperQualificationEvent.ACKNOWLEDGED): (
        PaperQualificationState.ACKNOWLEDGED
    ),
    (
        PaperQualificationState.ACKNOWLEDGED,
        PaperQualificationEvent.ZERO_FILL_VERIFIED,
    ): PaperQualificationState.STATUS_VERIFIED,
    (
        PaperQualificationState.STATUS_VERIFIED,
        PaperQualificationEvent.CANCEL_CONFIRMED,
    ): PaperQualificationState.CANCELLED,
    (
        PaperQualificationState.CANCELLED,
        PaperQualificationEvent.CLEANUP_CONFIRMED,
    ): PaperQualificationState.PASSED,
}


def transition_paper_qualification(
    state: PaperQualificationState,
    event: PaperQualificationEvent,
) -> PaperQualificationDecision:
    """Apply one deterministic qualification event without performing I/O."""

    if state.terminal:
        return PaperQualificationDecision(
            previous_state=state,
            next_state=state,
            event=event,
            accepted=False,
            reason_code="QUALIFICATION_ALREADY_TERMINAL",
        )

    if event is PaperQualificationEvent.FAIL:
        return PaperQualificationDecision(
            previous_state=state,
            next_state=PaperQualificationState.FAILED,
            event=event,
            accepted=True,
            reason_code="QUALIFICATION_FAILED",
        )

    next_state = _TRANSITIONS.get((state, event))
    if next_state is None:
        return PaperQualificationDecision(
            previous_state=state,
            next_state=state,
            event=event,
            accepted=False,
            reason_code="INVALID_QUALIFICATION_TRANSITION",
        )

    return PaperQualificationDecision(
        previous_state=state,
        next_state=next_state,
        event=event,
        accepted=True,
        reason_code=(
            "QUALIFICATION_BLOCKED"
            if next_state is PaperQualificationState.BLOCKED
            else "QUALIFICATION_TRANSITION_ACCEPTED"
        ),
    )
