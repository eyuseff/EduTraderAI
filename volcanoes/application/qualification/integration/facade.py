"""Non-executing Paper qualification integration facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from volcanoes.application.qualification.contracts import (
    CommandId,
    CorrelationId,
    IdempotencyKey,
    QualificationResult,
    QualificationRunId,
    QualificationState,
    StateRevision,
)
from volcanoes.application.qualification.integration.contracts import (
    PaperIntegrationEnvironment,
    PaperRuntimeRequest,
    RuntimeActionRequest,
    require_paper_environment,
)
from volcanoes.application.qualification.integration.errors import (
    FacadeIdentityContinuityError,
    FacadeResultValidationError,
    FacadeServiceInvocationError,
    QualificationIntegrationError,
    PaperQualificationFacadeError,
)
from volcanoes.application.qualification.integration.translation import (
    execution_plan_to_runtime_action_request,
    runtime_request_to_qualification_command,
)
from volcanoes.application.qualification.service import (
    PaperQualificationService,
    QualificationApplicationError,
    QualificationApplicationResult,
)


@dataclass(frozen=True, slots=True)
class PaperQualificationFacadeResult:
    """Safe facade result; returned runtime actions are descriptive only."""

    qualification_run_id: QualificationRunId
    application_result: QualificationApplicationResult
    runtime_action: RuntimeActionRequest
    command_id: CommandId
    correlation_id: CorrelationId
    idempotency_key: IdempotencyKey
    transition_id: str
    previous_revision: StateRevision
    next_revision: StateRevision
    qualification_state: QualificationState | None
    qualification_result: QualificationResult | None
    replayed: bool
    safe_operator_message: str
    action_executed: Literal[False] = False


class PaperQualificationFacade:
    """Orchestrate request translation, service invocation, and action description."""

    def __init__(self, service: PaperQualificationService) -> None:
        if not isinstance(service, PaperQualificationService):
            raise TypeError("service must be a PaperQualificationService instance.")
        self._service = service

    def handle(self, request: PaperRuntimeRequest) -> PaperQualificationFacadeResult:
        """Handle one Paper runtime request without executing any runtime action."""

        if not isinstance(request, PaperRuntimeRequest):
            raise PaperQualificationFacadeError(
                reason_code="UNSUPPORTED_FACADE_REQUEST",
                safe_message="Paper qualification facade request is unsupported.",
            )
        require_paper_environment(request.environment)
        command = runtime_request_to_qualification_command(request)
        try:
            application_result = self._service.execute(command)
        except QualificationApplicationError as error:
            raise FacadeServiceInvocationError(
                reason_code=error.reason_code,
                safe_message=error.safe_message,
            ) from error

        self._validate_application_result(request, application_result)
        execution_plan = application_result.execution_plan
        if execution_plan is None:
            raise FacadeResultValidationError(
                reason_code="MISSING_EXECUTION_PLAN",
                safe_message="Qualification service did not return an execution plan.",
            )
        try:
            runtime_action = execution_plan_to_runtime_action_request(
                execution_plan,
                environment=PaperIntegrationEnvironment.PAPER,
            )
        except QualificationIntegrationError as error:
            raise FacadeResultValidationError(
                reason_code="ACTION_TRANSLATION_FAILED",
                safe_message=error.safe_message,
            ) from error
        self._validate_runtime_action(request, runtime_action)
        decision = application_result.transition_decision
        if decision is None:
            raise FacadeResultValidationError(
                reason_code="MISSING_TRANSITION_DECISION",
                safe_message="Qualification service did not return a transition decision.",
            )
        return PaperQualificationFacadeResult(
            qualification_run_id=application_result.qualification_run_id,
            application_result=application_result,
            runtime_action=runtime_action,
            command_id=runtime_action.command_id,
            correlation_id=runtime_action.correlation_id,
            idempotency_key=runtime_action.idempotency_key,
            transition_id=runtime_action.source_transition_id,
            previous_revision=decision.previous_revision,
            next_revision=decision.next_revision,
            qualification_state=(
                application_result.resulting_run.state
                if application_result.resulting_run is not None
                else None
            ),
            qualification_result=(
                application_result.resulting_run.result
                if application_result.resulting_run is not None
                else None
            ),
            replayed=application_result.replayed,
            safe_operator_message=application_result.safe_message,
            action_executed=False,
        )

    @staticmethod
    def _validate_application_result(
        request: PaperRuntimeRequest,
        result: QualificationApplicationResult,
    ) -> None:
        if result.qualification_run_id != request.qualification_run_id:
            raise FacadeIdentityContinuityError(
                reason_code="RUN_ID_MISMATCH",
                safe_message="Qualification result run identity did not match request.",
            )
        plan = result.execution_plan
        if plan is None:
            return
        mismatches: list[str] = []
        if plan.qualification_run_id != request.qualification_run_id:
            mismatches.append("qualification_run_id")
        if plan.command_id != request.command_id:
            mismatches.append("command_id")
        if plan.correlation_id != request.correlation_id:
            mismatches.append("correlation_id")
        if plan.idempotency_key != request.idempotency_key:
            mismatches.append("idempotency_key")
        if plan.previous_revision != request.expected_revision:
            mismatches.append("expected_revision")
        if mismatches:
            raise FacadeIdentityContinuityError(
                reason_code="IDENTITY_CONTINUITY_FAILED",
                safe_message="Qualification result identity did not match request.",
                context=tuple(("field", field) for field in mismatches),
            )

    @staticmethod
    def _validate_runtime_action(
        request: PaperRuntimeRequest,
        action: RuntimeActionRequest,
    ) -> None:
        require_paper_environment(action.environment)
        mismatches: list[str] = []
        if action.qualification_run_id != request.qualification_run_id:
            mismatches.append("qualification_run_id")
        if action.command_id != request.command_id:
            mismatches.append("command_id")
        if action.correlation_id != request.correlation_id:
            mismatches.append("correlation_id")
        if action.idempotency_key != request.idempotency_key:
            mismatches.append("idempotency_key")
        if action.source_revision != request.expected_revision:
            mismatches.append("source_revision")
        if mismatches:
            raise FacadeIdentityContinuityError(
                reason_code="ACTION_IDENTITY_CONTINUITY_FAILED",
                safe_message="Runtime action identity did not match request.",
                context=tuple(("field", field) for field in mismatches),
            )
