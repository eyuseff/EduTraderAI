"""Pure side-effect-free Paper execution eligibility service."""

from __future__ import annotations

from datetime import UTC, datetime

from volcanoes.application.execution._canonical import normalize_datetime
from volcanoes.application.execution.contracts import PaperExecutionCommand
from volcanoes.application.execution.enums import (
    PaperExecutionMode,
    PaperExecutionOperation,
)
from volcanoes.application.execution.errors import PaperExecutionSerializationError
from volcanoes.application.execution.fingerprints import command_payload_fingerprint
from volcanoes.application.execution.eligibility.enums import (
    PaperExecutionEligibilityCriterion,
    PaperExecutionEligibilityCriterionOutcome,
    PaperExecutionEligibilityDecision,
    PaperExecutionEligibilityFailureCode,
    PaperExecutionEligibilitySeverity,
)
from volcanoes.application.execution.eligibility.errors import (
    PaperExecutionEligibilityError,
)
from volcanoes.application.execution.eligibility.policy import (
    PaperExecutionEligibilityPolicy,
)
from volcanoes.application.execution.eligibility.result import (
    PaperExecutionEligibilityCriterionResult,
    PaperExecutionEligibilityResult,
)


class PaperExecutionEligibilityService:
    """Evaluate advisory eligibility for one immutable Paper command."""

    def evaluate(
        self,
        command: PaperExecutionCommand,
        policy: PaperExecutionEligibilityPolicy,
        *,
        evaluated_at: datetime | None = None,
    ) -> PaperExecutionEligibilityResult:
        """Return a deterministic advisory eligibility result."""

        if not isinstance(command, PaperExecutionCommand):
            raise PaperExecutionEligibilityError(
                "INVALID_COMMAND_TYPE",
                "Eligibility evaluation requires a PaperExecutionCommand.",
            )
        if not isinstance(policy, PaperExecutionEligibilityPolicy):
            raise PaperExecutionEligibilityError(
                "INVALID_ELIGIBILITY_POLICY",
                "Eligibility evaluation requires an eligibility policy.",
            )
        normalized_evaluated_at = _normalize_evaluated_at(evaluated_at)
        criteria = tuple(_criteria(command, policy, normalized_evaluated_at))
        decision = _decision(criteria)
        return PaperExecutionEligibilityResult(
            decision=decision,
            command_id=command.command_id,
            aggregate_id=command.aggregate_id,
            correlation_id=command.correlation_id,
            policy_fingerprint=policy.policy_fingerprint,
            command_payload_fingerprint=command.payload_fingerprint,
            evaluated_at=normalized_evaluated_at,
            criteria=criteria,
        )


def _criteria(
    command: PaperExecutionCommand,
    policy: PaperExecutionEligibilityPolicy,
    evaluated_at: datetime | None,
) -> tuple[PaperExecutionEligibilityCriterionResult, ...]:
    results = [
        _passed(
            PaperExecutionEligibilityCriterion.COMMAND_TYPE_VALID,
            command,
            PaperExecutionEligibilityFailureCode.ELIGIBLE,
        ),
        _paper_mode(command, policy),
        _operation_allowed(command, policy),
        _identity_present(
            PaperExecutionEligibilityCriterion.COMMAND_IDENTITY_PRESENT,
            command,
            PaperExecutionEligibilityFailureCode.COMMAND_IDENTITY_INVALID,
        ),
        _payload_fingerprint(command, policy),
        _aggregate_identity(command, policy),
        _correlation_identity(command, policy),
        _idempotency_key(command, policy),
        _idempotency_consistency(command, policy),
        _expected_revision(command, policy),
        _operation_revision(command, policy),
        _intent_compatible(command, policy),
        _approval_present(command, policy),
        _approval_binding(command, policy),
        _approval_time(command, policy, evaluated_at),
        _policy_snapshot(command, policy),
        _context_consistent(command, policy),
        _passed(
            PaperExecutionEligibilityCriterion.NO_READINESS_AUTHORITY,
            command,
            PaperExecutionEligibilityFailureCode.ELIGIBLE,
        ),
        _external(
            PaperExecutionEligibilityCriterion.EXTERNAL_MARKET_CAPABILITY_STATUS,
            policy.require_external_market_capability,
            command,
            PaperExecutionEligibilityFailureCode.MARKET_CAPABILITY_CLEARANCE_REQUIRED,
        ),
        _external(
            PaperExecutionEligibilityCriterion.EXTERNAL_EMERGENCY_STOP_STATUS,
            policy.require_external_emergency_stop_clearance,
            command,
            PaperExecutionEligibilityFailureCode.EMERGENCY_STOP_CLEARANCE_REQUIRED,
        ),
        _external(
            PaperExecutionEligibilityCriterion.EXTERNAL_RISK_STATUS,
            policy.require_external_risk_clearance,
            command,
            PaperExecutionEligibilityFailureCode.RISK_CLEARANCE_REQUIRED,
        ),
        _external(
            PaperExecutionEligibilityCriterion.EXTERNAL_ACCOUNT_STATUS,
            policy.require_external_account_clearance,
            command,
            PaperExecutionEligibilityFailureCode.ACCOUNT_CLEARANCE_REQUIRED,
        ),
    ]
    return tuple(sorted(results, key=lambda item: item.criterion.value))


def _paper_mode(
    command: PaperExecutionCommand,
    policy: PaperExecutionEligibilityPolicy,
) -> PaperExecutionEligibilityCriterionResult:
    if not policy.require_paper_mode or command.mode is PaperExecutionMode.PAPER:
        return _passed(
            PaperExecutionEligibilityCriterion.PAPER_MODE_VALID,
            command,
            PaperExecutionEligibilityFailureCode.ELIGIBLE,
        )
    return _failed(
        PaperExecutionEligibilityCriterion.PAPER_MODE_VALID,
        command,
        PaperExecutionEligibilityFailureCode.PAPER_MODE_REQUIRED,
    )


def _operation_allowed(
    command: PaperExecutionCommand,
    policy: PaperExecutionEligibilityPolicy,
) -> PaperExecutionEligibilityCriterionResult:
    if command.operation in policy.allowed_operations:
        return _passed(
            PaperExecutionEligibilityCriterion.OPERATION_ALLOWED,
            command,
            PaperExecutionEligibilityFailureCode.ELIGIBLE,
        )
    return _failed(
        PaperExecutionEligibilityCriterion.OPERATION_ALLOWED,
        command,
        PaperExecutionEligibilityFailureCode.OPERATION_NOT_ALLOWED,
    )


def _identity_present(
    criterion: PaperExecutionEligibilityCriterion,
    command: PaperExecutionCommand,
    failure: PaperExecutionEligibilityFailureCode,
) -> PaperExecutionEligibilityCriterionResult:
    return _passed(criterion, command, failure)


def _payload_fingerprint(
    command: PaperExecutionCommand,
    policy: PaperExecutionEligibilityPolicy,
) -> PaperExecutionEligibilityCriterionResult:
    if not policy.require_payload_fingerprint_consistency:
        return _passed(
            PaperExecutionEligibilityCriterion.PAYLOAD_FINGERPRINT_VALID,
            command,
            PaperExecutionEligibilityFailureCode.ELIGIBLE,
        )
    recomputed = command_payload_fingerprint(command.canonical_payload())
    if recomputed == command.payload_fingerprint:
        return _passed(
            PaperExecutionEligibilityCriterion.PAYLOAD_FINGERPRINT_VALID,
            command,
            PaperExecutionEligibilityFailureCode.ELIGIBLE,
        )
    return _failed(
        PaperExecutionEligibilityCriterion.PAYLOAD_FINGERPRINT_VALID,
        command,
        PaperExecutionEligibilityFailureCode.PAYLOAD_FINGERPRINT_MISMATCH,
    )


def _aggregate_identity(
    command: PaperExecutionCommand,
    policy: PaperExecutionEligibilityPolicy,
) -> PaperExecutionEligibilityCriterionResult:
    if (
        not policy.require_aggregate_identity_consistency
        or command.aggregate_id == command.context.aggregate_id
    ):
        return _passed(
            PaperExecutionEligibilityCriterion.AGGREGATE_IDENTITY_VALID,
            command,
            PaperExecutionEligibilityFailureCode.ELIGIBLE,
        )
    return _failed(
        PaperExecutionEligibilityCriterion.AGGREGATE_IDENTITY_VALID,
        command,
        PaperExecutionEligibilityFailureCode.AGGREGATE_IDENTITY_MISMATCH,
    )


def _correlation_identity(
    command: PaperExecutionCommand,
    policy: PaperExecutionEligibilityPolicy,
) -> PaperExecutionEligibilityCriterionResult:
    if (
        not policy.require_correlation_identity_consistency
        or command.correlation_id == command.context.correlation_id
    ):
        return _passed(
            PaperExecutionEligibilityCriterion.CORRELATION_IDENTITY_VALID,
            command,
            PaperExecutionEligibilityFailureCode.ELIGIBLE,
        )
    return _failed(
        PaperExecutionEligibilityCriterion.CORRELATION_IDENTITY_VALID,
        command,
        PaperExecutionEligibilityFailureCode.CORRELATION_IDENTITY_MISMATCH,
    )


def _idempotency_key(
    command: PaperExecutionCommand,
    policy: PaperExecutionEligibilityPolicy,
) -> PaperExecutionEligibilityCriterionResult:
    if policy.require_idempotency_key and command.idempotency_key is None:
        return _failed(
            PaperExecutionEligibilityCriterion.IDEMPOTENCY_KEY_PRESENT,
            command,
            PaperExecutionEligibilityFailureCode.IDEMPOTENCY_KEY_MISSING,
        )
    return _passed(
        PaperExecutionEligibilityCriterion.IDEMPOTENCY_KEY_PRESENT,
        command,
        PaperExecutionEligibilityFailureCode.ELIGIBLE,
    )


def _idempotency_consistency(
    command: PaperExecutionCommand,
    policy: PaperExecutionEligibilityPolicy,
) -> PaperExecutionEligibilityCriterionResult:
    if not policy.require_idempotency_key_consistency:
        return _passed(
            PaperExecutionEligibilityCriterion.IDEMPOTENCY_KEY_CONSISTENT,
            command,
            PaperExecutionEligibilityFailureCode.ELIGIBLE,
        )
    return _unresolved(
        PaperExecutionEligibilityCriterion.IDEMPOTENCY_KEY_CONSISTENT,
        command,
        PaperExecutionEligibilityFailureCode.IDEMPOTENCY_KEY_UNVERIFIABLE,
    )


def _expected_revision(
    command: PaperExecutionCommand,
    policy: PaperExecutionEligibilityPolicy,
) -> PaperExecutionEligibilityCriterionResult:
    if policy.require_expected_revision:
        return _passed(
            PaperExecutionEligibilityCriterion.EXPECTED_REVISION_VALID,
            command,
            PaperExecutionEligibilityFailureCode.ELIGIBLE,
        )
    return _passed(
        PaperExecutionEligibilityCriterion.EXPECTED_REVISION_VALID,
        command,
        PaperExecutionEligibilityFailureCode.ELIGIBLE,
    )


def _operation_revision(
    command: PaperExecutionCommand,
    policy: PaperExecutionEligibilityPolicy,
) -> PaperExecutionEligibilityCriterionResult:
    if (
        policy.require_initial_submit_revision
        and command.operation is PaperExecutionOperation.SUBMIT
        and command.expected_execution_revision.value != 0
    ):
        return _failed(
            PaperExecutionEligibilityCriterion.OPERATION_REVISION_COMPATIBLE,
            command,
            PaperExecutionEligibilityFailureCode.INITIAL_SUBMIT_REVISION_REQUIRED,
        )
    return _passed(
        PaperExecutionEligibilityCriterion.OPERATION_REVISION_COMPATIBLE,
        command,
        PaperExecutionEligibilityFailureCode.ELIGIBLE,
    )


def _intent_compatible(
    command: PaperExecutionCommand,
    policy: PaperExecutionEligibilityPolicy,
) -> PaperExecutionEligibilityCriterionResult:
    if not policy.require_supported_intent:
        return _passed(
            PaperExecutionEligibilityCriterion.INTENT_COMPATIBLE,
            command,
            PaperExecutionEligibilityFailureCode.ELIGIBLE,
        )
    if command.operation is PaperExecutionOperation.SUBMIT and command.intent is None:
        return _failed(
            PaperExecutionEligibilityCriterion.INTENT_COMPATIBLE,
            command,
            PaperExecutionEligibilityFailureCode.INTENT_REQUIRED,
        )
    if (
        command.operation is PaperExecutionOperation.REPLACE
        and command.replacement_intent is None
    ):
        return _failed(
            PaperExecutionEligibilityCriterion.INTENT_COMPATIBLE,
            command,
            PaperExecutionEligibilityFailureCode.INTENT_REQUIRED,
        )
    if command.operation is PaperExecutionOperation.CANCEL and (
        command.intent is not None or command.replacement_intent is not None
    ):
        return _failed(
            PaperExecutionEligibilityCriterion.INTENT_COMPATIBLE,
            command,
            PaperExecutionEligibilityFailureCode.INTENT_NOT_ALLOWED,
        )
    return _passed(
        PaperExecutionEligibilityCriterion.INTENT_COMPATIBLE,
        command,
        PaperExecutionEligibilityFailureCode.ELIGIBLE,
    )


def _approval_present(
    command: PaperExecutionCommand,
    policy: PaperExecutionEligibilityPolicy,
) -> PaperExecutionEligibilityCriterionResult:
    if policy.require_explicit_approval and command.approval is None:
        return _failed(
            PaperExecutionEligibilityCriterion.APPROVAL_PRESENT,
            command,
            PaperExecutionEligibilityFailureCode.APPROVAL_REQUIRED,
        )
    return _passed(
        PaperExecutionEligibilityCriterion.APPROVAL_PRESENT,
        command,
        PaperExecutionEligibilityFailureCode.ELIGIBLE,
    )


def _approval_binding(
    command: PaperExecutionCommand,
    policy: PaperExecutionEligibilityPolicy,
) -> PaperExecutionEligibilityCriterionResult:
    if not policy.require_approval_binding:
        return _passed(
            PaperExecutionEligibilityCriterion.APPROVAL_BINDING_VALID,
            command,
            PaperExecutionEligibilityFailureCode.ELIGIBLE,
        )
    if command.approval is None:
        return _failed(
            PaperExecutionEligibilityCriterion.APPROVAL_BINDING_VALID,
            command,
            PaperExecutionEligibilityFailureCode.APPROVAL_REQUIRED,
        )
    allowed = {command.payload_fingerprint}
    allowed.add(command_payload_fingerprint(command.aggregate_id.to_primitive()))
    if command.intent is not None:
        allowed.add(command_payload_fingerprint(command.intent.to_primitive()))
    if command.replacement_intent is not None:
        allowed.add(
            command_payload_fingerprint(command.replacement_intent.to_primitive())
        )
    if command.approval.bound_fingerprint in allowed:
        return _passed(
            PaperExecutionEligibilityCriterion.APPROVAL_BINDING_VALID,
            command,
            PaperExecutionEligibilityFailureCode.ELIGIBLE,
        )
    return _failed(
        PaperExecutionEligibilityCriterion.APPROVAL_BINDING_VALID,
        command,
        PaperExecutionEligibilityFailureCode.APPROVAL_BINDING_MISMATCH,
    )


def _approval_time(
    command: PaperExecutionCommand,
    policy: PaperExecutionEligibilityPolicy,
    evaluated_at: datetime | None,
) -> PaperExecutionEligibilityCriterionResult:
    if not policy.require_unexpired_approval:
        return _passed(
            PaperExecutionEligibilityCriterion.APPROVAL_TIME_VALID,
            command,
            PaperExecutionEligibilityFailureCode.ELIGIBLE,
        )
    if evaluated_at is None:
        return _unresolved(
            PaperExecutionEligibilityCriterion.APPROVAL_TIME_VALID,
            command,
            PaperExecutionEligibilityFailureCode.EVALUATION_TIME_REQUIRED,
        )
    if command.approval is None:
        return _failed(
            PaperExecutionEligibilityCriterion.APPROVAL_TIME_VALID,
            command,
            PaperExecutionEligibilityFailureCode.APPROVAL_REQUIRED,
        )
    if command.approval.approved_at > evaluated_at:
        return _failed(
            PaperExecutionEligibilityCriterion.APPROVAL_TIME_VALID,
            command,
            PaperExecutionEligibilityFailureCode.APPROVAL_NOT_YET_VALID,
        )
    if (
        command.approval.expires_at is not None
        and command.approval.expires_at <= evaluated_at
    ):
        return _failed(
            PaperExecutionEligibilityCriterion.APPROVAL_TIME_VALID,
            command,
            PaperExecutionEligibilityFailureCode.APPROVAL_EXPIRED,
        )
    return _passed(
        PaperExecutionEligibilityCriterion.APPROVAL_TIME_VALID,
        command,
        PaperExecutionEligibilityFailureCode.ELIGIBLE,
    )


def _policy_snapshot(
    command: PaperExecutionCommand,
    policy: PaperExecutionEligibilityPolicy,
) -> PaperExecutionEligibilityCriterionResult:
    if not policy.require_policy_snapshot_compatibility:
        return _passed(
            PaperExecutionEligibilityCriterion.POLICY_SNAPSHOT_COMPATIBLE,
            command,
            PaperExecutionEligibilityFailureCode.ELIGIBLE,
        )
    snapshot = command.policy_snapshot
    compatible = (
        command.operation in snapshot.allowed_operations
        and (not policy.require_paper_mode or snapshot.paper_only_required)
        and (
            not policy.require_explicit_approval or snapshot.explicit_approval_required
        )
        and (
            not policy.require_expected_revision or snapshot.execution_revision_required
        )
        and (
            not policy.require_idempotency_key
            or snapshot.deterministic_idempotency_required
        )
    )
    if compatible:
        return _passed(
            PaperExecutionEligibilityCriterion.POLICY_SNAPSHOT_COMPATIBLE,
            command,
            PaperExecutionEligibilityFailureCode.ELIGIBLE,
        )
    return _failed(
        PaperExecutionEligibilityCriterion.POLICY_SNAPSHOT_COMPATIBLE,
        command,
        PaperExecutionEligibilityFailureCode.POLICY_SNAPSHOT_INCOMPATIBLE,
    )


def _context_consistent(
    command: PaperExecutionCommand,
    policy: PaperExecutionEligibilityPolicy,
) -> PaperExecutionEligibilityCriterionResult:
    if not policy.require_context_identity_consistency:
        return _passed(
            PaperExecutionEligibilityCriterion.CONTEXT_CONSISTENT,
            command,
            PaperExecutionEligibilityFailureCode.ELIGIBLE,
        )
    if (
        command.aggregate_id == command.context.aggregate_id
        and command.correlation_id == command.context.correlation_id
    ):
        return _passed(
            PaperExecutionEligibilityCriterion.CONTEXT_CONSISTENT,
            command,
            PaperExecutionEligibilityFailureCode.ELIGIBLE,
        )
    return _failed(
        PaperExecutionEligibilityCriterion.CONTEXT_CONSISTENT,
        command,
        PaperExecutionEligibilityFailureCode.CONTEXT_INCONSISTENT,
    )


def _external(
    criterion: PaperExecutionEligibilityCriterion,
    required: bool,
    command: PaperExecutionCommand,
    code: PaperExecutionEligibilityFailureCode,
) -> PaperExecutionEligibilityCriterionResult:
    if not required:
        return _passed(
            criterion, command, PaperExecutionEligibilityFailureCode.ELIGIBLE
        )
    return _unresolved(criterion, command, code, external=True)


def _decision(
    criteria: tuple[PaperExecutionEligibilityCriterionResult, ...],
) -> PaperExecutionEligibilityDecision:
    if any(
        item.outcome is PaperExecutionEligibilityCriterionOutcome.FAIL
        for item in criteria
    ):
        return PaperExecutionEligibilityDecision.INELIGIBLE
    if any(
        item.outcome is PaperExecutionEligibilityCriterionOutcome.UNRESOLVED
        for item in criteria
    ):
        return PaperExecutionEligibilityDecision.INDETERMINATE
    return PaperExecutionEligibilityDecision.ELIGIBLE


def _passed(
    criterion: PaperExecutionEligibilityCriterion,
    command: PaperExecutionCommand,
    code: PaperExecutionEligibilityFailureCode,
) -> PaperExecutionEligibilityCriterionResult:
    return PaperExecutionEligibilityCriterionResult(
        criterion=criterion,
        outcome=PaperExecutionEligibilityCriterionOutcome.PASS,
        severity=PaperExecutionEligibilitySeverity.INFO,
        code=code,
        safe_message="ELIGIBILITY_CRITERION_PASSED",
        authority_impacting=False,
        command_id=command.command_id,
        aggregate_id=command.aggregate_id,
    )


def _failed(
    criterion: PaperExecutionEligibilityCriterion,
    command: PaperExecutionCommand,
    code: PaperExecutionEligibilityFailureCode,
) -> PaperExecutionEligibilityCriterionResult:
    return PaperExecutionEligibilityCriterionResult(
        criterion=criterion,
        outcome=PaperExecutionEligibilityCriterionOutcome.FAIL,
        severity=PaperExecutionEligibilitySeverity.BLOCKING,
        code=code,
        safe_message=code.value,
        authority_impacting=True,
        command_id=command.command_id,
        aggregate_id=command.aggregate_id,
    )


def _unresolved(
    criterion: PaperExecutionEligibilityCriterion,
    command: PaperExecutionCommand,
    code: PaperExecutionEligibilityFailureCode,
    *,
    external: bool = False,
) -> PaperExecutionEligibilityCriterionResult:
    return PaperExecutionEligibilityCriterionResult(
        criterion=criterion,
        outcome=PaperExecutionEligibilityCriterionOutcome.UNRESOLVED,
        severity=PaperExecutionEligibilitySeverity.UNRESOLVED,
        code=code,
        safe_message=code.value,
        authority_impacting=True,
        external_evidence_required=external,
        command_id=command.command_id,
        aggregate_id=command.aggregate_id,
    )


def _normalize_evaluated_at(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    try:
        normalize_datetime(value, "evaluated_at")
    except PaperExecutionSerializationError as error:
        raise PaperExecutionEligibilityError(
            error.reason_code,
            error.safe_message,
        ) from error
    return value.astimezone(UTC)
