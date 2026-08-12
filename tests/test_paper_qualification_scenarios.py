"""Scenario-harness tests for Paper qualification reference flows."""

from __future__ import annotations

import builtins
import os
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from volcanoes.application.qualification import (
    CorrelationId,
    DEFAULT_SCENARIO_ID,
    DEFAULT_SCENARIO_VERSION,
    ExecutionPlanKind,
    Guard,
    InMemoryQualificationRunRepository,
    NormalizedBrokerObservation,
    PaperQualificationService,
    QualificationResult,
    QualificationRunId,
    QualificationScenarioHarness,
    QualificationScenarioId,
    QualificationScenarioResult,
    QualificationScenarioSpec,
    QualificationScenarioVersion,
    QualificationState,
    RecordingQualificationEvidenceRecorder,
    ScenarioCategory,
    ScenarioExecutionContext,
    ScenarioHarnessStatus,
    ScenarioValidationError,
    ScenarioValidationReason,
    SideEffectIntentType,
    StateRevision,
    approved_scenario_catalog,
    build_scenario_catalog,
    default_positive_scenario,
    duplicate_broker_observation_scenario,
    duplicate_command_replay_scenario,
    emergency_stop_scenario,
    idempotency_conflict_scenario,
    operator_rejection_scenario,
    precheck_failure_scenario,
    scenario_by_id,
    uncertain_submission_scenario,
    validate_scenario_spec,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = QualificationRunId("scenario-run-001")
CORRELATION_ID = CorrelationId("scenario-correlation-001")
SECRET_SENTINEL = "SECRET API_KEY TOKEN PASSWORD"
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


def harness_stack() -> tuple[
    QualificationScenarioHarness,
    InMemoryQualificationRunRepository,
    RecordingQualificationEvidenceRecorder,
]:
    repository = InMemoryQualificationRunRepository()
    recorder = RecordingQualificationEvidenceRecorder()
    service = PaperQualificationService(repository, recorder)
    return (
        QualificationScenarioHarness(service=service, repository=repository),
        repository,
        recorder,
    )


def run_scenario(
    scenario: QualificationScenarioSpec,
) -> tuple[
    QualificationScenarioResult,
    InMemoryQualificationRunRepository,
    RecordingQualificationEvidenceRecorder,
]:
    harness, repository, recorder = harness_stack()
    result = harness.run(
        scenario,
        execution_context=ScenarioExecutionContext(
            qualification_run_id=RUN_ID,
            correlation_id=CORRELATION_ID,
        ),
    )
    return result, repository, recorder


def assert_passed(result: QualificationScenarioResult) -> None:
    assert result.harness_status is ScenarioHarnessStatus.PASSED
    assert result.assertion_failures == ()
    assert result.external_actions_executed is False


def test_scenario_catalog_contains_mandatory_default_scenario() -> None:
    catalog = approved_scenario_catalog()

    default = scenario_by_id(DEFAULT_SCENARIO_ID, DEFAULT_SCENARIO_VERSION)

    assert default in catalog
    assert default.mandatory is True
    assert default.category is ScenarioCategory.POSITIVE


def test_scenario_ids_and_versions_are_unique() -> None:
    keys = {
        (scenario.scenario_id, scenario.scenario_version)
        for scenario in approved_scenario_catalog()
    }

    assert len(keys) == len(approved_scenario_catalog())


def test_duplicate_scenario_id_version_is_rejected() -> None:
    scenario = default_positive_scenario()

    with pytest.raises(ScenarioValidationError) as error_info:
        build_scenario_catalog((scenario, scenario))

    assert (
        error_info.value.reason_code
        is ScenarioValidationReason.DUPLICATE_SCENARIO_ID_VERSION
    )


def test_default_scenario_validates_successfully() -> None:
    validate_scenario_spec(default_positive_scenario())


def test_default_scenario_runs_to_qualified() -> None:
    result, _repository, _recorder = run_scenario(default_positive_scenario())

    assert_passed(result)
    assert result.terminal_workflow_state is QualificationState.QUALIFIED


def test_default_scenario_result_is_passed() -> None:
    result, _repository, _recorder = run_scenario(default_positive_scenario())

    assert result.terminal_qualification_result is QualificationResult.PASSED


def test_default_scenario_produces_expected_transition_sequence() -> None:
    result, _repository, _recorder = run_scenario(default_positive_scenario())

    assert result.transition_trace == DEFAULT_TRACE


def test_default_scenario_revision_trace_is_monotonic() -> None:
    result, _repository, _recorder = run_scenario(default_positive_scenario())

    assert result.revisions_observed == tuple(
        StateRevision(index) for index in range(1, 11)
    )


def test_default_scenario_final_revision_matches_accepted_steps() -> None:
    result, _repository, _recorder = run_scenario(default_positive_scenario())

    assert result.terminal_run is not None
    assert result.terminal_run.state_revision == len(DEFAULT_TRACE)


def test_default_scenario_produces_expected_execution_plan_intents() -> None:
    result, _repository, _recorder = run_scenario(default_positive_scenario())

    assert result.side_effect_intents_observed == (
        SideEffectIntentType.REQUEST_OPERATOR_APPROVAL,
        SideEffectIntentType.RECORD_OPERATOR_APPROVAL,
        SideEffectIntentType.PREPARE_BROKER_SUBMISSION,
        SideEffectIntentType.SEND_BROKER_REQUEST,
        SideEffectIntentType.RECORD_BROKER_REFERENCE,
        SideEffectIntentType.REQUEST_BROKER_CANCELLATION,
        SideEffectIntentType.RECORD_BROKER_LIFECYCLE,
        SideEffectIntentType.FINALIZE_QUALIFICATION,
    )


def test_default_scenario_does_not_execute_broker_behavior() -> None:
    result, repository, recorder = run_scenario(default_positive_scenario())

    assert result.external_actions_executed is False
    assert "save" in repository.operations
    assert recorder.operations == ["record_evidence"] * len(DEFAULT_TRACE)


def test_default_scenario_records_expected_evidence_intents() -> None:
    result, _repository, recorder = run_scenario(default_positive_scenario())

    assert len(result.evidence_records_observed) == len(DEFAULT_TRACE)
    assert tuple(intent.transition_id for intent in recorder.intents) == DEFAULT_TRACE
    assert {intent.correlation_id for intent in recorder.intents} == {CORRELATION_ID}


def test_operator_rejection_scenario_behaves_as_specified() -> None:
    result, _repository, _recorder = run_scenario(operator_rejection_scenario())

    assert_passed(result)
    assert result.transition_trace[-1] == "PQ-TRN-007"
    assert result.terminal_workflow_state is QualificationState.REJECTED
    assert result.terminal_qualification_result is QualificationResult.FAILED
    assert (
        SideEffectIntentType.SEND_BROKER_REQUEST
        not in result.side_effect_intents_observed
    )


def test_precheck_failure_scenario_produces_no_broker_plan() -> None:
    result, _repository, _recorder = run_scenario(precheck_failure_scenario())

    assert_passed(result)
    assert result.terminal_workflow_state is QualificationState.PRECHECK_FAILED
    assert ExecutionPlanKind.BROKER_ACTION_PROPOSED not in {
        kind for plan in result.execution_plans_observed for kind in plan
    }


def test_emergency_stop_scenario_blocks_consequential_action() -> None:
    result, _repository, _recorder = run_scenario(emergency_stop_scenario())

    assert_passed(result)
    assert result.transition_trace[-1] == "INVALID"
    assert result.terminal_workflow_state is QualificationState.APPROVED
    assert (
        SideEffectIntentType.SEND_BROKER_REQUEST
        not in result.side_effect_intents_observed
    )


def test_uncertain_submission_scenario_enters_reconciliation_semantics() -> None:
    result, _repository, _recorder = run_scenario(uncertain_submission_scenario())

    assert_passed(result)
    assert result.terminal_workflow_state is QualificationState.RECONCILIATION_REQUIRED
    assert result.terminal_qualification_result is QualificationResult.INCONCLUSIVE
    assert result.reconciliation_required is True


def test_duplicate_command_replay_does_not_increment_revision() -> None:
    result, _repository, _recorder = run_scenario(duplicate_command_replay_scenario())

    assert_passed(result)
    assert result.revisions_observed[-2:] == (StateRevision(6), StateRevision(6))


def test_duplicate_command_replay_does_not_reproduce_consequential_plan() -> None:
    result, _repository, _recorder = run_scenario(duplicate_command_replay_scenario())

    replay_step = result.step_results[-1]
    assert replay_step.replayed is True
    assert replay_step.side_effect_intents == ()
    assert replay_step.evidence_records == ()


def test_idempotency_conflict_preserves_state() -> None:
    result, _repository, recorder = run_scenario(idempotency_conflict_scenario())

    assert_passed(result)
    assert result.transition_trace == ("PQ-TRN-001", "INVALID")
    assert result.terminal_workflow_state is QualificationState.PRECHECK_PENDING
    assert result.revisions_observed == (StateRevision(1), StateRevision(1))
    assert len(recorder.intents) == 1


def test_duplicate_broker_observation_is_safe() -> None:
    result, _repository, recorder = run_scenario(
        duplicate_broker_observation_scenario()
    )

    assert_passed(result)
    assert result.transition_trace[-2:] == ("PQ-TRN-011", "PQ-TRN-011")
    assert result.revisions_observed[-2:] == (StateRevision(7), StateRevision(7))
    assert len(recorder.intents) == 7


def test_empty_scenario_id_is_rejected() -> None:
    invalid = replace(
        default_positive_scenario(), scenario_id=QualificationScenarioId("")
    )

    result, _repository, _recorder = run_scenario(invalid)

    assert result.harness_status is ScenarioHarnessStatus.INVALID_SPECIFICATION
    assert "Scenario ID cannot be empty" in result.assertion_failures[0]


def test_unsupported_scenario_version_is_rejected() -> None:
    invalid = replace(
        default_positive_scenario(),
        scenario_version=QualificationScenarioVersion("v2"),
    )

    result, _repository, _recorder = run_scenario(invalid)

    assert result.harness_status is ScenarioHarnessStatus.INVALID_SPECIFICATION


def test_duplicate_step_id_is_rejected() -> None:
    scenario = default_positive_scenario()
    duplicate = replace(
        scenario.steps[1],
        step_id=scenario.steps[0].step_id,
    )
    invalid = replace(
        scenario, steps=(scenario.steps[0], duplicate, *scenario.steps[2:])
    )

    result, _repository, _recorder = run_scenario(invalid)

    assert result.harness_status is ScenarioHarnessStatus.INVALID_SPECIFICATION


def test_non_sequential_steps_are_rejected() -> None:
    scenario = default_positive_scenario()
    invalid_step = replace(scenario.steps[1], sequence=99)
    invalid = replace(
        scenario, steps=(scenario.steps[0], invalid_step, *scenario.steps[2:])
    )

    result, _repository, _recorder = run_scenario(invalid)

    assert result.harness_status is ScenarioHarnessStatus.INVALID_SPECIFICATION


def test_missing_initial_creation_step_is_rejected() -> None:
    scenario = default_positive_scenario()
    invalid = replace(scenario, steps=scenario.steps[1:])

    result, _repository, _recorder = run_scenario(invalid)

    assert result.harness_status is ScenarioHarnessStatus.INVALID_SPECIFICATION


def test_live_environment_scenario_is_rejected() -> None:
    invalid = replace(default_positive_scenario(), environment="LIVE")

    result, _repository, _recorder = run_scenario(invalid)

    assert result.harness_status is ScenarioHarnessStatus.INVALID_SPECIFICATION


def test_step_after_terminal_state_is_rejected() -> None:
    scenario = default_positive_scenario()
    invalid = replace(scenario, steps=(*scenario.steps, scenario.steps[-1]))

    result, _repository, _recorder = run_scenario(invalid)

    assert result.harness_status is ScenarioHarnessStatus.INVALID_SPECIFICATION


def test_expected_rejection_can_be_asserted_successfully() -> None:
    result, _repository, _recorder = run_scenario(emergency_stop_scenario())

    assert result.step_results[-1].harness_status is (
        ScenarioHarnessStatus.EXPECTED_REJECTION_CONFIRMED
    )


def test_unexpected_rejection_fails_the_scenario() -> None:
    scenario = default_positive_scenario()
    broken_step = replace(
        scenario.steps[1], guards=frozenset({Guard.PAPER_ENVIRONMENT})
    )
    broken = replace(
        scenario, steps=(scenario.steps[0], broken_step, *scenario.steps[2:])
    )

    result, _repository, _recorder = run_scenario(broken)

    assert result.harness_status is ScenarioHarnessStatus.FAILED
    assert result.failed_step_id == broken_step.step_id


def test_unexpected_transition_id_fails_the_scenario() -> None:
    scenario = default_positive_scenario()
    broken_step = replace(scenario.steps[0], expected_transition_id="PQ-TRN-002")
    broken = replace(scenario, steps=(broken_step, *scenario.steps[1:]))

    result, _repository, _recorder = run_scenario(broken)

    assert result.harness_status is ScenarioHarnessStatus.FAILED
    assert "transition expected" in result.assertion_failures[0]


def test_unexpected_destination_state_fails_the_scenario() -> None:
    scenario = default_positive_scenario()
    broken_expectation = replace(
        scenario.steps[0].expectation,
        destination_state=QualificationState.APPROVED,
    )
    broken_step = replace(scenario.steps[0], expectation=broken_expectation)
    broken = replace(scenario, steps=(broken_step, *scenario.steps[1:]))

    result, _repository, _recorder = run_scenario(broken)

    assert result.harness_status is ScenarioHarnessStatus.FAILED
    assert "destination expected" in result.assertion_failures[0]


def test_unexpected_result_fails_the_scenario() -> None:
    scenario = default_positive_scenario()
    broken_expectation = replace(
        scenario.steps[0].expectation,
        qualification_result=QualificationResult.FAILED,
    )
    broken_step = replace(scenario.steps[0], expectation=broken_expectation)
    broken = replace(scenario, steps=(broken_step, *scenario.steps[1:]))

    result, _repository, _recorder = run_scenario(broken)

    assert result.harness_status is ScenarioHarnessStatus.FAILED
    assert "result expected" in result.assertion_failures[0]


def test_unexpected_side_effect_intent_fails_the_scenario() -> None:
    scenario = default_positive_scenario()
    broken_expectation = replace(
        scenario.steps[2].expectation,
        side_effect_intents=(SideEffectIntentType.SEND_BROKER_REQUEST,),
    )
    broken_step = replace(scenario.steps[2], expectation=broken_expectation)
    broken = replace(
        scenario, steps=(*scenario.steps[:2], broken_step, *scenario.steps[3:])
    )

    result, _repository, _recorder = run_scenario(broken)

    assert result.harness_status is ScenarioHarnessStatus.FAILED
    assert "side-effect intents expected" in result.assertion_failures[0]


def test_unexpected_revision_fails_the_scenario() -> None:
    scenario = default_positive_scenario()
    broken_expectation = replace(
        scenario.steps[0].expectation, revision=StateRevision(9)
    )
    broken_step = replace(scenario.steps[0], expectation=broken_expectation)
    broken = replace(scenario, steps=(broken_step, *scenario.steps[1:]))

    result, _repository, _recorder = run_scenario(broken)

    assert result.harness_status is ScenarioHarnessStatus.FAILED
    assert "revision expected" in result.assertion_failures[0]


def test_evidence_mismatch_fails_the_scenario() -> None:
    scenario = default_positive_scenario()
    broken_expectation = replace(scenario.steps[0].expectation, evidence_recorded=False)
    broken_step = replace(scenario.steps[0], expectation=broken_expectation)
    broken = replace(scenario, steps=(broken_step, *scenario.steps[1:]))

    result, _repository, _recorder = run_scenario(broken)

    assert result.harness_status is ScenarioHarnessStatus.FAILED
    assert "evidence recorded expected" in result.assertion_failures[0]


def test_port_failure_is_distinguished_from_assertion_failure() -> None:
    harness, repository, _recorder = harness_stack()
    repository.fail_get = True

    result = harness.run(
        default_positive_scenario(),
        execution_context=ScenarioExecutionContext(RUN_ID, CORRELATION_ID),
    )

    assert result.harness_status is ScenarioHarnessStatus.FAILED
    assert (
        result.step_results[0].harness_status is ScenarioHarnessStatus.APPLICATION_ERROR
    )


def test_identical_input_yields_equivalent_logical_scenario_result() -> None:
    first, _first_repo, _first_recorder = run_scenario(default_positive_scenario())
    second, _second_repo, _second_recorder = run_scenario(default_positive_scenario())

    assert first.transition_trace == second.transition_trace
    assert first.revisions_observed == second.revisions_observed
    assert first.side_effect_intents_observed == second.side_effect_intents_observed
    assert first.safe_summary == second.safe_summary


def test_secret_fixture_does_not_appear_in_result_evidence_or_error_text() -> None:
    scenario = default_positive_scenario()
    secret_step = replace(
        scenario.steps[0],
        payload_fingerprint=(SECRET_SENTINEL,),
    )
    invalid = replace(scenario, steps=(secret_step, *scenario.steps[1:]))

    result, _repository, recorder = run_scenario(invalid)
    rendered = repr((result, recorder.intents))

    assert result.harness_status is ScenarioHarnessStatus.INVALID_SPECIFICATION
    assert "API_KEY" not in rendered
    assert "TOKEN" not in rendered
    assert "PASSWORD" not in rendered


def test_harness_stops_after_first_unexpected_failure() -> None:
    scenario = default_positive_scenario()
    broken_expectation = replace(
        scenario.steps[0].expectation, revision=StateRevision(9)
    )
    broken_step = replace(scenario.steps[0], expectation=broken_expectation)
    broken = replace(scenario, steps=(broken_step, *scenario.steps[1:]))

    result, _repository, _recorder = run_scenario(broken)

    assert result.completed_steps == 1


def test_scenario_result_remains_distinct_from_qualification_result() -> None:
    result, _repository, _recorder = run_scenario(default_positive_scenario())

    assert isinstance(result.harness_status, ScenarioHarnessStatus)
    assert isinstance(result.terminal_qualification_result, QualificationResult)
    assert result.harness_status.value == result.terminal_qualification_result.value


def test_scenario_models_are_immutable() -> None:
    scenario = default_positive_scenario()

    with pytest.raises(FrozenInstanceError):
        scenario.title = "Changed"  # type: ignore[misc]


def test_normalized_broker_observations_are_immutable_fixtures() -> None:
    observation = NormalizedBrokerObservation(
        observation_type="BROKER_ACKNOWLEDGED",
        object_reference="reference",
        facts=("safe",),
    )

    with pytest.raises(FrozenInstanceError):
        observation.observation_type = "CHANGED"  # type: ignore[misc]


def test_harness_never_invokes_apply_transition_directly() -> None:
    source = (
        PROJECT_ROOT / "volcanoes/application/qualification/scenario_harness.py"
    ).read_text(encoding="utf-8")

    assert "apply_transition" not in source


def test_no_runtime_file_is_created_or_read_by_harness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_open(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("filesystem access is not allowed")

    monkeypatch.setattr(builtins, "open", fail_open)

    result, _repository, _recorder = run_scenario(default_positive_scenario())

    assert_passed(result)


def test_no_environment_variable_is_read_by_harness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_getenv(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("environment access is not allowed")

    monkeypatch.setattr(os, "getenv", fail_getenv)

    result, _repository, _recorder = run_scenario(default_positive_scenario())

    assert_passed(result)


def test_no_simulator_state_changes() -> None:
    simulator_state = PROJECT_ROOT / "state/simulated_broker.json"
    before = simulator_state.read_bytes() if simulator_state.exists() else b""

    result, _repository, _recorder = run_scenario(default_positive_scenario())

    after = simulator_state.read_bytes() if simulator_state.exists() else b""
    assert_passed(result)
    assert after == before


def test_all_catalog_scenarios_run_successfully() -> None:
    statuses = []
    for scenario in approved_scenario_catalog():
        result, _repository, _recorder = run_scenario(scenario)
        statuses.append(result.harness_status)

    assert statuses == [ScenarioHarnessStatus.PASSED] * len(statuses)


def test_scenario_lookup_by_id_and_version_is_stable() -> None:
    scenario = scenario_by_id(DEFAULT_SCENARIO_ID, DEFAULT_SCENARIO_VERSION)

    assert scenario.scenario_id == DEFAULT_SCENARIO_ID
    assert scenario.scenario_version == DEFAULT_SCENARIO_VERSION
