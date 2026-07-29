"""Deterministic runner for approved Paper qualification scenarios."""

from __future__ import annotations

from volcanoes.application.qualification.contracts import (
    PaperQualificationRun,
    QualificationState,
    SideEffectIntentType,
    StateRevision,
)
from volcanoes.application.qualification.ports import QualificationRunRepository
from volcanoes.application.qualification.scenario_models import (
    QualificationScenarioResult,
    QualificationScenarioSpec,
    QualificationScenarioStep,
    QualificationScenarioStepResult,
    ScenarioExecutionContext,
    ScenarioHarnessStatus,
    ScenarioValidationError,
)
from volcanoes.application.qualification.scenario_validation import (
    validate_scenario_spec,
)
from volcanoes.application.qualification.service import (
    ExecutionPlanKind,
    PaperQualificationService,
    QualificationApplicationCommand,
    QualificationApplicationError,
    QualificationApplicationResult,
)


class QualificationScenarioHarness:
    """Execute scenario specifications through PaperQualificationService."""

    def __init__(
        self,
        *,
        service: PaperQualificationService,
        repository: QualificationRunRepository,
    ) -> None:
        self._service = service
        self._repository = repository

    def run(
        self,
        scenario: QualificationScenarioSpec,
        *,
        execution_context: ScenarioExecutionContext,
    ) -> QualificationScenarioResult:
        """Run one scenario without executing broker or infrastructure effects."""

        try:
            validate_scenario_spec(scenario)
        except ScenarioValidationError as error:
            return _invalid_specification_result(
                scenario,
                execution_context,
                str(error),
            )

        step_results: list[QualificationScenarioStepResult] = []
        failures: list[str] = []
        terminal_run = None

        for step in scenario.steps:
            try:
                current_run = self._repository.get(
                    execution_context.qualification_run_id
                )
            except Exception:
                message = "Qualification run repository could not be read."
                failures.append(message)
                step_results.append(_application_error_step(step, message))
                break
            state_failure = _source_state_failure(step, current_run)
            if state_failure is not None:
                failures.append(state_failure)
                step_results.append(_failed_precheck_step(step, state_failure))
                break

            try:
                app_result = self._service.execute(
                    _command_for_step(scenario, step, execution_context)
                )
            except QualificationApplicationError as error:
                failures.append(error.safe_message)
                step_results.append(_application_error_step(step, error.safe_message))
                break

            step_result = _assert_step(step, app_result)
            step_results.append(step_result)
            terminal_run = app_result.resulting_run
            if step_result.assertion_failures:
                failures.extend(step_result.assertion_failures)
                if scenario.execution_policy.fail_fast:
                    break
            if step.expected_rejection and not (
                scenario.execution_policy.continue_after_expected_rejection
            ):
                break

        if failures:
            final_run = terminal_run
        else:
            final_run = terminal_run or self._repository.get(
                execution_context.qualification_run_id
            )
        terminal_failures = _terminal_failures(scenario, final_run)
        failures.extend(terminal_failures)

        return _scenario_result(
            scenario=scenario,
            execution_context=execution_context,
            step_results=tuple(step_results),
            final_run=final_run,
            failures=tuple(failures),
        )


def _command_for_step(
    scenario: QualificationScenarioSpec,
    step: QualificationScenarioStep,
    execution_context: ScenarioExecutionContext,
) -> QualificationApplicationCommand:
    object_reference = step.object_reference
    fingerprint = step.payload_fingerprint
    if step.observation is not None:
        object_reference = step.observation.object_reference
        fingerprint = (
            step.observation.observation_type,
            *step.observation.facts,
            *fingerprint,
        )
    return QualificationApplicationCommand(
        qualification_run_id=execution_context.qualification_run_id,
        qualification_scenario_id=scenario.scenario_id,
        correlation_id=execution_context.correlation_id,
        event_type=step.event_type,
        expected_revision=step.expected_revision,
        command_id=step.command_id,
        idempotency_key=step.idempotency_key,
        actor_type=step.actor_type,
        satisfied_guards=step.guards,
        payload_fingerprint=fingerprint,
        object_reference=object_reference,
        environment=scenario.environment,
    )


def _source_state_failure(
    step: QualificationScenarioStep,
    current_run: object,
) -> str | None:
    if step.sequence == 1 and current_run is None:
        return None
    if current_run is None:
        return "Scenario run was not created before this step."
    state = getattr(current_run, "state", None)
    if state is not step.expected_source_state:
        return (
            f"{step.step_id}: expected source state "
            f"{step.expected_source_state.value}, observed "
            f"{state.value if isinstance(state, QualificationState) else state}."
        )
    return None


def _assert_step(
    step: QualificationScenarioStep,
    app_result: QualificationApplicationResult,
) -> QualificationScenarioStepResult:
    failures: list[str] = []
    decision = app_result.transition_decision
    plan = app_result.execution_plan
    resulting_run = app_result.resulting_run

    if app_result.accepted is not step.expectation.accepted:
        failures.append(
            f"{step.step_id}: accepted expected "
            f"{step.expectation.accepted}, observed {app_result.accepted}."
        )
    if decision is None:
        failures.append(f"{step.step_id}: transition decision missing.")
    elif decision.transition_id != step.expected_transition_id:
        failures.append(
            f"{step.step_id}: transition expected {step.expected_transition_id}, "
            f"observed {decision.transition_id}."
        )
    if resulting_run is not None:
        if resulting_run.state is not step.expectation.destination_state:
            failures.append(
                f"{step.step_id}: destination expected "
                f"{step.expectation.destination_state.value}, observed "
                f"{resulting_run.state.value}."
            )
        if resulting_run.result is not step.expectation.qualification_result:
            failures.append(
                f"{step.step_id}: result expected "
                f"{step.expectation.qualification_result.value}, observed "
                f"{resulting_run.result.value}."
            )
        if resulting_run.state_revision != step.expectation.revision:
            failures.append(
                f"{step.step_id}: revision expected {step.expectation.revision}, "
                f"observed {resulting_run.state_revision}."
            )
    else:
        failures.append(f"{step.step_id}: resulting run missing.")
    if plan is None:
        failures.append(f"{step.step_id}: execution plan missing.")
        plan_kinds: tuple[ExecutionPlanKind, ...] = ()
        side_effects: tuple[SideEffectIntentType, ...] = ()
    else:
        plan_kinds = plan.plan_kinds
        side_effects = tuple(intent.intent_type for intent in plan.side_effect_intents)
        if plan_kinds != step.expectation.execution_plan_kinds:
            failures.append(
                f"{step.step_id}: plan kinds expected "
                f"{step.expectation.execution_plan_kinds}, observed {plan_kinds}."
            )
        if side_effects != step.expectation.side_effect_intents:
            failures.append(
                f"{step.step_id}: side-effect intents expected "
                f"{step.expectation.side_effect_intents}, observed {side_effects}."
            )
    expected_evidence = step.expectation.evidence_recorded
    if bool(app_result.evidence_records) is not expected_evidence:
        failures.append(
            f"{step.step_id}: evidence recorded expected {expected_evidence}, "
            f"observed {bool(app_result.evidence_records)}."
        )
    if app_result.replayed is not step.expectation.replayed:
        failures.append(
            f"{step.step_id}: replay expected {step.expectation.replayed}, "
            f"observed {app_result.replayed}."
        )
    if app_result.reconciliation_required is not (
        step.expectation.reconciliation_required
    ):
        failures.append(
            f"{step.step_id}: reconciliation expected "
            f"{step.expectation.reconciliation_required}, observed "
            f"{app_result.reconciliation_required}."
        )
    if step.expectation.reason_code is not None and (
        app_result.code != step.expectation.reason_code
    ):
        failures.append(
            f"{step.step_id}: reason expected {step.expectation.reason_code}, "
            f"observed {app_result.code}."
        )
    if step.expectation.safe_message_contains is not None and (
        step.expectation.safe_message_contains not in app_result.safe_message
    ):
        failures.append(f"{step.step_id}: safe message did not match expectation.")

    if step.expected_rejection and not failures:
        status = ScenarioHarnessStatus.EXPECTED_REJECTION_CONFIRMED
    elif failures:
        status = ScenarioHarnessStatus.FAILED
    else:
        status = ScenarioHarnessStatus.PASSED
    return QualificationScenarioStepResult(
        step_id=step.step_id,
        sequence=step.sequence,
        harness_status=status,
        application_result=app_result,
        transition_id=decision.transition_id if decision is not None else None,
        source_state=decision.previous_state if decision is not None else None,
        destination_state=resulting_run.state if resulting_run is not None else None,
        revision=(
            StateRevision(resulting_run.state_revision)
            if resulting_run is not None
            else None
        ),
        qualification_result=(
            resulting_run.result if resulting_run is not None else None
        ),
        execution_plan_kinds=plan_kinds,
        side_effect_intents=side_effects,
        evidence_records=app_result.evidence_records,
        replayed=app_result.replayed,
        reconciliation_required=app_result.reconciliation_required,
        assertion_failures=tuple(failures),
        safe_summary=app_result.safe_message,
    )


def _failed_precheck_step(
    step: QualificationScenarioStep,
    failure: str,
) -> QualificationScenarioStepResult:
    return QualificationScenarioStepResult(
        step_id=step.step_id,
        sequence=step.sequence,
        harness_status=ScenarioHarnessStatus.FAILED,
        application_result=None,
        transition_id=None,
        source_state=None,
        destination_state=None,
        revision=None,
        qualification_result=None,
        assertion_failures=(failure,),
        safe_summary=failure,
    )


def _application_error_step(
    step: QualificationScenarioStep,
    message: str,
) -> QualificationScenarioStepResult:
    return QualificationScenarioStepResult(
        step_id=step.step_id,
        sequence=step.sequence,
        harness_status=ScenarioHarnessStatus.APPLICATION_ERROR,
        application_result=None,
        transition_id=None,
        source_state=None,
        destination_state=None,
        revision=None,
        qualification_result=None,
        assertion_failures=(message,),
        safe_summary=message,
    )


def _terminal_failures(
    scenario: QualificationScenarioSpec,
    final_run: object,
) -> tuple[str, ...]:
    if final_run is None:
        return ("Scenario did not produce a qualification run.",)
    observed_state = getattr(final_run, "state", None)
    observed_result = getattr(final_run, "result", None)
    failures: list[str] = []
    if observed_state is not scenario.terminal_expectation.workflow_state:
        failures.append(
            "Terminal state expected "
            f"{scenario.terminal_expectation.workflow_state.value}, observed "
            f"{observed_state.value if isinstance(observed_state, QualificationState) else observed_state}."
        )
    if observed_result is not scenario.terminal_expectation.qualification_result:
        failures.append(
            "Terminal result expected "
            f"{scenario.terminal_expectation.qualification_result.value}, observed "
            f"{getattr(observed_result, 'value', observed_result)}."
        )
    return tuple(failures)


def _scenario_result(
    *,
    scenario: QualificationScenarioSpec,
    execution_context: ScenarioExecutionContext,
    step_results: tuple[QualificationScenarioStepResult, ...],
    final_run: object,
    failures: tuple[str, ...],
) -> QualificationScenarioResult:
    transition_trace = tuple(
        result.transition_id
        for result in step_results
        if result.transition_id is not None
    )
    revisions = tuple(
        result.revision for result in step_results if result.revision is not None
    )
    plan_trace = tuple(result.execution_plan_kinds for result in step_results)
    side_effects = tuple(
        intent
        for result in step_results
        for intent in result.side_effect_intents
        if intent is not SideEffectIntentType.NONE
    )
    evidence_records = tuple(
        evidence for result in step_results for evidence in result.evidence_records
    )
    replay_steps = tuple(result.step_id for result in step_results if result.replayed)
    status = ScenarioHarnessStatus.PASSED
    if failures:
        status = ScenarioHarnessStatus.FAILED
    elif step_results and all(
        result.harness_status is ScenarioHarnessStatus.EXPECTED_REJECTION_CONFIRMED
        for result in step_results
    ):
        status = ScenarioHarnessStatus.EXPECTED_REJECTION_CONFIRMED
    terminal_run = final_run if isinstance(final_run, PaperQualificationRun) else None
    return QualificationScenarioResult(
        scenario_id=scenario.scenario_id,
        scenario_version=scenario.scenario_version,
        title=scenario.title,
        harness_status=status,
        run_id=execution_context.qualification_run_id,
        total_steps=len(scenario.steps),
        completed_steps=len(step_results),
        failed_step_id=step_results[-1].step_id if failures and step_results else None,
        terminal_run=terminal_run,
        terminal_workflow_state=getattr(terminal_run, "state", None),
        terminal_qualification_result=getattr(terminal_run, "result", None),
        step_results=step_results,
        transition_trace=transition_trace,
        revisions_observed=revisions,
        execution_plans_observed=plan_trace,
        side_effect_intents_observed=side_effects,
        evidence_records_observed=evidence_records,
        replay_observations=replay_steps,
        reconciliation_required=any(
            result.reconciliation_required for result in step_results
        ),
        assertion_failures=failures,
        safe_summary=(
            "Scenario executed as expected."
            if not failures
            else "Scenario stopped safely after unexpected behavior."
        ),
        external_actions_executed=False,
    )


def _invalid_specification_result(
    scenario: QualificationScenarioSpec,
    execution_context: ScenarioExecutionContext,
    failure: str,
) -> QualificationScenarioResult:
    return QualificationScenarioResult(
        scenario_id=scenario.scenario_id,
        scenario_version=scenario.scenario_version,
        title=scenario.title,
        harness_status=ScenarioHarnessStatus.INVALID_SPECIFICATION,
        run_id=execution_context.qualification_run_id,
        total_steps=len(scenario.steps),
        completed_steps=0,
        failed_step_id=None,
        terminal_run=None,
        terminal_workflow_state=None,
        terminal_qualification_result=None,
        step_results=(),
        transition_trace=(),
        revisions_observed=(),
        execution_plans_observed=(),
        side_effect_intents_observed=(),
        evidence_records_observed=(),
        replay_observations=(),
        reconciliation_required=False,
        assertion_failures=(failure,),
        safe_summary="Scenario specification was rejected before execution.",
        external_actions_executed=False,
    )
