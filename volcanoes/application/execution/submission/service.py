"""Durably claimed, broker-neutral controlled Paper submission service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Protocol

from volcanoes.application.execution.persistence import (
    DispatchClaimStatus,
    DispatchEffectPhase,
    DispatchResolutionStatus,
    ExecutionBrokerReferenceRecord,
    ExecutionBrokerReferenceStatus,
    ExecutionDispatchAuthorizationRecord,
    ExecutionDispatchResolutionRecord,
    ExecutionPersistenceResultStatus,
    ExecutionFailureRecord,
    ExecutionReceiptRecord,
    ExecutionTransitionRecord,
    ExecutionReplayKind,
)
from volcanoes.application.execution.persistence.contracts import (
    DispatchClaimResult,
    DispatchOutcomeWriteSet,
    ExecutionDispatchClaim,
    ExecutionDispatchClaimAttempt,
)
from volcanoes.application.execution.persistence.unit_of_work import ExecutionUnitOfWork
from volcanoes.application.execution.contracts import (
    PaperExecutionFailure,
    PaperExecutionReceipt,
)
from volcanoes.application.execution.enums import (
    PaperExecutionFailureKind,
    PaperExecutionFailureSeverity,
    PaperExecutionOperation,
    PaperExecutionReceiptKind,
    PaperExecutionStatus,
)
from volcanoes.application.execution.lifecycle import (
    PaperExecutionLifecycleEvidenceIntentKind,
    PaperExecutionLifecycleInputType,
    PaperExecutionLifecycleSideEffectIntentKind,
    PaperExecutionLifecycleState,
    is_aggregate_terminal,
    is_command_terminal,
)
from volcanoes.application.execution.identities import (
    PaperBrokerOrderReference,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
)
from volcanoes.application.execution.submission.contracts import (
    ControlledPaperOrder,
    ControlledSubmissionRequest,
    ControlledSubmissionResult,
    ControlledSubmissionStatus,
    DispatchFailurePhase,
    PaperDispatchFailure,
    PaperDispatchObservation,
)
from volcanoes.application.execution.submission.ports import (
    OneShotPaperDispatchBoundary,
)


class _DispatchAuthorityProvider(Protocol):
    def unit_of_work(self) -> ExecutionUnitOfWork: ...

    def acquire_and_authorize_dispatch(
        self,
        attempt: ExecutionDispatchClaimAttempt,
        *,
        claimed_at: datetime,
        authorized_at: datetime,
    ) -> DispatchClaimResult: ...


class ControlledPaperSubmissionService:
    """Cross the effect boundary only for this process's newly committed winner grant."""

    __slots__ = ("_clock", "_dispatch", "_persistence")

    def __init__(
        self,
        persistence: _DispatchAuthorityProvider,
        dispatch: OneShotPaperDispatchBoundary,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not hasattr(persistence, "unit_of_work") or not callable(dispatch):
            raise TypeError("Valid persistence and dispatch boundaries are required.")
        self._persistence = persistence
        self._dispatch = dispatch
        self._clock = clock or (lambda: datetime.now(UTC))

    def apply_once(
        self, request: ControlledSubmissionRequest
    ) -> ControlledSubmissionResult:
        if not isinstance(request, ControlledSubmissionRequest):
            raise TypeError("request must be a ControlledSubmissionRequest.")
        acquired = self._acquire(request)
        if (
            acquired.status is DispatchClaimStatus.EXACT_REPLAY
            and acquired.claim is not None
        ):
            return _replay(self, request, acquired.claim)
        if (
            acquired.status is not DispatchClaimStatus.ACQUIRED
            or acquired.claim is None
        ):
            status = (
                ControlledSubmissionStatus.IDENTITY_CONFLICT
                if acquired.status
                in {
                    DispatchClaimStatus.IDENTITY_CONFLICT,
                    DispatchClaimStatus.ALREADY_CLAIMED,
                }
                else ControlledSubmissionStatus.BLOCKED
            )
            return _result(request, status, acquired.reason_code)
        if (
            not acquired.authorized
            or acquired.authorization is None
            or acquired.aggregate is None
        ):
            return _result(
                request, ControlledSubmissionStatus.BLOCKED, acquired.reason_code
            )
        claim = acquired.claim
        try:
            order = ControlledPaperOrder.from_claim(claim)
        except Exception:
            self._record_resolution(
                claim,
                acquired.authorization,
                acquired.aggregate,
                _result(
                    request, ControlledSubmissionStatus.BLOCKED, "INVALID_DURABLE_ORDER"
                ),
                DispatchResolutionStatus.PRE_EFFECT_BLOCKED,
                DispatchEffectPhase.PRE_EFFECT,
            )
            return _result(
                request, ControlledSubmissionStatus.BLOCKED, "INVALID_DURABLE_ORDER"
            )
        try:
            dispatched = self._dispatch(order)
        except Exception:
            normalized = _result(
                request,
                ControlledSubmissionStatus.OUTCOME_UNKNOWN,
                "DISPATCH_OUTCOME_UNKNOWN",
                claim_token=claim.claim_token,
                dispatch_invoked=True,
                outcome_unknown=True,
                source_fingerprint=order.order_fingerprint,
            )
        else:
            normalized = _normalize(request, claim, dispatched)
        resolution_status: DispatchResolutionStatus = (
            DispatchResolutionStatus.ACKNOWLEDGED
            if normalized.status is ControlledSubmissionStatus.ACKNOWLEDGED
            else (
                DispatchResolutionStatus.BROKER_REJECTED
                if normalized.status is ControlledSubmissionStatus.BROKER_REJECTED
                else DispatchResolutionStatus.OUTCOME_UNKNOWN
            )
        )
        if normalized.status is ControlledSubmissionStatus.PRE_DISPATCH_FAILURE:
            resolution_status = DispatchResolutionStatus.PRE_EFFECT_BLOCKED
        phase = (
            DispatchEffectPhase.PRE_EFFECT
            if normalized.status is ControlledSubmissionStatus.PRE_DISPATCH_FAILURE
            else (
                DispatchEffectPhase.POST_EFFECT_OBSERVED
                if normalized.broker_reference
                else DispatchEffectPhase.POSSIBLE_POST_EFFECT
            )
        )
        recorded, conflict_owner = self._record_resolution(
            claim,
            acquired.authorization,
            acquired.aggregate,
            normalized,
            resolution_status,
            phase,
        )
        if not recorded:
            owner_aggregate_id = None
            owner_command_id = None
            owner_record_fingerprint = None
            if conflict_owner is not None:
                owner_aggregate_id, owner_command_id, owner_record_fingerprint = (
                    conflict_owner
                )
                conflict_result = _result(
                    request,
                    ControlledSubmissionStatus.OUTCOME_UNKNOWN,
                    "BROKER_REFERENCE_OWNERSHIP_CONFLICT",
                    claim_token=claim.claim_token,
                    broker_reference=normalized.broker_reference,
                    dispatch_invoked=True,
                    outcome_unknown=True,
                    source_fingerprint=normalized.source_fingerprint,
                    conflicting_owner_aggregate_id=owner_aggregate_id,
                    conflicting_owner_command_id=owner_command_id,
                    conflicting_owner_record_fingerprint=owner_record_fingerprint,
                )
                conflict_recorded, _ = self._record_resolution(
                    claim,
                    acquired.authorization,
                    acquired.aggregate,
                    conflict_result,
                    DispatchResolutionStatus.BROKER_REFERENCE_CONFLICT,
                    DispatchEffectPhase.POSSIBLE_POST_EFFECT,
                    register_broker_reference=False,
                )
                if conflict_recorded:
                    return conflict_result
            return _result(
                request,
                ControlledSubmissionStatus.OUTCOME_UNKNOWN,
                (
                    "BROKER_REFERENCE_OWNERSHIP_CONFLICT"
                    if conflict_owner is not None
                    else "DURABLE_RECORDING_FAILED"
                ),
                claim_token=claim.claim_token,
                broker_reference=normalized.broker_reference,
                dispatch_invoked=True,
                outcome_unknown=True,
                source_fingerprint=normalized.source_fingerprint,
                conflicting_owner_aggregate_id=owner_aggregate_id,
                conflicting_owner_command_id=owner_command_id,
                conflicting_owner_record_fingerprint=owner_record_fingerprint,
            )
        return normalized

    def _acquire(self, request: ControlledSubmissionRequest):
        now = self._clock()
        return self._persistence.acquire_and_authorize_dispatch(
            request.to_attempt(), claimed_at=now, authorized_at=now
        )

    def _record_resolution(
        self,
        claim: ExecutionDispatchClaim,
        authorization: ExecutionDispatchAuthorizationRecord,
        aggregate,
        result: ControlledSubmissionResult,
        status: DispatchResolutionStatus,
        phase: DispatchEffectPhase,
        *,
        register_broker_reference: bool = True,
    ) -> tuple[
        bool,
        tuple[PaperExecutionAggregateId, PaperExecutionCommandId, str] | None,
    ]:
        try:
            with self._persistence.unit_of_work() as unit:
                now = self._clock()
                broker_record = (
                    None
                    if result.broker_reference is None or not register_broker_reference
                    else ExecutionBrokerReferenceRecord(
                        result.broker_reference,
                        claim.aggregate_id,
                        claim.command_id,
                        "controlled-paper-submission",
                        ExecutionBrokerReferenceStatus.ACTIVE,
                        now,
                        now,
                        True,
                        4,
                    )
                )
                evidence = _outcome_evidence(claim, result, status, now)
                transitions, updated = _outcome_lifecycle(
                    claim, aggregate, result, status, evidence, now
                )
                resolution = ExecutionDispatchResolutionRecord(
                    claim_token=claim.claim_token,
                    status=status,
                    effect_phase=phase,
                    resolved_at=now,
                    broker_reference=(
                        None
                        if result.broker_reference is None
                        else str(result.broker_reference)
                    ),
                    observation_fingerprint=result.source_fingerprint,
                    conflicting_owner_aggregate_id=(
                        result.conflicting_owner_aggregate_id
                    ),
                    conflicting_owner_command_id=result.conflicting_owner_command_id,
                    conflicting_owner_record_fingerprint=(
                        result.conflicting_owner_record_fingerprint
                    ),
                    result_fingerprint=result.result_fingerprint,
                    evidence_fingerprint=(
                        evidence.receipt.receipt_fingerprint
                        if isinstance(evidence, ExecutionReceiptRecord)
                        else evidence.failure.failure_fingerprint
                    ),
                    evidence_record_fingerprint=evidence.record_fingerprint,
                    safe_reason_code=result.reason_code,
                    reconciliation_required=result.outcome_unknown,
                    operator_action_required=result.operator_action_required,
                    schema_version=4,
                )
                saved = unit.record_dispatch_outcome(
                    DispatchOutcomeWriteSet(
                        claim,
                        authorization,
                        aggregate.execution_revision,
                        evidence,
                        transitions,
                        updated,
                        resolution,
                        broker_record,
                    )
                )
                if saved.status is not ExecutionPersistenceResultStatus.CREATED:
                    unit.rollback()
                    conflict = saved.conflict
                    owner = (
                        None
                        if (
                            saved.status
                            is not ExecutionPersistenceResultStatus.DUPLICATE_BROKER_REFERENCE
                            or conflict is None
                            or conflict.aggregate_id is None
                            or conflict.command_id is None
                            or saved.record_fingerprint is None
                        )
                        else (
                            conflict.aggregate_id,
                            conflict.command_id,
                            saved.record_fingerprint,
                        )
                    )
                    return False, owner
                return unit.commit().committed, None
        except Exception:
            return False, None


def _outcome_evidence(
    claim: ExecutionDispatchClaim,
    result: ControlledSubmissionResult,
    status: DispatchResolutionStatus,
    now: datetime,
) -> ExecutionReceiptRecord | ExecutionFailureRecord:
    if status is DispatchResolutionStatus.PRE_EFFECT_BLOCKED:
        failure_kind = result.failure_kind or {
            "INVALID_DURABLE_ORDER": PaperExecutionFailureKind.CONTRACT_VALIDATION,
            "FINAL_GUARD_BLOCKED": PaperExecutionFailureKind.AUTHORIZATION_FAILURE,
            "GUARD_DISABLED": PaperExecutionFailureKind.AUTHORIZATION_FAILURE,
            "EMERGENCY_STOP": PaperExecutionFailureKind.AUTHORIZATION_FAILURE,
            "LEGACY_AUTHORITY_ACTIVE": PaperExecutionFailureKind.AUTHORIZATION_FAILURE,
            "BROKER_UNAVAILABLE": PaperExecutionFailureKind.BROKER_UNAVAILABLE,
            "APPROVAL_INVALID": PaperExecutionFailureKind.APPROVAL_INVALID,
            "MARKET_CLOSED": PaperExecutionFailureKind.MARKET_CLOSED,
            "AUTHENTICATION_FAILURE": PaperExecutionFailureKind.AUTHENTICATION_FAILURE,
            "BROKER_REJECTED": PaperExecutionFailureKind.BROKER_REJECTED,
            "RATE_LIMITED": PaperExecutionFailureKind.RATE_LIMITED,
            "TRANSPORT_TIMEOUT": PaperExecutionFailureKind.TRANSPORT_TIMEOUT,
        }.get(result.reason_code, PaperExecutionFailureKind.INTERNAL_INVARIANT)
        return ExecutionFailureRecord(
            PaperExecutionFailure(
                failure_kind,
                PaperExecutionFailureSeverity.ERROR,
                result.reason_code,
                "Paper dispatch stopped before an external effect.",
                False,
                False,
                result.operator_action_required,
                True,
                True,
                claim.command_id,
                claim.aggregate_id,
                claim.correlation_id,
            ),
            now,
            4,
        )
    kind, execution_status = {
        DispatchResolutionStatus.ACKNOWLEDGED: (
            PaperExecutionReceiptKind.BROKER_ACKNOWLEDGED,
            PaperExecutionStatus.ACKNOWLEDGED,
        ),
        DispatchResolutionStatus.BROKER_REJECTED: (
            PaperExecutionReceiptKind.BROKER_REJECTED,
            PaperExecutionStatus.BROKER_REJECTED,
        ),
        DispatchResolutionStatus.OUTCOME_UNKNOWN: (
            PaperExecutionReceiptKind.OUTCOME_UNKNOWN,
            PaperExecutionStatus.OUTCOME_UNKNOWN,
        ),
        DispatchResolutionStatus.BROKER_REFERENCE_CONFLICT: (
            PaperExecutionReceiptKind.OUTCOME_UNKNOWN,
            PaperExecutionStatus.OUTCOME_UNKNOWN,
        ),
    }[status]
    ambiguous_outcome = status in {
        DispatchResolutionStatus.OUTCOME_UNKNOWN,
        DispatchResolutionStatus.BROKER_REFERENCE_CONFLICT,
    }
    return ExecutionReceiptRecord(
        PaperExecutionReceipt(
            claim.command_id,
            claim.aggregate_id,
            claim.correlation_id,
            PaperExecutionOperation.SUBMIT,
            kind,
            execution_status,
            claim.expected_execution_revision.next(),
            now,
            result.reason_code,
            result.broker_reference,
            not ambiguous_outcome,
            ambiguous_outcome,
        ),
        now,
        4,
    )


def _outcome_lifecycle(
    claim: ExecutionDispatchClaim,
    aggregate,
    result: ControlledSubmissionResult,
    status: DispatchResolutionStatus,
    evidence: ExecutionReceiptRecord | ExecutionFailureRecord,
    now: datetime,
):
    receipt_fp = (
        evidence.receipt.receipt_fingerprint
        if isinstance(evidence, ExecutionReceiptRecord)
        else None
    )
    failure_fp = (
        evidence.failure.failure_fingerprint
        if isinstance(evidence, ExecutionFailureRecord)
        else None
    )
    edges = (
        (
            (
                "PX-TRN-029",
                PaperExecutionLifecycleInputType.ABORT_BEFORE_DISPATCH,
                PaperExecutionLifecycleState.ABORTED_BEFORE_DISPATCH,
            ),
        )
        if status is DispatchResolutionStatus.PRE_EFFECT_BLOCKED
        else (
            (
                "PX-TRN-009",
                PaperExecutionLifecycleInputType.RECORD_DISPATCH,
                PaperExecutionLifecycleState.DISPATCHED,
            ),
            {
                DispatchResolutionStatus.ACKNOWLEDGED: (
                    "PX-TRN-010",
                    PaperExecutionLifecycleInputType.OBSERVE_BROKER_ACKNOWLEDGEMENT,
                    PaperExecutionLifecycleState.BROKER_ACKNOWLEDGED,
                ),
                DispatchResolutionStatus.BROKER_REJECTED: (
                    "PX-TRN-011",
                    PaperExecutionLifecycleInputType.OBSERVE_BROKER_REJECTION,
                    PaperExecutionLifecycleState.BROKER_REJECTED,
                ),
                DispatchResolutionStatus.OUTCOME_UNKNOWN: (
                    "PX-TRN-012",
                    PaperExecutionLifecycleInputType.MARK_OUTCOME_UNKNOWN,
                    PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
                ),
                DispatchResolutionStatus.BROKER_REFERENCE_CONFLICT: (
                    "PX-TRN-012",
                    PaperExecutionLifecycleInputType.MARK_OUTCOME_UNKNOWN,
                    PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
                ),
            }[status],
        )
    )
    transitions = []
    source = aggregate.lifecycle_state
    revision = aggregate.execution_revision
    for index, (transition_id, input_kind, destination) in enumerate(edges):
        next_revision = revision.next()
        terminal = destination in {
            PaperExecutionLifecycleState.ABORTED_BEFORE_DISPATCH,
            PaperExecutionLifecycleState.BROKER_REJECTED,
        }
        unknown = destination is PaperExecutionLifecycleState.OUTCOME_UNKNOWN
        transitions.append(
            ExecutionTransitionRecord(
                f"{claim.claim_token}-{transition_id}",
                claim.aggregate_id,
                transition_id,
                source,
                destination,
                revision,
                next_revision,
                input_kind,
                result.source_fingerprint or result.result_fingerprint,
                claim.command_id,
                claim.correlation_id,
                claim.idempotency_key,
                ExecutionReplayKind.NONE,
                (
                    (
                        PaperExecutionLifecycleSideEffectIntentKind.WOULD_DISPATCH
                        if transition_id == "PX-TRN-009"
                        else PaperExecutionLifecycleSideEffectIntentKind.NONE
                    ),
                ),
                (
                    (
                        PaperExecutionLifecycleEvidenceIntentKind.LIFECYCLE_RECONCILIATION_REQUIRED
                        if unknown
                        else (
                            PaperExecutionLifecycleEvidenceIntentKind.LIFECYCLE_TERMINAL_STATE_REACHED
                            if terminal
                            else PaperExecutionLifecycleEvidenceIntentKind.LIFECYCLE_TRANSITION_ACCEPTED
                        )
                    ),
                ),
                "ACCEPTED",
                now,
                4,
                broker_observation_identity=(
                    result.source_fingerprint if index == len(edges) - 1 else None
                ),
                receipt_fingerprint=(receipt_fp if index == len(edges) - 1 else None),
                failure_fingerprint=(failure_fp if index == len(edges) - 1 else None),
            )
        )
        source, revision = destination, next_revision
    updated = replace(
        aggregate,
        lifecycle_state=source,
        execution_revision=revision,
        active_broker_reference=result.broker_reference,
        outcome_unknown=source is PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
        reconciliation_required=source is PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
        command_terminal=is_command_terminal(source),
        aggregate_terminal=is_aggregate_terminal(source),
        last_transition_id=transitions[-1].transition_id,
        last_receipt_fingerprint=receipt_fp,
        last_failure_fingerprint=failure_fp,
        updated_at=now,
    )
    return tuple(transitions), updated


def _replay(
    service: ControlledPaperSubmissionService,
    request: ControlledSubmissionRequest,
    claim: ExecutionDispatchClaim,
) -> ControlledSubmissionResult:
    with service._persistence.unit_of_work() as unit:
        resolution = unit.dispatch_resolutions.get(claim.claim_token)
        unit.rollback()
    if resolution is None:
        return _result(
            request,
            ControlledSubmissionStatus.BLOCKED,
            "UNRESOLVED_CLAIM",
            claim_token=claim.claim_token,
        )
    if resolution.status is DispatchResolutionStatus.PRE_EFFECT_BLOCKED:
        return _result(
            request,
            ControlledSubmissionStatus.EXACT_REPLAY,
            resolution.safe_reason_code,
            claim_token=claim.claim_token,
            source_fingerprint=resolution.result_fingerprint,
        )
    replay_status = (
        ControlledSubmissionStatus.ACKNOWLEDGED
        if resolution.status is DispatchResolutionStatus.ACKNOWLEDGED
        else (
            ControlledSubmissionStatus.BROKER_REJECTED
            if resolution.status is DispatchResolutionStatus.BROKER_REJECTED
            else ControlledSubmissionStatus.OUTCOME_UNKNOWN
        )
    )
    return _result(
        request,
        replay_status,
        resolution.safe_reason_code,
        claim_token=claim.claim_token,
        broker_reference=(
            None
            if resolution.broker_reference is None
            else PaperBrokerOrderReference(resolution.broker_reference)
        ),
        dispatch_invoked=True,
        outcome_unknown=resolution.reconciliation_required,
        source_fingerprint=resolution.observation_fingerprint,
        conflicting_owner_aggregate_id=resolution.conflicting_owner_aggregate_id,
        conflicting_owner_command_id=resolution.conflicting_owner_command_id,
        conflicting_owner_record_fingerprint=(
            resolution.conflicting_owner_record_fingerprint
        ),
    )


def _normalize(
    request: ControlledSubmissionRequest,
    claim: ExecutionDispatchClaim,
    value: object,
) -> ControlledSubmissionResult:
    if (
        isinstance(value, PaperDispatchObservation)
        and value.submission_id == request.submission_id
    ):
        return _result(
            request,
            (
                ControlledSubmissionStatus.ACKNOWLEDGED
                if value.accepted
                else ControlledSubmissionStatus.BROKER_REJECTED
            ),
            value.message_code,
            claim_token=claim.claim_token,
            broker_reference=value.broker_reference,
            dispatch_invoked=True,
            source_fingerprint=value.observation_fingerprint,
        )
    if (
        isinstance(value, PaperDispatchFailure)
        and value.submission_id == request.submission_id
    ):
        unknown = value.phase is DispatchFailurePhase.POSSIBLE_POST_DISPATCH
        return _result(
            request,
            (
                ControlledSubmissionStatus.OUTCOME_UNKNOWN
                if unknown
                else ControlledSubmissionStatus.PRE_DISPATCH_FAILURE
            ),
            value.reason_code,
            claim_token=claim.claim_token,
            dispatch_invoked=True,
            outcome_unknown=unknown,
            source_fingerprint=value.failure_fingerprint,
            failure_kind=value.failure_kind,
        )
    return _result(
        request,
        ControlledSubmissionStatus.OUTCOME_UNKNOWN,
        "MALFORMED_DISPATCH_RESULT",
        claim_token=claim.claim_token,
        dispatch_invoked=True,
        outcome_unknown=True,
    )


def _result(
    request: ControlledSubmissionRequest,
    status: ControlledSubmissionStatus,
    reason_code: str,
    *,
    claim_token: str | None = None,
    broker_reference: PaperBrokerOrderReference | None = None,
    dispatch_invoked: bool = False,
    outcome_unknown: bool = False,
    source_fingerprint: str | None = None,
    failure_kind: PaperExecutionFailureKind | None = None,
    conflicting_owner_aggregate_id: PaperExecutionAggregateId | None = None,
    conflicting_owner_command_id: PaperExecutionCommandId | None = None,
    conflicting_owner_record_fingerprint: str | None = None,
) -> ControlledSubmissionResult:
    return ControlledSubmissionResult(
        submission_id=request.submission_id,
        request_fingerprint=request.request_fingerprint,
        status=status,
        reason_code=reason_code,
        claim_token=claim_token,
        broker_reference=broker_reference,
        dispatch_invoked=dispatch_invoked,
        outcome_unknown=outcome_unknown,
        reconciliation_required=outcome_unknown,
        operator_action_required=outcome_unknown,
        source_fingerprint=source_fingerprint,
        failure_kind=failure_kind,
        conflicting_owner_aggregate_id=conflicting_owner_aggregate_id,
        conflicting_owner_command_id=conflicting_owner_command_id,
        conflicting_owner_record_fingerprint=conflicting_owner_record_fingerprint,
    )
