"""Abstract ports for Paper qualification application orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from volcanoes.application.qualification.contracts import (
    CorrelationId,
    EvidenceIntent,
    IdempotencyKey,
    PaperQualificationRun,
    PriorCommandRecord,
    QualificationRunId,
    StateRevision,
)


@dataclass(frozen=True, slots=True)
class SaveResult:
    """Revision-aware save outcome returned by a repository port."""

    saved: bool
    previous_revision: StateRevision | None
    current_revision: StateRevision
    reason_code: str = "SAVED"
    safe_message: str = "Qualification run state was recorded."

    def __post_init__(self) -> None:
        if self.previous_revision is not None and self.previous_revision < 0:
            raise ValueError("previous_revision cannot be negative.")
        if self.current_revision < 0:
            raise ValueError("current_revision cannot be negative.")
        if not self.reason_code.strip():
            raise ValueError("reason_code cannot be empty.")
        if not self.safe_message.strip():
            raise ValueError("safe_message cannot be empty.")


@dataclass(frozen=True, slots=True)
class EvidenceRecordReference:
    """Safe reference to evidence recorded by an abstract recorder."""

    evidence_id: str
    transition_id: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        for name in ("evidence_id", "transition_id", "correlation_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} cannot be empty.")


class QualificationRunRepository(Protocol):
    """Abstract revision-aware storage for qualification runs."""

    def get(self, run_id: QualificationRunId) -> PaperQualificationRun | None:
        """Return the current run snapshot, if any."""

    def save(
        self,
        run: PaperQualificationRun,
        *,
        expected_previous_revision: StateRevision | None,
    ) -> SaveResult:
        """Record a run snapshot without silently overwriting another revision."""

    def prior_command(
        self,
        run_id: QualificationRunId,
        idempotency_key: IdempotencyKey,
    ) -> PriorCommandRecord | None:
        """Return the recorded command decision for idempotency replay, if any."""

    def record_command(
        self,
        run_id: QualificationRunId,
        record: PriorCommandRecord,
    ) -> None:
        """Record one command decision for later idempotency checks."""


class QualificationEvidenceRecorder(Protocol):
    """Abstract evidence recorder for safe transition evidence intents."""

    def record(
        self,
        evidence_intents: tuple[EvidenceIntent, ...],
    ) -> tuple[EvidenceRecordReference, ...]:
        """Record evidence intents and return safe references."""
