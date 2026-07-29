"""Immutable scenario contracts for Paper qualification harnesses."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import NewType

from volcanoes.application.qualification.contracts import (
    ActorType,
    CommandId,
    CorrelationId,
    Guard,
    IdempotencyKey,
    PaperQualificationRun,
    QualificationEventType,
    QualificationResult,
    QualificationRunId,
    QualificationScenarioId,
    QualificationState,
    SideEffectIntentType,
    StateRevision,
)
from volcanoes.application.qualification.ports import EvidenceRecordReference
from volcanoes.application.qualification.service import (
    ExecutionPlanKind,
    QualificationApplicationResult,
)

QualificationScenarioVersion = NewType("QualificationScenarioVersion", str)
ScenarioStepId = NewType("ScenarioStepId", str)


class ScenarioCategory(StrEnum):
    """Business category for an approved qualification scenario."""

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    RECOVERY = "RECOVERY"
    SAFETY = "SAFETY"


class ScenarioStepKind(StrEnum):
    """Typed scenario step source without executable callbacks."""

    APPLICATION_COMMAND = "APPLICATION_COMMAND"
    OPERATOR_COMMAND = "OPERATOR_COMMAND"
    BROKER_OBSERVATION = "BROKER_OBSERVATION"
    SYSTEM_OBSERVATION = "SYSTEM_OBSERVATION"
    EXPECTED_REJECTION = "EXPECTED_REJECTION"


class ScenarioHarnessStatus(StrEnum):
    """Harness outcome, distinct from qualification result."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    INCONCLUSIVE = "INCONCLUSIVE"
    INVALID_SPECIFICATION = "INVALID_SPECIFICATION"
    APPLICATION_ERROR = "APPLICATION_ERROR"
    EXPECTED_REJECTION_CONFIRMED = "EXPECTED_REJECTION_CONFIRMED"


class ScenarioValidationReason(StrEnum):
    """Stable safe scenario-validation reason codes."""

    EMPTY_SCENARIO_ID = "EMPTY_SCENARIO_ID"
    UNSUPPORTED_VERSION = "UNSUPPORTED_VERSION"
    DUPLICATE_STEP_ID = "DUPLICATE_STEP_ID"
    NON_SEQUENTIAL_STEPS = "NON_SEQUENTIAL_STEPS"
    MISSING_INITIAL_CREATION_STEP = "MISSING_INITIAL_CREATION_STEP"
    LIVE_ENVIRONMENT = "LIVE_ENVIRONMENT"
    MISSING_EXPECTED_TRANSITION_ID = "MISSING_EXPECTED_TRANSITION_ID"
    MISSING_EXPECTED_SOURCE_STATE = "MISSING_EXPECTED_SOURCE_STATE"
    INCOMPATIBLE_TERMINAL_EXPECTATION = "INCOMPATIBLE_TERMINAL_EXPECTATION"
    CONSEQUENTIAL_STEP_WITHOUT_PLAN = "CONSEQUENTIAL_STEP_WITHOUT_PLAN"
    BROKER_OBSERVATION_DECLARES_OPERATOR_APPROVAL = (
        "BROKER_OBSERVATION_DECLARES_OPERATOR_APPROVAL"
    )
    OPERATOR_COMMAND_DECLARES_BROKER_TRUTH = "OPERATOR_COMMAND_DECLARES_BROKER_TRUTH"
    DUPLICATE_COMMAND_IDENTITY = "DUPLICATE_COMMAND_IDENTITY"
    INCONSISTENT_EXPECTED_REVISION = "INCONSISTENT_EXPECTED_REVISION"
    UNRECOGNIZED_TRANSITION_ID = "UNRECOGNIZED_TRANSITION_ID"
    STEP_AFTER_TERMINAL_STATE = "STEP_AFTER_TERMINAL_STATE"
    SECRET_FIXTURE = "SECRET_FIXTURE"
    DUPLICATE_SCENARIO_ID_VERSION = "DUPLICATE_SCENARIO_ID_VERSION"


@dataclass(frozen=True, slots=True)
class ScenarioValidationError(Exception):
    """Safe typed validation error for scenario specifications."""

    reason_code: ScenarioValidationReason
    safe_message: str

    def __post_init__(self) -> None:
        if not isinstance(self.reason_code, ScenarioValidationReason):
            raise TypeError("reason_code must be a ScenarioValidationReason.")
        if not self.safe_message.strip():
            raise ValueError("safe_message cannot be empty.")
        Exception.__init__(self, self.safe_message)

    def __str__(self) -> str:
        return self.safe_message


@dataclass(frozen=True, slots=True)
class ScenarioExecutionPolicy:
    """Deterministic harness policy for one scenario run."""

    fail_fast: bool = True
    continue_after_expected_rejection: bool = False


@dataclass(frozen=True, slots=True)
class ScenarioTerminalExpectation:
    """Expected terminal snapshot for a scenario specification."""

    workflow_state: QualificationState
    qualification_result: QualificationResult


@dataclass(frozen=True, slots=True)
class NormalizedBrokerObservation:
    """Broker-neutral observation fixture supplied to the service as facts."""

    observation_type: str
    object_reference: str
    facts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.observation_type.strip():
            raise ValueError("observation_type cannot be empty.")
        if not self.object_reference.strip():
            raise ValueError("object_reference cannot be empty.")
        object.__setattr__(self, "facts", tuple(str(fact) for fact in self.facts))


@dataclass(frozen=True, slots=True)
class QualificationScenarioExpectation:
    """Expected application-service response for one step."""

    accepted: bool
    transition_id: str
    destination_state: QualificationState
    qualification_result: QualificationResult
    revision: StateRevision
    execution_plan_kinds: tuple[ExecutionPlanKind, ...]
    side_effect_intents: tuple[SideEffectIntentType, ...] = ()
    reconciliation_required: bool = False
    evidence_recorded: bool = True
    reason_code: str | None = None
    safe_message_contains: str | None = None
    replayed: bool = False

    def __post_init__(self) -> None:
        if not self.transition_id.strip():
            raise ValueError("transition_id cannot be empty.")
        if self.revision < 0:
            raise ValueError("revision cannot be negative.")
        object.__setattr__(
            self, "execution_plan_kinds", tuple(self.execution_plan_kinds)
        )
        object.__setattr__(self, "side_effect_intents", tuple(self.side_effect_intents))


@dataclass(frozen=True, slots=True)
class QualificationScenarioStep:
    """One declarative scenario step; expectations are assertions only."""

    step_id: ScenarioStepId
    sequence: int
    step_kind: ScenarioStepKind
    event_type: QualificationEventType
    expected_source_state: QualificationState
    expected_transition_id: str
    expected_revision: StateRevision
    actor_type: ActorType
    command_id: CommandId
    idempotency_key: IdempotencyKey
    guards: frozenset[Guard]
    expectation: QualificationScenarioExpectation
    payload_fingerprint: tuple[str, ...] = ()
    object_reference: str | None = None
    observation: NormalizedBrokerObservation | None = None
    replay_verification: bool = False
    expected_rejection: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.step_kind, ScenarioStepKind):
            raise TypeError("step_kind must be a ScenarioStepKind.")
        if self.sequence < 1:
            raise ValueError("sequence must be positive.")
        for name in ("step_id", "command_id", "idempotency_key"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} cannot be empty.")
        if not self.expected_transition_id.strip():
            raise ValueError("expected_transition_id cannot be empty.")
        object.__setattr__(self, "guards", frozenset(self.guards))
        object.__setattr__(
            self,
            "payload_fingerprint",
            tuple(str(item) for item in self.payload_fingerprint),
        )


@dataclass(frozen=True, slots=True)
class QualificationScenarioSpec:
    """Immutable declarative scenario specification."""

    scenario_id: QualificationScenarioId
    scenario_version: QualificationScenarioVersion
    title: str
    description: str
    environment: str
    order_intent_summary: str
    preconditions: tuple[str, ...]
    steps: tuple[QualificationScenarioStep, ...]
    terminal_expectation: ScenarioTerminalExpectation
    required_evidence_expectations: tuple[str, ...]
    required_side_effect_expectations: tuple[SideEffectIntentType, ...]
    prohibited_behavior: tuple[str, ...]
    tags: tuple[str, ...]
    mandatory: bool
    category: ScenarioCategory
    execution_policy: ScenarioExecutionPolicy = ScenarioExecutionPolicy()

    def __post_init__(self) -> None:
        for name in (
            "scenario_version",
            "title",
            "description",
            "environment",
            "order_intent_summary",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} cannot be empty.")
        object.__setattr__(self, "preconditions", tuple(self.preconditions))
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(
            self,
            "required_evidence_expectations",
            tuple(self.required_evidence_expectations),
        )
        object.__setattr__(
            self,
            "required_side_effect_expectations",
            tuple(self.required_side_effect_expectations),
        )
        object.__setattr__(self, "prohibited_behavior", tuple(self.prohibited_behavior))
        object.__setattr__(self, "tags", tuple(self.tags))


@dataclass(frozen=True, slots=True)
class ScenarioExecutionContext:
    """Deterministic context injected into scenario execution."""

    qualification_run_id: QualificationRunId
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class QualificationScenarioStepResult:
    """Immutable result for one executed scenario step."""

    step_id: ScenarioStepId
    sequence: int
    harness_status: ScenarioHarnessStatus
    application_result: QualificationApplicationResult | None
    transition_id: str | None
    source_state: QualificationState | None
    destination_state: QualificationState | None
    revision: StateRevision | None
    qualification_result: QualificationResult | None
    execution_plan_kinds: tuple[ExecutionPlanKind, ...] = ()
    side_effect_intents: tuple[SideEffectIntentType, ...] = ()
    evidence_records: tuple[EvidenceRecordReference, ...] = ()
    replayed: bool = False
    reconciliation_required: bool = False
    assertion_failures: tuple[str, ...] = ()
    safe_summary: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "execution_plan_kinds", tuple(self.execution_plan_kinds)
        )
        object.__setattr__(self, "side_effect_intents", tuple(self.side_effect_intents))
        object.__setattr__(self, "evidence_records", tuple(self.evidence_records))
        object.__setattr__(self, "assertion_failures", tuple(self.assertion_failures))


@dataclass(frozen=True, slots=True)
class QualificationScenarioResult:
    """Deterministic safe report produced by the scenario harness."""

    scenario_id: QualificationScenarioId
    scenario_version: QualificationScenarioVersion
    title: str
    harness_status: ScenarioHarnessStatus
    run_id: QualificationRunId
    total_steps: int
    completed_steps: int
    failed_step_id: ScenarioStepId | None
    terminal_run: PaperQualificationRun | None
    terminal_workflow_state: QualificationState | None
    terminal_qualification_result: QualificationResult | None
    step_results: tuple[QualificationScenarioStepResult, ...]
    transition_trace: tuple[str, ...]
    revisions_observed: tuple[StateRevision, ...]
    execution_plans_observed: tuple[tuple[ExecutionPlanKind, ...], ...]
    side_effect_intents_observed: tuple[SideEffectIntentType, ...]
    evidence_records_observed: tuple[EvidenceRecordReference, ...]
    replay_observations: tuple[ScenarioStepId, ...]
    reconciliation_required: bool
    assertion_failures: tuple[str, ...]
    safe_summary: str
    external_actions_executed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "step_results", tuple(self.step_results))
        object.__setattr__(self, "transition_trace", tuple(self.transition_trace))
        object.__setattr__(self, "revisions_observed", tuple(self.revisions_observed))
        object.__setattr__(
            self,
            "execution_plans_observed",
            tuple(tuple(plan) for plan in self.execution_plans_observed),
        )
        object.__setattr__(
            self,
            "side_effect_intents_observed",
            tuple(self.side_effect_intents_observed),
        )
        object.__setattr__(
            self,
            "evidence_records_observed",
            tuple(self.evidence_records_observed),
        )
        object.__setattr__(self, "replay_observations", tuple(self.replay_observations))
        object.__setattr__(self, "assertion_failures", tuple(self.assertion_failures))
