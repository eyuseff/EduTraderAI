from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from volcanoes.application.execution import (
    PaperExecutionAggregateId,
    PaperExecutionApproval,
    PaperExecutionApprovalKind,
    PaperExecutionCommand,
    PaperExecutionCommandId,
    PaperExecutionContext,
    PaperExecutionCorrelationId,
    PaperExecutionEligibilityCriterion,
    PaperExecutionEligibilityCriterionOutcome,
    PaperExecutionEligibilityDecision,
    PaperExecutionEligibilityFailureCode,
    PaperExecutionEligibilityPolicy,
    PaperExecutionEligibilityService,
    PaperExecutionIdempotencyKey,
    PaperExecutionInstrument,
    PaperExecutionIntent,
    PaperExecutionOperation,
    PaperExecutionOrderType,
    PaperExecutionPolicySnapshot,
    PaperExecutionRevision,
    PaperExecutionSide,
)
from volcanoes.application.execution.fingerprints import command_payload_fingerprint


def build_command(
    *,
    operation: PaperExecutionOperation = PaperExecutionOperation.SUBMIT,
    revision: PaperExecutionRevision | None = None,
    approval_bound: str | None = None,
    policy_snapshot: PaperExecutionPolicySnapshot | None = None,
) -> PaperExecutionCommand:
    aggregate_id = PaperExecutionAggregateId.from_seed("aggregate", operation.value)
    correlation_id = PaperExecutionCorrelationId.from_seed(
        "correlation", operation.value
    )
    command_id = PaperExecutionCommandId.from_seed("command", operation.value)
    idempotency_key = PaperExecutionIdempotencyKey.from_seed(
        aggregate_id,
        operation,
        revision or PaperExecutionRevision.initial(),
        "logical-operation",
    )
    intent = PaperExecutionIntent(
        instrument=PaperExecutionInstrument("AAPL"),
        side=PaperExecutionSide.BUY,
        order_type=PaperExecutionOrderType.LIMIT,
        quantity=Decimal("1"),
        limit_price=Decimal("100"),
    )
    replacement_intent = PaperExecutionIntent(
        instrument=PaperExecutionInstrument("AAPL"),
        side=PaperExecutionSide.BUY,
        order_type=PaperExecutionOrderType.LIMIT,
        quantity=Decimal("1"),
        limit_price=Decimal("101"),
    )
    bound_target = (
        aggregate_id.to_primitive()
        if operation is PaperExecutionOperation.CANCEL
        else (
            replacement_intent.to_primitive()
            if operation is PaperExecutionOperation.REPLACE
            else intent.to_primitive()
        )
    )
    approval = PaperExecutionApproval(
        approval_kind=PaperExecutionApprovalKind.OPERATOR,
        approver_reference="operator.primary",
        approval_reference="approval-1",
        bound_fingerprint=approval_bound or command_payload_fingerprint(bound_target),
        approved_at=datetime(2026, 7, 30, 10, tzinfo=UTC),
        expires_at=datetime(2026, 7, 30, 12, tzinfo=UTC),
    )
    context = PaperExecutionContext(
        aggregate_id=aggregate_id,
        correlation_id=correlation_id,
        source_component="manual.paper",
        requested_at=datetime(2026, 7, 30, 10, tzinfo=UTC),
    )
    return PaperExecutionCommand(
        command_id=command_id,
        aggregate_id=aggregate_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        operation=operation,
        expected_execution_revision=revision or PaperExecutionRevision.initial(),
        approval=approval,
        policy_snapshot=policy_snapshot
        or PaperExecutionPolicySnapshot(
            "paper-snapshot-v1",
            allowed_operations=(
                PaperExecutionOperation.SUBMIT,
                PaperExecutionOperation.CANCEL,
                PaperExecutionOperation.REPLACE,
            ),
        ),
        context=context,
        intent=(intent if operation is PaperExecutionOperation.SUBMIT else None),
        replacement_intent=(
            replacement_intent if operation is PaperExecutionOperation.REPLACE else None
        ),
    )


def evaluate(
    command: PaperExecutionCommand,
    policy: PaperExecutionEligibilityPolicy | None = None,
    *,
    evaluated_at: datetime | None = datetime(2026, 7, 30, 11, tzinfo=UTC),
):
    return PaperExecutionEligibilityService().evaluate(
        command,
        policy or PaperExecutionEligibilityPolicy("eligibility-v1"),
        evaluated_at=evaluated_at,
    )


def criterion(result, criterion: PaperExecutionEligibilityCriterion):
    return next(item for item in result.criteria if item.criterion is criterion)


def test_all_criteria_pass_for_valid_submit_command() -> None:
    result = evaluate(build_command())

    assert result.decision is PaperExecutionEligibilityDecision.ELIGIBLE
    assert result.eligible is True
    assert result.failed_criterion_count == 0
    assert result.unresolved_criterion_count == 0
    assert result.execution_authorized is False
    assert result.action_executed is False


@pytest.mark.parametrize(
    "operation",
    (
        PaperExecutionOperation.SUBMIT,
        PaperExecutionOperation.CANCEL,
        PaperExecutionOperation.REPLACE,
    ),
)
def test_allowed_operations_pass(operation: PaperExecutionOperation) -> None:
    result = evaluate(
        build_command(
            operation=operation,
            revision=(
                PaperExecutionRevision(1)
                if operation is not PaperExecutionOperation.SUBMIT
                else PaperExecutionRevision.initial()
            ),
        )
    )

    assert criterion(
        result, PaperExecutionEligibilityCriterion.OPERATION_ALLOWED
    ).passed


def test_disallowed_operation_is_ineligible() -> None:
    result = evaluate(
        build_command(),
        PaperExecutionEligibilityPolicy(
            "eligibility-v1",
            allowed_operations=(PaperExecutionOperation.CANCEL,),
        ),
    )

    assert result.decision is PaperExecutionEligibilityDecision.INELIGIBLE
    assert (
        criterion(result, PaperExecutionEligibilityCriterion.OPERATION_ALLOWED).code
        is PaperExecutionEligibilityFailureCode.OPERATION_NOT_ALLOWED
    )


def test_payload_fingerprint_mismatch_is_ineligible() -> None:
    command = build_command()
    object.__setattr__(command, "payload_fingerprint", "pcf-" + ("0" * 64))

    result = evaluate(command)

    assert result.decision is PaperExecutionEligibilityDecision.INELIGIBLE
    assert (
        criterion(
            result, PaperExecutionEligibilityCriterion.PAYLOAD_FINGERPRINT_VALID
        ).code
        is PaperExecutionEligibilityFailureCode.PAYLOAD_FINGERPRINT_MISMATCH
    )


def test_context_identity_mismatches_are_detected() -> None:
    command = build_command()
    other_context = PaperExecutionContext(
        aggregate_id=PaperExecutionAggregateId.from_seed("other"),
        correlation_id=command.correlation_id,
        source_component="manual.paper",
        requested_at=datetime(2026, 7, 30, 10, tzinfo=UTC),
    )
    object.__setattr__(command, "context", other_context)

    result = evaluate(command)

    assert result.decision is PaperExecutionEligibilityDecision.INELIGIBLE
    assert (
        criterion(
            result, PaperExecutionEligibilityCriterion.AGGREGATE_IDENTITY_VALID
        ).code
        is PaperExecutionEligibilityFailureCode.AGGREGATE_IDENTITY_MISMATCH
    )


def test_idempotency_consistency_required_is_unresolved_not_guessed() -> None:
    result = evaluate(
        build_command(),
        PaperExecutionEligibilityPolicy(
            "eligibility-v1",
            require_idempotency_key_consistency=True,
        ),
    )

    assert result.decision is PaperExecutionEligibilityDecision.INDETERMINATE
    assert (
        criterion(
            result, PaperExecutionEligibilityCriterion.IDEMPOTENCY_KEY_CONSISTENT
        ).outcome
        is PaperExecutionEligibilityCriterionOutcome.UNRESOLVED
    )


def test_submit_revision_must_be_initial_when_policy_requires() -> None:
    result = evaluate(build_command(revision=PaperExecutionRevision(1)))

    assert result.decision is PaperExecutionEligibilityDecision.INELIGIBLE
    assert (
        criterion(
            result, PaperExecutionEligibilityCriterion.OPERATION_REVISION_COMPATIBLE
        ).code
        is PaperExecutionEligibilityFailureCode.INITIAL_SUBMIT_REVISION_REQUIRED
    )


def test_cancel_and_replace_revisions_are_represented_without_storage_lookup() -> None:
    cancel = evaluate(
        build_command(
            operation=PaperExecutionOperation.CANCEL,
            revision=PaperExecutionRevision(3),
        )
    )
    replace = evaluate(
        build_command(
            operation=PaperExecutionOperation.REPLACE,
            revision=PaperExecutionRevision(2),
        )
    )

    assert cancel.decision is PaperExecutionEligibilityDecision.ELIGIBLE
    assert replace.decision is PaperExecutionEligibilityDecision.ELIGIBLE


def test_approval_binding_mismatch_is_ineligible() -> None:
    result = evaluate(build_command(approval_bound="pcf-" + ("9" * 64)))

    assert result.decision is PaperExecutionEligibilityDecision.INELIGIBLE
    assert (
        criterion(
            result, PaperExecutionEligibilityCriterion.APPROVAL_BINDING_VALID
        ).code
        is PaperExecutionEligibilityFailureCode.APPROVAL_BINDING_MISMATCH
    )


def test_missing_approval_returns_ineligible_result_without_raising() -> None:
    command = build_command()
    object.__setattr__(command, "approval", None)

    result = evaluate(command)

    assert result.decision is PaperExecutionEligibilityDecision.INELIGIBLE
    assert (
        criterion(result, PaperExecutionEligibilityCriterion.APPROVAL_PRESENT).code
        is PaperExecutionEligibilityFailureCode.APPROVAL_REQUIRED
    )
    assert (
        criterion(
            result, PaperExecutionEligibilityCriterion.APPROVAL_BINDING_VALID
        ).code
        is PaperExecutionEligibilityFailureCode.APPROVAL_REQUIRED
    )
    assert (
        criterion(result, PaperExecutionEligibilityCriterion.APPROVAL_TIME_VALID).code
        is PaperExecutionEligibilityFailureCode.APPROVAL_REQUIRED
    )


def test_approval_time_boundaries_are_deterministic() -> None:
    command = build_command()

    assert evaluate(
        command, evaluated_at=datetime(2026, 7, 30, 10, tzinfo=UTC)
    ).eligible
    expired = evaluate(command, evaluated_at=datetime(2026, 7, 30, 12, tzinfo=UTC))
    not_yet = evaluate(command, evaluated_at=datetime(2026, 7, 30, 9, tzinfo=UTC))

    assert (
        criterion(expired, PaperExecutionEligibilityCriterion.APPROVAL_TIME_VALID).code
        is PaperExecutionEligibilityFailureCode.APPROVAL_EXPIRED
    )
    assert (
        criterion(not_yet, PaperExecutionEligibilityCriterion.APPROVAL_TIME_VALID).code
        is PaperExecutionEligibilityFailureCode.APPROVAL_NOT_YET_VALID
    )


def test_missing_evaluation_time_is_indeterminate_when_expiry_required() -> None:
    result = evaluate(build_command(), evaluated_at=None)

    assert result.decision is PaperExecutionEligibilityDecision.INDETERMINATE
    assert (
        criterion(result, PaperExecutionEligibilityCriterion.APPROVAL_TIME_VALID).code
        is PaperExecutionEligibilityFailureCode.EVALUATION_TIME_REQUIRED
    )


def test_equivalent_timezones_produce_same_result_fingerprint() -> None:
    command = build_command()
    utc_result = evaluate(command, evaluated_at=datetime(2026, 7, 30, 11, tzinfo=UTC))
    offset_result = evaluate(
        command,
        evaluated_at=datetime(2026, 7, 30, 7, tzinfo=timezone(timedelta(hours=-4))),
    )

    assert utc_result.result_fingerprint == offset_result.result_fingerprint
    assert offset_result.evaluated_at == datetime(2026, 7, 30, 11, tzinfo=UTC)


def test_policy_snapshot_incompatibility_is_detected() -> None:
    snapshot = PaperExecutionPolicySnapshot(
        "paper-snapshot-v1",
        allowed_operations=(PaperExecutionOperation.CANCEL,),
    )
    result = evaluate(build_command(policy_snapshot=snapshot))

    assert result.decision is PaperExecutionEligibilityDecision.INELIGIBLE
    assert (
        criterion(
            result, PaperExecutionEligibilityCriterion.POLICY_SNAPSHOT_COMPATIBLE
        ).code
        is PaperExecutionEligibilityFailureCode.POLICY_SNAPSHOT_INCOMPATIBLE
    )


@pytest.mark.parametrize(
    ("field", "criterion_name", "code"),
    (
        (
            "require_external_market_capability",
            PaperExecutionEligibilityCriterion.EXTERNAL_MARKET_CAPABILITY_STATUS,
            PaperExecutionEligibilityFailureCode.MARKET_CAPABILITY_CLEARANCE_REQUIRED,
        ),
        (
            "require_external_emergency_stop_clearance",
            PaperExecutionEligibilityCriterion.EXTERNAL_EMERGENCY_STOP_STATUS,
            PaperExecutionEligibilityFailureCode.EMERGENCY_STOP_CLEARANCE_REQUIRED,
        ),
        (
            "require_external_risk_clearance",
            PaperExecutionEligibilityCriterion.EXTERNAL_RISK_STATUS,
            PaperExecutionEligibilityFailureCode.RISK_CLEARANCE_REQUIRED,
        ),
        (
            "require_external_account_clearance",
            PaperExecutionEligibilityCriterion.EXTERNAL_ACCOUNT_STATUS,
            PaperExecutionEligibilityFailureCode.ACCOUNT_CLEARANCE_REQUIRED,
        ),
    ),
)
def test_external_prerequisites_are_unresolved(
    field: str,
    criterion_name: PaperExecutionEligibilityCriterion,
    code: PaperExecutionEligibilityFailureCode,
) -> None:
    policy = PaperExecutionEligibilityPolicy("eligibility-v1", **{field: True})
    result = evaluate(build_command(), policy)
    item = criterion(result, criterion_name)

    assert result.decision is PaperExecutionEligibilityDecision.INDETERMINATE
    assert item.outcome is PaperExecutionEligibilityCriterionOutcome.UNRESOLVED
    assert item.code is code
    assert item.external_evidence_required is True


def test_failure_takes_precedence_over_unresolved_evidence() -> None:
    policy = PaperExecutionEligibilityPolicy(
        "eligibility-v1",
        allowed_operations=(PaperExecutionOperation.CANCEL,),
        require_external_market_capability=True,
    )
    result = evaluate(build_command(), policy)

    assert result.decision is PaperExecutionEligibilityDecision.INELIGIBLE
    assert result.failed_criterion_count >= 1
    assert result.unresolved_criterion_count >= 1


def test_criterion_ordering_and_repeatability_are_stable() -> None:
    command = build_command()
    first = evaluate(command)
    second = evaluate(command)

    assert first.result_fingerprint == second.result_fingerprint
    assert [item.criterion.value for item in first.criteria] == sorted(
        item.criterion.value for item in first.criteria
    )


def test_invalid_api_usage_raises_not_business_result() -> None:
    with pytest.raises(Exception):
        PaperExecutionEligibilityService().evaluate(object(), PaperExecutionEligibilityPolicy("v1"))  # type: ignore[arg-type]
