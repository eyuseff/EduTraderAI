"""Deterministic side-effect-free Paper dry-run executor."""

from __future__ import annotations

from dataclasses import replace

from volcanoes.application.execution.contracts import PaperExecutionCommand
from volcanoes.application.execution.dry_run.contracts import (
    PaperDryRunFailure,
    PaperDryRunReceipt,
    PaperDryRunRequest,
    PaperDryRunResult,
    PaperDryRunStep,
)
from volcanoes.application.execution.dry_run.enums import (
    PaperDryRunFailureReason,
    PaperDryRunOutcomeKind,
    PaperDryRunStepKind,
)
from volcanoes.application.execution.errors import PaperExecutionInvariantError
from volcanoes.application.execution.fingerprints import command_payload_fingerprint
from volcanoes.application.execution.lifecycle import (
    PaperExecutionLifecycle,
    PaperExecutionLifecycleInput,
    PaperExecutionLifecycleInputType as LifecycleInput,
    PaperExecutionLifecycleState,
    PaperExecutionTransitionContext,
    PaperExecutionTransitionDecision,
    apply_transition,
    transition,
)
from volcanoes.application.execution.eligibility import (
    PaperExecutionEligibilityDecision,
    PaperExecutionEligibilityResult,
    PaperExecutionEligibilityService,
)


class PaperDryRunExecutor:
    """Compose eligibility and lifecycle cores without external effects."""

    def __init__(
        self,
        eligibility_service: PaperExecutionEligibilityService | None = None,
    ) -> None:
        self._eligibility_service = (
            eligibility_service or PaperExecutionEligibilityService()
        )

    def execute(self, request: PaperDryRunRequest) -> PaperDryRunResult:
        """Return deterministic dry-run orchestration facts."""

        if not isinstance(request, PaperDryRunRequest):
            raise PaperExecutionInvariantError(
                "INVALID_DRY_RUN_REQUEST",
                "Dry-run executor requires a PaperDryRunRequest.",
            )
        replay = _replay_or_conflict_result(request)
        if replay is not None:
            return replay
        steps = [
            _step(
                1,
                PaperDryRunStepKind.REQUEST_VALIDATED,
                "REQUEST_VALIDATED",
                request.initial_lifecycle.revision,
                request.initial_lifecycle.revision,
            )
        ]
        if (
            request.lifecycle_context.expected_revision
            != request.initial_lifecycle.revision
        ):
            steps.append(
                _step(
                    len(steps) + 1,
                    PaperDryRunStepKind.FAILED_SAFE,
                    "STALE_EXECUTION_REVISION",
                    request.initial_lifecycle.revision,
                    request.initial_lifecycle.revision,
                )
            )
            return _result(
                request,
                PaperDryRunOutcomeKind.WOULD_REJECT,
                None,
                request.initial_lifecycle,
                tuple(steps),
                PaperDryRunFailureReason.STALE_REVISION,
                "STALE_EXECUTION_REVISION",
            )
        if request.initial_lifecycle.state in {
            PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
            PaperExecutionLifecycleState.RECONCILIATION_REQUIRED,
        }:
            steps.append(
                _step(
                    len(steps) + 1,
                    PaperDryRunStepKind.WOULD_REQUIRE_RECONCILIATION,
                    "INITIAL_LIFECYCLE_RECONCILIATION_REQUIRED",
                    request.initial_lifecycle.revision,
                    request.initial_lifecycle.revision,
                )
            )
            return _result(
                request,
                PaperDryRunOutcomeKind.WOULD_REQUIRE_RECONCILIATION,
                None,
                request.initial_lifecycle,
                tuple(steps),
                PaperDryRunFailureReason.RECONCILIATION_REQUIRED,
                "RECONCILIATION_REQUIRED",
                reconciliation_required=True,
            )

        eligibility = self._eligibility_service.evaluate(
            request.command,
            request.eligibility_policy,
            evaluated_at=request.evaluated_at,
        )
        steps.append(
            _step(
                len(steps) + 1,
                PaperDryRunStepKind.ELIGIBILITY_EVALUATED,
                eligibility.decision.value,
                request.initial_lifecycle.revision,
                request.initial_lifecycle.revision,
            )
        )
        if eligibility.decision is PaperExecutionEligibilityDecision.INELIGIBLE:
            return _ineligible_result(request, eligibility, tuple(steps))
        if eligibility.decision is PaperExecutionEligibilityDecision.INDETERMINATE:
            return _indeterminate_result(request, eligibility, tuple(steps))
        return _eligible_result(request, eligibility, tuple(steps))


def _eligible_result(
    request: PaperDryRunRequest,
    eligibility: PaperExecutionEligibilityResult,
    initial_steps: tuple[PaperDryRunStep, ...],
) -> PaperDryRunResult:
    current = request.initial_lifecycle
    steps = list(initial_steps)
    transition_ids: list[str] = []
    path = (
        (
            LifecycleInput.RECORD_ELIGIBILITY,
            PaperDryRunStepKind.LIFECYCLE_ELIGIBILITY_RECORDED,
            "ELIGIBILITY_RECORDED",
        ),
        (
            LifecycleInput.RECORD_APPROVAL,
            PaperDryRunStepKind.APPROVAL_RECORDED,
            "APPROVAL_RECORDED",
        ),
        (
            LifecycleInput.RECORD_IDEMPOTENCY_RESERVATION,
            PaperDryRunStepKind.IDEMPOTENCY_RESERVATION_SIMULATED,
            "IDEMPOTENCY_RESERVATION_SIMULATED",
        ),
        (
            LifecycleInput.PREPARE_DISPATCH,
            PaperDryRunStepKind.READY_FOR_DISPATCH_REACHED,
            "READY_FOR_DISPATCH_REACHED",
        ),
    )
    for input_type, step_kind, reason in path:
        facts = _context_for(request.lifecycle_context, current, "ELIGIBLE")
        decision = transition(
            current, _lifecycle_input(request.command, input_type), facts
        )
        if not decision.accepted:
            return _lifecycle_rejection(
                request,
                eligibility,
                current,
                tuple(steps),
                decision,
            )
        steps.append(_transition_step(len(steps) + 1, step_kind, reason, decision))
        transition_ids.append(decision.transition_id or "")
        current = apply_transition(current, decision)
    steps.append(
        _step(
            len(steps) + 1,
            PaperDryRunStepKind.WOULD_DISPATCH,
            "WOULD_DISPATCH",
            current.revision,
            current.revision,
        )
    )
    return _result(
        request,
        PaperDryRunOutcomeKind.WOULD_DISPATCH,
        eligibility,
        current,
        tuple(steps),
        None,
        "WOULD_DISPATCH",
        transition_ids=tuple(transition_ids),
    )


def _ineligible_result(
    request: PaperDryRunRequest,
    eligibility: PaperExecutionEligibilityResult,
    initial_steps: tuple[PaperDryRunStep, ...],
) -> PaperDryRunResult:
    current, steps, transition_ids = _terminal_eligibility_record(
        request,
        eligibility,
        initial_steps,
        LifecycleInput.RECORD_INELIGIBLE,
        "INELIGIBLE",
        PaperDryRunStepKind.ELIGIBILITY_REJECTED,
    )
    return _result(
        request,
        PaperDryRunOutcomeKind.WOULD_REJECT,
        eligibility,
        current,
        steps,
        PaperDryRunFailureReason.COMMAND_INELIGIBLE,
        "COMMAND_INELIGIBLE",
        transition_ids=transition_ids,
    )


def _indeterminate_result(
    request: PaperDryRunRequest,
    eligibility: PaperExecutionEligibilityResult,
    initial_steps: tuple[PaperDryRunStep, ...],
) -> PaperDryRunResult:
    current, steps, transition_ids = _terminal_eligibility_record(
        request,
        eligibility,
        initial_steps,
        LifecycleInput.RECORD_INDETERMINATE,
        "INDETERMINATE",
        PaperDryRunStepKind.ELIGIBILITY_INDETERMINATE,
    )
    return _result(
        request,
        PaperDryRunOutcomeKind.WOULD_REQUIRE_EXTERNAL_EVIDENCE,
        eligibility,
        current,
        steps,
        PaperDryRunFailureReason.EXTERNAL_EVIDENCE_REQUIRED,
        "EXTERNAL_EVIDENCE_REQUIRED",
        transition_ids=transition_ids,
        external_evidence_required=True,
    )


def _terminal_eligibility_record(
    request: PaperDryRunRequest,
    eligibility: PaperExecutionEligibilityResult,
    initial_steps: tuple[PaperDryRunStep, ...],
    input_type: LifecycleInput,
    eligibility_decision: str,
    step_kind: PaperDryRunStepKind,
) -> tuple[PaperExecutionLifecycle, tuple[PaperDryRunStep, ...], tuple[str, ...]]:
    current = request.initial_lifecycle
    steps = list(initial_steps)
    transition_ids: list[str] = []
    if current.state is PaperExecutionLifecycleState.ELIGIBILITY_EVALUATED:
        decision = transition(
            current,
            _lifecycle_input(request.command, input_type),
            _context_for(request.lifecycle_context, current, eligibility_decision),
        )
        if decision.accepted:
            steps.append(
                _transition_step(
                    len(steps) + 1,
                    step_kind,
                    eligibility_decision,
                    decision,
                )
            )
            transition_ids.append(decision.transition_id or "")
            current = apply_transition(current, decision)
            return current, tuple(steps), tuple(transition_ids)
    steps.append(
        _step(
            len(steps) + 1,
            step_kind,
            eligibility_decision,
            current.revision,
            current.revision,
        )
    )
    return current, tuple(steps), tuple(transition_ids)


def _lifecycle_rejection(
    request: PaperDryRunRequest,
    eligibility: PaperExecutionEligibilityResult,
    current: PaperExecutionLifecycle,
    steps: tuple[PaperDryRunStep, ...],
    decision: PaperExecutionTransitionDecision,
) -> PaperDryRunResult:
    reason = _failure_reason(decision.reason_code)
    outcome = (
        PaperDryRunOutcomeKind.WOULD_REQUIRE_EXTERNAL_EVIDENCE
        if reason is PaperDryRunFailureReason.EXTERNAL_EVIDENCE_REQUIRED
        else PaperDryRunOutcomeKind.WOULD_REJECT
    )
    next_steps = (
        *steps,
        _transition_step(
            len(steps) + 1,
            PaperDryRunStepKind.FAILED_SAFE,
            decision.reason_code,
            decision,
        ),
    )
    return _result(
        request,
        outcome,
        eligibility,
        current,
        next_steps,
        reason,
        decision.reason_code,
        external_evidence_required=reason
        is PaperDryRunFailureReason.EXTERNAL_EVIDENCE_REQUIRED,
        reconciliation_required=decision.reconciliation_required,
    )


def _replay_or_conflict_result(
    request: PaperDryRunRequest,
) -> PaperDryRunResult | None:
    prior = request.prior_result
    if prior is None:
        return None
    if prior.command_id != request.command.command_id:
        return None
    if prior.request_fingerprint == request.request_fingerprint:
        steps = (
            _step(
                1,
                PaperDryRunStepKind.REPLAYED,
                "NO_ACTION_REPLAY",
                request.initial_lifecycle.revision,
                request.initial_lifecycle.revision,
            ),
        )
        return _result(
            request,
            PaperDryRunOutcomeKind.NO_ACTION_REPLAY,
            prior.eligibility_result,
            request.initial_lifecycle,
            steps,
            None,
            "NO_ACTION_REPLAY",
            replayed=True,
        )
    steps = (
        _step(
            1,
            PaperDryRunStepKind.FAILED_SAFE,
            "COMMAND_CONFLICT",
            request.initial_lifecycle.revision,
            request.initial_lifecycle.revision,
        ),
    )
    return _result(
        request,
        PaperDryRunOutcomeKind.WOULD_REJECT,
        None,
        request.initial_lifecycle,
        steps,
        PaperDryRunFailureReason.COMMAND_CONFLICT,
        "COMMAND_CONFLICT",
    )


def _result(
    request: PaperDryRunRequest,
    outcome: PaperDryRunOutcomeKind,
    eligibility: PaperExecutionEligibilityResult | None,
    final_lifecycle: PaperExecutionLifecycle,
    steps: tuple[PaperDryRunStep, ...],
    failure_reason: PaperDryRunFailureReason | None,
    message_code: str,
    *,
    transition_ids: tuple[str, ...] = (),
    replayed: bool = False,
    external_evidence_required: bool = False,
    reconciliation_required: bool = False,
) -> PaperDryRunResult:
    receipt = None
    failure = None
    if failure_reason is None:
        receipt = PaperDryRunReceipt(
            request_fingerprint=request.request_fingerprint,
            command_id=request.command.command_id,
            aggregate_id=request.command.aggregate_id,
            correlation_id=request.command.correlation_id,
            outcome_kind=outcome,
            simulated_at=request.evaluated_at,
            final_lifecycle_state=final_lifecycle.state.value,
            final_revision=final_lifecycle.revision,
            safe_message_code=message_code,
            would_dispatch=outcome is PaperDryRunOutcomeKind.WOULD_DISPATCH,
            external_evidence_required=external_evidence_required,
            reconciliation_required=reconciliation_required,
        )
    else:
        failure = PaperDryRunFailure(
            request_fingerprint=request.request_fingerprint,
            reason=failure_reason,
            safe_message_code=message_code,
            command_id=request.command.command_id,
            aggregate_id=request.command.aggregate_id,
            correlation_id=request.command.correlation_id,
            lifecycle_transition_id=transition_ids[-1] if transition_ids else None,
        )
    return PaperDryRunResult(
        outcome_kind=outcome,
        request_fingerprint=request.request_fingerprint,
        command_id=request.command.command_id,
        aggregate_id=request.command.aggregate_id,
        correlation_id=request.command.correlation_id,
        eligibility_result=eligibility,
        initial_lifecycle=request.initial_lifecycle,
        final_lifecycle=final_lifecycle,
        steps=steps,
        receipt=receipt,
        failure=failure,
        lifecycle_transition_ids=transition_ids,
        initial_revision=request.initial_lifecycle.revision,
        final_revision=final_lifecycle.revision,
        replayed=replayed,
        external_evidence_required=external_evidence_required,
        reconciliation_required=reconciliation_required,
    )


def _context_for(
    base: PaperExecutionTransitionContext,
    current: PaperExecutionLifecycle,
    eligibility_decision: str,
) -> PaperExecutionTransitionContext:
    return replace(
        base,
        expected_revision=current.revision,
        eligibility_decision=eligibility_decision,
    )


def _lifecycle_input(
    command: PaperExecutionCommand,
    input_type: LifecycleInput,
) -> PaperExecutionLifecycleInput:
    return PaperExecutionLifecycleInput(
        input_type=input_type,
        command_id=command.command_id,
        aggregate_id=command.aggregate_id,
        correlation_id=command.correlation_id,
        idempotency_key=command.idempotency_key,
        command_payload_fingerprint=command.payload_fingerprint,
        idempotency_payload_fingerprint=command_payload_fingerprint(
            ("idempotency", command.idempotency_key, command.payload_fingerprint)
        ),
    )


def _transition_step(
    sequence: int,
    kind: PaperDryRunStepKind,
    reason_code: str,
    decision: PaperExecutionTransitionDecision,
) -> PaperDryRunStep:
    return PaperDryRunStep(
        sequence=sequence,
        kind=kind,
        reason_code=reason_code,
        lifecycle_transition_id=decision.transition_id,
        previous_revision=decision.previous_revision,
        next_revision=decision.next_revision,
        side_effect_intent_kinds=tuple(
            intent.kind for intent in decision.side_effect_intents
        ),
        evidence_intent_kinds=tuple(
            intent.kind for intent in decision.evidence_intents
        ),
    )


def _step(
    sequence: int,
    kind: PaperDryRunStepKind,
    reason_code: str,
    previous_revision,
    next_revision,
) -> PaperDryRunStep:
    return PaperDryRunStep(
        sequence=sequence,
        kind=kind,
        reason_code=reason_code,
        previous_revision=previous_revision,
        next_revision=next_revision,
    )


def _failure_reason(reason_code: str) -> PaperDryRunFailureReason:
    if reason_code == "STALE_EXECUTION_REVISION":
        return PaperDryRunFailureReason.STALE_REVISION
    if reason_code == "COMMAND_CONFLICT":
        return PaperDryRunFailureReason.COMMAND_CONFLICT
    if reason_code == "IDEMPOTENCY_CONFLICT":
        return PaperDryRunFailureReason.IDEMPOTENCY_CONFLICT
    if reason_code in {
        "IDEMPOTENCY_NOT_CONFIRMED",
        "EXTERNAL_PREREQUISITES_NOT_SATISFIED",
        "EMERGENCY_STOP_ACTIVE",
    }:
        return PaperDryRunFailureReason.EXTERNAL_EVIDENCE_REQUIRED
    if reason_code in {
        "RECONCILIATION_REQUIRED",
        "OUTCOME_UNKNOWN_REQUIRES_RECONCILIATION",
    }:
        return PaperDryRunFailureReason.RECONCILIATION_REQUIRED
    return PaperDryRunFailureReason.LIFECYCLE_TRANSITION_REJECTED
