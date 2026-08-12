"""Deterministic non-durable in-memory ports for qualification harnesses."""

from __future__ import annotations

from volcanoes.application.qualification.contracts import (
    EvidenceIntent,
    IdempotencyKey,
    PaperQualificationRun,
    PriorCommandRecord,
    QualificationRunId,
    StateRevision,
)
from volcanoes.application.qualification.ports import (
    EvidenceRecordReference,
    SaveResult,
)


class InMemoryQualificationRunRepository:
    """Deterministic fake repository; not production persistence."""

    def __init__(self) -> None:
        self.runs: dict[QualificationRunId, PaperQualificationRun] = {}
        self.records: dict[
            tuple[QualificationRunId, IdempotencyKey], PriorCommandRecord
        ] = {}
        self.operations: list[str] = []
        self.fail_get = False
        self.fail_save = False
        self.conflict_save = False
        self.fail_record_command = False

    def get(self, run_id: QualificationRunId) -> PaperQualificationRun | None:
        """Return the current immutable run snapshot."""

        self.operations.append("get")
        if self.fail_get:
            raise RuntimeError("repository unavailable")
        return self.runs.get(run_id)

    def save(
        self,
        run: PaperQualificationRun,
        *,
        expected_previous_revision: StateRevision | None,
    ) -> SaveResult:
        """Save a run snapshot with revision checking."""

        self.operations.append("save")
        if self.fail_save:
            raise RuntimeError("save unavailable")
        existing = self.runs.get(run.qualification_run_id)
        if self.conflict_save or (
            existing is not None
            and expected_previous_revision is not None
            and existing.state_revision != expected_previous_revision
        ):
            return SaveResult(
                saved=False,
                previous_revision=existing.state_revision if existing else None,
                current_revision=run.state_revision,
                reason_code="SAVE_CONFLICT",
                safe_message="Qualification run state could not be recorded.",
            )
        self.runs[run.qualification_run_id] = run
        return SaveResult(
            saved=True,
            previous_revision=expected_previous_revision,
            current_revision=run.state_revision,
        )

    def prior_command(
        self,
        run_id: QualificationRunId,
        idempotency_key: IdempotencyKey,
    ) -> PriorCommandRecord | None:
        """Return a prior command record for idempotency checks."""

        self.operations.append("prior_command")
        return self.records.get((run_id, idempotency_key))

    def record_command(
        self,
        run_id: QualificationRunId,
        record: PriorCommandRecord,
    ) -> None:
        """Record an idempotency result for deterministic replay."""

        self.operations.append("record_command")
        if self.fail_record_command:
            raise RuntimeError("record unavailable")
        self.records[(run_id, record.idempotency_key)] = record


class RecordingQualificationEvidenceRecorder:
    """Deterministic fake evidence recorder; not durable evidence storage."""

    def __init__(self) -> None:
        self.intents: list[EvidenceIntent] = []
        self.operations: list[str] = []
        self.fail = False

    def record(
        self,
        evidence_intents: tuple[EvidenceIntent, ...],
    ) -> tuple[EvidenceRecordReference, ...]:
        """Record evidence intents in memory and return safe references."""

        self.operations.append("record_evidence")
        if self.fail:
            raise RuntimeError("evidence unavailable")
        starting_count = len(self.intents)
        self.intents.extend(evidence_intents)
        return tuple(
            EvidenceRecordReference(
                evidence_id=f"evidence-{starting_count + index + 1}",
                transition_id=intent.transition_id,
                correlation_id=intent.correlation_id,
            )
            for index, intent in enumerate(evidence_intents)
        )
