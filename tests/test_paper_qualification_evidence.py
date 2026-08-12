"""Canonical evidence-adapter tests for Paper qualification."""

from __future__ import annotations

import builtins
import io
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from volcanoes.application.qualification import (
    ActorType,
    CommandId,
    CorrelationId,
    EvidenceIntent,
    EvidenceIntegrityError,
    EvidenceRecordConflictError,
    EvidenceRedactionError,
    EvidenceSchemaVersionError,
    EvidenceValidationError,
    Guard,
    IdempotencyKey,
    InMemoryCanonicalQualificationEvidenceRecorder,
    InMemoryQualificationRunRepository,
    MetadataInput,
    PaperQualificationService,
    QUALIFICATION_EVIDENCE_SCHEMA_VERSION,
    QualificationApplicationCommand,
    QualificationEventType,
    QualificationEvidenceAdapter,
    QualificationEvidenceRecord,
    QualificationEvidenceType,
    QualificationResult,
    QualificationRunId,
    QualificationScenarioHarness,
    QualificationScenarioId,
    QualificationState,
    REDACTED_VALUE,
    ScenarioExecutionContext,
    ScenarioHarnessStatus,
    SideEffectIntentType,
    StateRevision,
    compute_evidence_digest,
    default_positive_scenario,
    duplicate_command_replay_scenario,
    emergency_stop_scenario,
    idempotency_conflict_scenario,
    operator_rejection_scenario,
    precheck_failure_scenario,
    serialize_qualification_evidence,
    uncertain_submission_scenario,
    verify_evidence_digest,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXED_TIME = datetime(2026, 7, 28, 12, 30, 45, tzinfo=UTC)
RUN_ID = QualificationRunId("evidence-run-001")
SCENARIO_ID = QualificationScenarioId("PQ-SCN-005")
CORRELATION_ID = CorrelationId("evidence-correlation-001")
SECRET_SENTINEL = "SENTINEL_API_SECRET_DO_NOT_EXPOSE"
DEFAULT_TRACE = (
    "PQ-TRN-001",
    "PQ-TRN-002",
    "PQ-TRN-005",
    "PQ-TRN-006",
    "PQ-TRN-009",
    "PQ-TRN-010",
    "PQ-TRN-011",
    "PQ-TRN-015",
    "PQ-TRN-017",
    "PQ-TRN-030",
)
DEFAULT_EVIDENCE_TYPES = (
    QualificationEvidenceType.QUALIFICATION_TRANSITION_ACCEPTED,
    QualificationEvidenceType.QUALIFICATION_TRANSITION_ACCEPTED,
    QualificationEvidenceType.QUALIFICATION_TRANSITION_ACCEPTED,
    QualificationEvidenceType.QUALIFICATION_TRANSITION_ACCEPTED,
    QualificationEvidenceType.QUALIFICATION_TRANSITION_ACCEPTED,
    QualificationEvidenceType.QUALIFICATION_TRANSITION_ACCEPTED,
    QualificationEvidenceType.QUALIFICATION_TRANSITION_ACCEPTED,
    QualificationEvidenceType.QUALIFICATION_TRANSITION_ACCEPTED,
    QualificationEvidenceType.QUALIFICATION_TRANSITION_ACCEPTED,
    QualificationEvidenceType.QUALIFICATION_TERMINAL_RESULT,
)


def _install_protected_state_access_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> list[str]:
    """Fail if evidence construction targets the production state path."""

    protected_path = os.path.normcase(
        os.path.abspath(
            os.path.normpath(os.fspath(PROJECT_ROOT / "state/simulated_broker.json"))
        )
    )
    attempts: list[str] = []

    def normalized_path(candidate: object) -> str | None:
        if isinstance(candidate, int):
            return None
        if not isinstance(candidate, (str, bytes, os.PathLike)):
            return None
        try:
            raw_path = os.fspath(candidate)
        except TypeError:
            return None
        return os.path.normcase(
            os.path.abspath(os.path.normpath(os.fsdecode(raw_path)))
        )

    def guard(operation: str, *candidates: object) -> None:
        if any(
            normalized_path(candidate) == protected_path for candidate in candidates
        ):
            attempts.append(operation)
            raise AssertionError(
                f"protected simulator-state access attempted via {operation}"
            )

    def guard_one_path(operation: str, original: object):
        def wrapped(path: object, *args: object, **kwargs: object) -> object:
            guard(operation, path)
            return original(path, *args, **kwargs)  # type: ignore[operator]

        return wrapped

    def guard_two_paths(operation: str, original: object):
        def wrapped(
            source: object,
            destination: object,
            *args: object,
            **kwargs: object,
        ) -> object:
            guard(operation, source, destination)
            return original(source, destination, *args, **kwargs)  # type: ignore[operator]

        return wrapped

    original_builtins_open = builtins.open
    original_io_open = io.open
    original_os_open = os.open
    original_os_stat = os.stat
    original_os_lstat = os.lstat
    original_os_access = os.access
    original_os_unlink = os.unlink
    original_os_remove = os.remove
    original_os_rename = os.rename
    original_os_replace = os.replace
    original_path_open = Path.open
    original_path_read_bytes = Path.read_bytes
    original_path_read_text = Path.read_text
    original_path_write_bytes = Path.write_bytes
    original_path_write_text = Path.write_text
    original_path_exists = Path.exists
    original_path_stat = Path.stat
    original_path_lstat = Path.lstat
    original_path_is_file = Path.is_file
    original_path_is_dir = Path.is_dir
    original_path_touch = Path.touch
    original_path_unlink = Path.unlink
    original_path_rename = Path.rename
    original_path_replace = Path.replace

    monkeypatch.setattr(
        builtins, "open", guard_one_path("builtins.open", original_builtins_open)
    )
    monkeypatch.setattr(io, "open", guard_one_path("io.open", original_io_open))
    monkeypatch.setattr(os, "open", guard_one_path("os.open", original_os_open))
    monkeypatch.setattr(os, "stat", guard_one_path("os.stat", original_os_stat))
    monkeypatch.setattr(os, "lstat", guard_one_path("os.lstat", original_os_lstat))
    monkeypatch.setattr(os, "access", guard_one_path("os.access", original_os_access))
    monkeypatch.setattr(os, "unlink", guard_one_path("os.unlink", original_os_unlink))
    monkeypatch.setattr(os, "remove", guard_one_path("os.remove", original_os_remove))
    monkeypatch.setattr(os, "rename", guard_two_paths("os.rename", original_os_rename))
    monkeypatch.setattr(
        os, "replace", guard_two_paths("os.replace", original_os_replace)
    )
    monkeypatch.setattr(Path, "open", guard_one_path("Path.open", original_path_open))
    monkeypatch.setattr(
        Path, "read_bytes", guard_one_path("Path.read_bytes", original_path_read_bytes)
    )
    monkeypatch.setattr(
        Path, "read_text", guard_one_path("Path.read_text", original_path_read_text)
    )
    monkeypatch.setattr(
        Path,
        "write_bytes",
        guard_one_path("Path.write_bytes", original_path_write_bytes),
    )
    monkeypatch.setattr(
        Path,
        "write_text",
        guard_one_path("Path.write_text", original_path_write_text),
    )
    monkeypatch.setattr(
        Path, "exists", guard_one_path("Path.exists", original_path_exists)
    )
    monkeypatch.setattr(Path, "stat", guard_one_path("Path.stat", original_path_stat))
    monkeypatch.setattr(
        Path, "lstat", guard_one_path("Path.lstat", original_path_lstat)
    )
    monkeypatch.setattr(
        Path, "is_file", guard_one_path("Path.is_file", original_path_is_file)
    )
    monkeypatch.setattr(
        Path, "is_dir", guard_one_path("Path.is_dir", original_path_is_dir)
    )
    monkeypatch.setattr(
        Path, "touch", guard_one_path("Path.touch", original_path_touch)
    )
    monkeypatch.setattr(
        Path, "unlink", guard_one_path("Path.unlink", original_path_unlink)
    )
    monkeypatch.setattr(
        Path, "rename", guard_two_paths("Path.rename", original_path_rename)
    )
    monkeypatch.setattr(
        Path, "replace", guard_two_paths("Path.replace", original_path_replace)
    )
    return attempts


def sample_intent(
    *,
    diagnostic: bool = False,
    reason_code: str = "PQ_TRN_001",
    result: QualificationResult = QualificationResult.PENDING,
    source: QualificationState = QualificationState.NOT_STARTED,
    destination: QualificationState = QualificationState.PRECHECK_PENDING,
    previous_revision: int = 0,
    next_revision: int = 1,
    message: str = "Qualification prechecks are running. No broker request has been sent.",
    event_type: QualificationEventType = QualificationEventType.START_QUALIFICATION,
    actor: ActorType = ActorType.APPLICATION,
    reconciliation_required: bool = False,
) -> EvidenceIntent:
    return EvidenceIntent(
        transition_id="INVALID" if diagnostic else "PQ-TRN-001",
        event_type=event_type,
        source_state=source,
        destination_state=destination,
        qualification_run_id=RUN_ID,
        qualification_scenario_id=SCENARIO_ID,
        correlation_id=CORRELATION_ID,
        command_id=CommandId("command-001"),
        idempotency_key=IdempotencyKey("idem-001"),
        result=result,
        reason_code=reason_code,
        actor_type=actor,
        environment="PAPER",
        safe_message=message,
        object_reference="paper-order-reference-001",
        diagnostic=diagnostic,
        previous_revision=StateRevision(previous_revision),
        next_revision=StateRevision(next_revision),
        reconciliation_required=reconciliation_required,
    )


def adapter() -> QualificationEvidenceAdapter:
    return QualificationEvidenceAdapter()


def build_record(
    intent: EvidenceIntent | None = None,
    *,
    metadata: MetadataInput = (),
) -> QualificationEvidenceRecord:
    return adapter().build(
        intent or sample_intent(),
        occurred_at=FIXED_TIME,
        additional_metadata=metadata,
    )


def canonical_service_stack() -> tuple[
    PaperQualificationService,
    InMemoryQualificationRunRepository,
    InMemoryCanonicalQualificationEvidenceRecorder,
]:
    repository = InMemoryQualificationRunRepository()
    recorder = InMemoryCanonicalQualificationEvidenceRecorder(occurred_at=FIXED_TIME)
    return PaperQualificationService(repository, recorder), repository, recorder


def run_scenario_with_canonical_recorder():
    service, repository, recorder = canonical_service_stack()
    harness = QualificationScenarioHarness(service=service, repository=repository)
    result = harness.run(
        default_positive_scenario(),
        execution_context=ScenarioExecutionContext(RUN_ID, CORRELATION_ID),
    )
    return result, recorder


def test_build_canonical_record_from_accepted_transition_intent() -> None:
    record = build_record()

    assert record.schema_version == QUALIFICATION_EVIDENCE_SCHEMA_VERSION
    assert record.evidence_type is (
        QualificationEvidenceType.QUALIFICATION_TRANSITION_ACCEPTED
    )
    assert record.transition_id == "PQ-TRN-001"
    assert record.source_state == "NOT_STARTED"
    assert record.destination_state == "PRECHECK_PENDING"


def test_build_canonical_record_from_diagnostic_rejection_intent() -> None:
    record = build_record(
        sample_intent(
            diagnostic=True,
            reason_code="GUARD_PAPER_ENVIRONMENT",
            source=QualificationState.NOT_STARTED,
            destination=QualificationState.NOT_STARTED,
            previous_revision=0,
            next_revision=0,
        )
    )

    assert record.evidence_type is QualificationEvidenceType.QUALIFICATION_GUARD_FAILED
    assert record.diagnostic is True
    assert record.previous_revision == 0
    assert record.next_revision == 0


def test_schema_version_is_present() -> None:
    assert build_record().schema_version == "qualification-evidence/v1"


def test_unsupported_schema_version_is_rejected() -> None:
    with pytest.raises(EvidenceSchemaVersionError):
        QualificationEvidenceAdapter(schema_version="qualification-evidence/v2")


def test_record_identity_is_deterministic() -> None:
    assert build_record().evidence_id == build_record().evidence_id


def test_equivalent_input_produces_equivalent_record() -> None:
    assert build_record() == build_record()


def test_materially_different_input_produces_different_record_identity() -> None:
    different = sample_intent(destination=QualificationState.PRECHECK_FAILED)

    assert build_record().evidence_id != build_record(different).evidence_id


def test_timestamp_normalization_is_deterministic() -> None:
    record = adapter().build(
        sample_intent(),
        occurred_at=datetime(2026, 7, 28, 8, 30, 45, tzinfo=UTC),
    )

    assert record.occurred_at == "2026-07-28T08:30:45Z"


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(EvidenceValidationError):
        adapter().build(sample_intent(), occurred_at=datetime(2026, 7, 28))


def test_enum_normalization_is_stable() -> None:
    record = build_record()

    assert record.event_type == "START_QUALIFICATION"
    assert record.actor_type == "APPLICATION"
    assert record.qualification_result == "PENDING"


def test_optional_fields_serialize_consistently() -> None:
    record = build_record(replace(sample_intent(), object_reference=None))

    assert '"object_reference":null' in serialize_qualification_evidence(record)


def test_canonical_key_order_and_separators_are_stable() -> None:
    serialized = serialize_qualification_evidence(build_record())

    assert serialized.startswith('{"actor_type":')
    assert ": " not in serialized
    assert ", " not in serialized


def test_unicode_behavior_is_stable() -> None:
    record = build_record(metadata=(("note", "café"),))

    assert "caf\\u00e9" in serialize_qualification_evidence(record)


def test_serialization_contains_no_python_repr_artifacts() -> None:
    serialized = serialize_qualification_evidence(build_record())

    assert "object at 0x" not in serialized
    assert "MappingProxyType" not in serialized


def test_repeated_serialization_is_identical() -> None:
    record = build_record()

    assert serialize_qualification_evidence(record) == serialize_qualification_evidence(
        record
    )


def test_digest_is_reproducible() -> None:
    assert build_record().integrity.digest == build_record().integrity.digest


def test_digest_verification_succeeds() -> None:
    assert verify_evidence_digest(build_record()) is True


def test_modified_record_fails_digest_verification() -> None:
    modified = replace(build_record(), safe_operator_message="Changed safe message.")

    assert verify_evidence_digest(modified) is False


def test_missing_digest_fails_verification() -> None:
    record = build_record()
    without_digest = replace(
        record,
        integrity=replace(record.integrity, digest=None),
    )

    with pytest.raises(EvidenceIntegrityError):
        verify_evidence_digest(without_digest)


def test_digest_is_not_described_as_signature() -> None:
    source = (
        PROJECT_ROOT / "volcanoes/application/qualification/evidence.py"
    ).read_text(encoding="utf-8")

    assert "digital signature" in source
    assert "tamper-proof" not in source


def test_secret_like_metadata_key_is_redacted() -> None:
    record = build_record(metadata=(("api_key", SECRET_SENTINEL),))

    assert record.metadata["api_key"] == REDACTED_VALUE
    assert record.redaction.redacted_fields == ("api_key",)


def test_severe_raw_payload_field_is_rejected() -> None:
    with pytest.raises(EvidenceRedactionError):
        build_record(metadata=(("raw_payload", "{}"),))


def test_safe_message_secret_marker_is_redacted() -> None:
    record = build_record(sample_intent(message=f"token {SECRET_SENTINEL}"))

    assert record.safe_operator_message == REDACTED_VALUE
    assert "safe_operator_message" in record.redaction.redacted_fields


def test_secret_does_not_appear_in_exception_text() -> None:
    with pytest.raises(EvidenceRedactionError) as error_info:
        build_record(metadata=(("raw_payload", SECRET_SENTINEL),))

    assert SECRET_SENTINEL not in str(error_info.value)


def test_secret_does_not_appear_in_serialized_evidence() -> None:
    record = build_record(metadata=(("access_token", SECRET_SENTINEL),))

    assert SECRET_SENTINEL not in serialize_qualification_evidence(record)


def test_secret_does_not_appear_in_record_id_or_digest_metadata() -> None:
    record = build_record(metadata=(("password", SECRET_SENTINEL),))

    assert SECRET_SENTINEL not in record.evidence_id
    assert SECRET_SENTINEL not in (record.integrity.digest or "")


def test_absolute_local_path_is_rejected() -> None:
    with pytest.raises(EvidenceRedactionError):
        build_record(metadata=(("path", "/Users/example/private.txt"),))


def test_exception_objects_are_rejected_as_metadata() -> None:
    with pytest.raises(EvidenceValidationError):
        build_record(metadata=(("error", ValueError("unsafe")),))  # type: ignore[arg-type]


def test_callables_are_rejected_as_metadata() -> None:
    with pytest.raises(EvidenceValidationError):
        build_record(metadata=(("callback", lambda: None),))  # type: ignore[arg-type]


def test_sets_are_rejected_as_metadata() -> None:
    with pytest.raises(EvidenceValidationError):
        build_record(metadata=(("set", {"unsafe"}),))  # type: ignore[arg-type]


def test_unsupported_nested_mappings_are_rejected() -> None:
    with pytest.raises(EvidenceValidationError):
        build_record(metadata=(("nested", {"key": "value"}),))  # type: ignore[arg-type]


def test_metadata_ordering_is_deterministic() -> None:
    first = build_record(metadata=(("zeta", "last"), ("alpha", "first")))
    second = build_record(metadata=(("alpha", "first"), ("zeta", "last")))

    assert serialize_qualification_evidence(first) == serialize_qualification_evidence(
        second
    )


def test_duplicate_equivalent_record_is_idempotent() -> None:
    recorder = InMemoryCanonicalQualificationEvidenceRecorder(occurred_at=FIXED_TIME)
    intent = sample_intent()

    first = recorder.record((intent,))
    second = recorder.record((intent,))

    assert first == second
    assert len(recorder.records) == 1


def test_duplicate_conflicting_record_raises_typed_conflict() -> None:
    recorder = InMemoryCanonicalQualificationEvidenceRecorder(
        occurred_at=FIXED_TIME,
        metadata=(("alpha", "first"),),
    )
    intent = sample_intent()
    recorder.record((intent,))
    recorder_with_conflict = InMemoryCanonicalQualificationEvidenceRecorder(
        occurred_at=FIXED_TIME,
        metadata=(("alpha", "different"),),
    )
    recorder_with_conflict._records = recorder._records  # type: ignore[attr-defined]
    recorder_with_conflict._order = recorder._order  # type: ignore[attr-defined]

    with pytest.raises(EvidenceRecordConflictError):
        recorder_with_conflict.record((intent,))


def test_existing_record_remains_unchanged_after_conflict() -> None:
    recorder = InMemoryCanonicalQualificationEvidenceRecorder(
        occurred_at=FIXED_TIME,
        metadata=(("alpha", "first"),),
    )
    intent = sample_intent()
    recorder.record((intent,))
    before = recorder.records
    conflict = InMemoryCanonicalQualificationEvidenceRecorder(
        occurred_at=FIXED_TIME,
        metadata=(("alpha", "different"),),
    )
    conflict._records = recorder._records  # type: ignore[attr-defined]
    conflict._order = recorder._order  # type: ignore[attr-defined]

    with pytest.raises(EvidenceRecordConflictError):
        conflict.record((intent,))

    assert recorder.records == before


def test_recorder_preserves_insertion_order() -> None:
    recorder = InMemoryCanonicalQualificationEvidenceRecorder(occurred_at=FIXED_TIME)
    first = sample_intent()
    second = sample_intent(
        event_type=QualificationEventType.PRECHECKS_PASSED,
        source=QualificationState.PRECHECK_PENDING,
        destination=QualificationState.READY_FOR_APPROVAL,
        previous_revision=1,
        next_revision=2,
    )

    recorder.record((first, second))

    assert tuple(record.transition_id for record in recorder.records) == (
        "PQ-TRN-001",
        "PQ-TRN-001",
    )
    assert tuple(record.event_type for record in recorder.records) == (
        "START_QUALIFICATION",
        "PRECHECKS_PASSED",
    )


def test_recorder_returns_stable_evidence_references() -> None:
    recorder = InMemoryCanonicalQualificationEvidenceRecorder(occurred_at=FIXED_TIME)

    references = recorder.record((sample_intent(),))

    assert references[0].evidence_id == recorder.records[0].evidence_id
    assert references[0].transition_id == "PQ-TRN-001"
    assert references[0].correlation_id == CORRELATION_ID


def test_application_service_works_with_canonical_recorder() -> None:
    service, _repository, recorder = canonical_service_stack()

    result = service.execute(
        QualificationApplicationCommand(
            qualification_run_id=RUN_ID,
            qualification_scenario_id=SCENARIO_ID,
            correlation_id=CORRELATION_ID,
            event_type=QualificationEventType.START_QUALIFICATION,
            expected_revision=StateRevision(0),
            command_id=CommandId("command-start"),
            idempotency_key=IdempotencyKey("idem-start"),
            actor_type=ActorType.APPLICATION,
            satisfied_guards=frozenset(
                {Guard.SCENARIO_AUTHORIZED, Guard.PAPER_ENVIRONMENT}
            ),
        )
    )

    assert result.accepted is True
    assert len(recorder.records) == 1
    assert verify_evidence_digest(recorder.records[0]) is True


def test_scenario_harness_works_with_canonical_recorder() -> None:
    result, recorder = run_scenario_with_canonical_recorder()

    assert result.harness_status is ScenarioHarnessStatus.PASSED
    assert len(recorder.records) == len(DEFAULT_TRACE)


def test_default_scenario_canonical_evidence_trace_matches_scenario_trace() -> None:
    result, recorder = run_scenario_with_canonical_recorder()

    assert tuple(record.transition_id for record in recorder.records) == DEFAULT_TRACE
    assert (
        tuple(record.transition_id for record in recorder.records)
        == result.transition_trace
    )


def test_default_scenario_evidence_revisions_match_scenario_revisions() -> None:
    result, recorder = run_scenario_with_canonical_recorder()

    assert (
        tuple(record.next_revision for record in recorder.records)
        == result.revisions_observed
    )


def test_replay_scenario_produces_no_duplicate_transition_evidence() -> None:
    service, repository, recorder = canonical_service_stack()
    harness = QualificationScenarioHarness(service=service, repository=repository)
    result = harness.run(
        duplicate_command_replay_scenario(),
        execution_context=ScenarioExecutionContext(RUN_ID, CORRELATION_ID),
    )

    assert result.harness_status is ScenarioHarnessStatus.PASSED
    assert len(recorder.records) == 6
    assert result.revisions_observed[-1] == 6


def test_idempotency_conflict_does_not_produce_false_accepted_evidence() -> None:
    service, repository, recorder = canonical_service_stack()
    harness = QualificationScenarioHarness(service=service, repository=repository)
    result = harness.run(
        idempotency_conflict_scenario(),
        execution_context=ScenarioExecutionContext(RUN_ID, CORRELATION_ID),
    )

    assert result.harness_status is ScenarioHarnessStatus.PASSED
    assert tuple(record.transition_id for record in recorder.records) == ("PQ-TRN-001",)


def test_uncertain_submission_evidence_marks_reconciliation_required() -> None:
    service, repository, recorder = canonical_service_stack()
    harness = QualificationScenarioHarness(service=service, repository=repository)
    result = harness.run(
        uncertain_submission_scenario(),
        execution_context=ScenarioExecutionContext(RUN_ID, CORRELATION_ID),
    )

    assert result.harness_status is ScenarioHarnessStatus.PASSED
    assert recorder.records[-1].evidence_type is (
        QualificationEvidenceType.QUALIFICATION_RECONCILIATION_REQUIRED
    )


def test_terminal_qualification_evidence_records_passed_only_at_finalization() -> None:
    _result, recorder = run_scenario_with_canonical_recorder()

    assert (
        tuple(record.qualification_result for record in recorder.records[:-1])
        == ("PENDING",) * 9
    )
    assert recorder.records[-1].qualification_result == "PASSED"


def test_operator_rejection_evidence_does_not_imply_broker_submission() -> None:
    service, repository, recorder = canonical_service_stack()
    harness = QualificationScenarioHarness(service=service, repository=repository)
    result = harness.run(
        operator_rejection_scenario(),
        execution_context=ScenarioExecutionContext(RUN_ID, CORRELATION_ID),
    )

    assert result.harness_status is ScenarioHarnessStatus.PASSED
    assert (
        SideEffectIntentType.SEND_BROKER_REQUEST
        not in result.side_effect_intents_observed
    )
    assert all(
        record.event_type != "BROKER_REQUEST_SENT" for record in recorder.records
    )


def test_precheck_failure_evidence_does_not_imply_approval() -> None:
    service, repository, recorder = canonical_service_stack()
    harness = QualificationScenarioHarness(service=service, repository=repository)
    result = harness.run(
        precheck_failure_scenario(),
        execution_context=ScenarioExecutionContext(RUN_ID, CORRELATION_ID),
    )

    assert result.harness_status is ScenarioHarnessStatus.PASSED
    assert all(record.actor_type != "OPERATOR" for record in recorder.records)


def test_emergency_stop_evidence_does_not_imply_effect_execution() -> None:
    service, repository, recorder = canonical_service_stack()
    harness = QualificationScenarioHarness(service=service, repository=repository)
    result = harness.run(
        emergency_stop_scenario(),
        execution_context=ScenarioExecutionContext(RUN_ID, CORRELATION_ID),
    )

    assert result.harness_status is ScenarioHarnessStatus.PASSED
    assert len(recorder.records) == 4
    assert (
        SideEffectIntentType.SEND_BROKER_REQUEST
        not in result.side_effect_intents_observed
    )


def test_no_broker_sdk_object_can_be_stored() -> None:
    class BrokerSdkObject:
        pass

    with pytest.raises(EvidenceValidationError):
        build_record(metadata=(("broker_object", BrokerSdkObject()),))  # type: ignore[arg-type]


def test_identical_complete_scenario_execution_produces_equivalent_evidence_stream() -> (
    None
):
    _first_result, first_recorder = run_scenario_with_canonical_recorder()
    _second_result, second_recorder = run_scenario_with_canonical_recorder()

    assert tuple(
        serialize_qualification_evidence(record) for record in first_recorder.records
    ) == tuple(
        serialize_qualification_evidence(record) for record in second_recorder.records
    )


def test_evidence_record_model_remains_distinct_from_evidence_intent() -> None:
    assert not isinstance(build_record(), EvidenceIntent)


def test_evidence_record_result_remains_distinct_from_qualification_result() -> None:
    record = build_record()

    assert isinstance(record.qualification_result, str)
    assert record.qualification_result == QualificationResult.PENDING.value


def test_no_runtime_file_is_created_by_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_open(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("filesystem access is not allowed")

    monkeypatch.setattr(builtins, "open", fail_open)

    assert build_record().transition_id == "PQ-TRN-001"


def test_no_simulator_state_is_accessed(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = _install_protected_state_access_guard(monkeypatch)
    build_record()

    assert attempts == []


def test_no_environment_variables_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_getenv(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("environment access is not allowed")

    monkeypatch.setattr(os, "getenv", fail_getenv)

    assert build_record().schema_version == QUALIFICATION_EVIDENCE_SCHEMA_VERSION


def test_no_external_event_publisher_is_invoked() -> None:
    source = (
        PROJECT_ROOT / "volcanoes/application/qualification/evidence.py"
    ).read_text(encoding="utf-8")

    assert "EventPublisher" not in source


def test_evidence_type_trace_is_deterministic_for_default_scenario() -> None:
    _result, recorder = run_scenario_with_canonical_recorder()

    assert (
        tuple(record.evidence_type for record in recorder.records)
        == DEFAULT_EVIDENCE_TYPES
    )


def test_compute_digest_matches_record_digest() -> None:
    record = build_record()

    assert compute_evidence_digest(record) == record.integrity.digest
