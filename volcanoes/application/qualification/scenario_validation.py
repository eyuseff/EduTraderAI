"""Validation for immutable qualification scenario specifications."""

from __future__ import annotations

from volcanoes.application.qualification.contracts import (
    ActorType,
    QualificationEventType,
    QualificationResult,
    QualificationState,
    TERMINAL_WORKFLOW_STATES,
)
from volcanoes.application.qualification.scenario_models import (
    QualificationScenarioSpec,
    QualificationScenarioStep,
    ScenarioValidationError,
    ScenarioValidationReason,
)
from volcanoes.application.qualification.state_machine import all_transition_specs

_SUPPORTED_SCENARIO_VERSIONS = frozenset({"v1"})
_SAFE_ENVIRONMENTS = frozenset({"PAPER"})
_SECRET_MARKERS = (
    "API_KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "AUTHORIZATION",
    "ACCOUNT_NUMBER",
)


def validate_scenario_spec(spec: QualificationScenarioSpec) -> None:
    """Reject scenario specifications that cannot be safely executed."""

    if not spec.scenario_id.strip():
        _raise(
            ScenarioValidationReason.EMPTY_SCENARIO_ID,
            "Scenario ID cannot be empty.",
        )
    if spec.scenario_version not in _SUPPORTED_SCENARIO_VERSIONS:
        _raise(
            ScenarioValidationReason.UNSUPPORTED_VERSION,
            "Scenario version is not supported by this harness.",
        )
    if spec.environment not in _SAFE_ENVIRONMENTS:
        _raise(
            ScenarioValidationReason.LIVE_ENVIRONMENT,
            "Only Paper environment scenarios are supported.",
        )
    if not spec.steps or spec.steps[0].event_type is not (
        QualificationEventType.START_QUALIFICATION
    ):
        _raise(
            ScenarioValidationReason.MISSING_INITIAL_CREATION_STEP,
            "The first scenario step must create the qualification run.",
        )
    _validate_unique_steps(spec.steps)
    _validate_step_order(spec.steps)
    _validate_transition_ids(spec.steps)
    _validate_command_identities(spec.steps)
    _validate_step_roles(spec.steps)
    _validate_terminal_expectation(spec)
    _validate_no_secret_fixtures(spec)


def _validate_unique_steps(steps: tuple[QualificationScenarioStep, ...]) -> None:
    seen: set[str] = set()
    for step in steps:
        if step.step_id in seen:
            _raise(
                ScenarioValidationReason.DUPLICATE_STEP_ID,
                "Scenario step IDs must be unique.",
            )
        seen.add(step.step_id)


def _validate_step_order(steps: tuple[QualificationScenarioStep, ...]) -> None:
    for expected_sequence, step in enumerate(steps, start=1):
        if step.sequence != expected_sequence:
            _raise(
                ScenarioValidationReason.NON_SEQUENTIAL_STEPS,
                "Scenario step order must be sequential.",
            )
        if step.expected_revision < 0:
            _raise(
                ScenarioValidationReason.INCONSISTENT_EXPECTED_REVISION,
                "Expected revisions must be non-negative.",
            )
        if not step.expected_transition_id.strip():
            _raise(
                ScenarioValidationReason.MISSING_EXPECTED_TRANSITION_ID,
                "Each scenario step must assert a transition ID.",
            )
        if not isinstance(step.expected_source_state, QualificationState):
            _raise(
                ScenarioValidationReason.MISSING_EXPECTED_SOURCE_STATE,
                "Each scenario step must assert a source state.",
            )
        if step.sequence < len(steps) and step.expectation.destination_state in (
            TERMINAL_WORKFLOW_STATES
        ):
            _raise(
                ScenarioValidationReason.STEP_AFTER_TERMINAL_STATE,
                "Scenario cannot continue after terminal workflow state.",
            )
        if step.expectation.side_effect_intents and not (
            step.expectation.execution_plan_kinds
        ):
            _raise(
                ScenarioValidationReason.CONSEQUENTIAL_STEP_WITHOUT_PLAN,
                "Consequential steps must assert execution-plan behavior.",
            )


def _validate_transition_ids(steps: tuple[QualificationScenarioStep, ...]) -> None:
    valid_transition_ids = {spec.transition_id for spec in all_transition_specs()} | {
        "INVALID"
    }
    for step in steps:
        if step.expected_transition_id not in valid_transition_ids:
            _raise(
                ScenarioValidationReason.UNRECOGNIZED_TRANSITION_ID,
                "Scenario references an unrecognized transition ID.",
            )


def _validate_command_identities(
    steps: tuple[QualificationScenarioStep, ...],
) -> None:
    seen: set[str] = set()
    for step in steps:
        identity = step.idempotency_key
        if identity in seen and not step.replay_verification:
            _raise(
                ScenarioValidationReason.DUPLICATE_COMMAND_IDENTITY,
                "Duplicate command identity requires explicit replay verification.",
            )
        seen.add(identity)


def _validate_step_roles(steps: tuple[QualificationScenarioStep, ...]) -> None:
    broker_truth_events = {
        QualificationEventType.BROKER_ACKNOWLEDGED,
        QualificationEventType.BROKER_PARTIAL_FILL_REPORTED,
        QualificationEventType.BROKER_FILL_REPORTED,
        QualificationEventType.BROKER_CANCELLATION_CONFIRMED,
        QualificationEventType.BROKER_REJECTED,
        QualificationEventType.BROKER_EXPIRED,
    }
    operator_events = {
        QualificationEventType.OPERATOR_APPROVED,
        QualificationEventType.OPERATOR_REJECTED,
    }
    for step in steps:
        if step.actor_type is ActorType.BROKER and step.event_type in operator_events:
            _raise(
                ScenarioValidationReason.BROKER_OBSERVATION_DECLARES_OPERATOR_APPROVAL,
                "Broker observations cannot declare operator approval decisions.",
            )
        if step.actor_type is ActorType.OPERATOR and step.event_type in (
            broker_truth_events
        ):
            _raise(
                ScenarioValidationReason.OPERATOR_COMMAND_DECLARES_BROKER_TRUTH,
                "Operator commands cannot declare broker truth.",
            )


def _validate_terminal_expectation(spec: QualificationScenarioSpec) -> None:
    expected_state = spec.terminal_expectation.workflow_state
    expected_result = spec.terminal_expectation.qualification_result
    if expected_state is QualificationState.QUALIFIED and expected_result is not (
        QualificationResult.PASSED
    ):
        _raise(
            ScenarioValidationReason.INCOMPATIBLE_TERMINAL_EXPECTATION,
            "Qualified terminal state requires PASSED result.",
        )
    if expected_state is QualificationState.DISQUALIFIED and expected_result is not (
        QualificationResult.FAILED
    ):
        _raise(
            ScenarioValidationReason.INCOMPATIBLE_TERMINAL_EXPECTATION,
            "Disqualified terminal state requires FAILED result.",
        )


def _validate_no_secret_fixtures(spec: QualificationScenarioSpec) -> None:
    fields = (
        spec.scenario_id,
        spec.title,
        spec.description,
        spec.order_intent_summary,
        *spec.preconditions,
        *spec.required_evidence_expectations,
        *spec.prohibited_behavior,
        *spec.tags,
    )
    step_fields: list[str] = []
    for step in spec.steps:
        step_fields.extend(
            (
                step.step_id,
                step.command_id,
                step.idempotency_key,
                step.object_reference or "",
                *step.payload_fingerprint,
            )
        )
        if step.observation is not None:
            step_fields.extend(
                (
                    step.observation.observation_type,
                    step.observation.object_reference,
                    *step.observation.facts,
                )
            )
    rendered = " ".join((*fields, *step_fields)).upper()
    if any(marker in rendered for marker in _SECRET_MARKERS):
        _raise(
            ScenarioValidationReason.SECRET_FIXTURE,
            "Scenario fixtures cannot contain credential-like markers.",
        )


def _raise(reason: ScenarioValidationReason, message: str) -> None:
    raise ScenarioValidationError(reason_code=reason, safe_message=message)
