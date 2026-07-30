from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tests.test_paper_execution_eligibility_service import (
    build_command,
    criterion,
    evaluate,
)
from volcanoes.application.execution import (
    PaperExecutionEligibilityCriterion,
    PaperExecutionEligibilityCriterionOutcome,
    PaperExecutionEligibilityDecision,
    PaperExecutionEligibilityFailureCode,
    PaperExecutionEligibilityPolicy,
    PaperExecutionOperation,
    PaperExecutionPolicySnapshot,
    PaperExecutionRevision,
)
from volcanoes.application.execution.fingerprints import command_payload_fingerprint


@pytest.mark.parametrize("criterion_name", tuple(PaperExecutionEligibilityCriterion))
def test_every_defined_criterion_is_reported_once(
    criterion_name: PaperExecutionEligibilityCriterion,
) -> None:
    result = evaluate(build_command())

    assert sum(item.criterion is criterion_name for item in result.criteria) == 1


@pytest.mark.parametrize(
    "operation",
    (
        PaperExecutionOperation.SUBMIT,
        PaperExecutionOperation.CANCEL,
        PaperExecutionOperation.REPLACE,
    ),
)
@pytest.mark.parametrize(
    "allowed",
    (
        (PaperExecutionOperation.SUBMIT,),
        (PaperExecutionOperation.CANCEL,),
        (PaperExecutionOperation.REPLACE,),
        (
            PaperExecutionOperation.SUBMIT,
            PaperExecutionOperation.CANCEL,
            PaperExecutionOperation.REPLACE,
        ),
    ),
)
def test_operation_subset_policy_is_deterministic(
    operation: PaperExecutionOperation,
    allowed: tuple[PaperExecutionOperation, ...],
) -> None:
    revision = (
        PaperExecutionRevision.initial()
        if operation is PaperExecutionOperation.SUBMIT
        else PaperExecutionRevision(1)
    )
    result = evaluate(
        build_command(operation=operation, revision=revision),
        PaperExecutionEligibilityPolicy("eligibility-v1", allowed_operations=allowed),
    )
    operation_result = criterion(
        result,
        PaperExecutionEligibilityCriterion.OPERATION_ALLOWED,
    )

    assert operation_result.passed is (operation in allowed)


@pytest.mark.parametrize(
    ("snapshot", "expected_pass"),
    (
        (
            PaperExecutionPolicySnapshot(
                "snapshot",
                allowed_operations=(PaperExecutionOperation.SUBMIT,),
            ),
            True,
        ),
        (
            PaperExecutionPolicySnapshot(
                "snapshot",
                allowed_operations=(PaperExecutionOperation.CANCEL,),
            ),
            False,
        ),
        (
            PaperExecutionPolicySnapshot(
                "snapshot",
                allowed_operations=(PaperExecutionOperation.SUBMIT,),
                paper_only_required=False,
            ),
            False,
        ),
        (
            PaperExecutionPolicySnapshot(
                "snapshot",
                allowed_operations=(PaperExecutionOperation.SUBMIT,),
                explicit_approval_required=False,
            ),
            False,
        ),
        (
            PaperExecutionPolicySnapshot(
                "snapshot",
                allowed_operations=(PaperExecutionOperation.SUBMIT,),
                execution_revision_required=False,
            ),
            False,
        ),
        (
            PaperExecutionPolicySnapshot(
                "snapshot",
                allowed_operations=(PaperExecutionOperation.SUBMIT,),
                deterministic_idempotency_required=False,
            ),
            False,
        ),
    ),
)
def test_policy_snapshot_compatibility_matrix(
    snapshot: PaperExecutionPolicySnapshot,
    expected_pass: bool,
) -> None:
    result = evaluate(build_command(policy_snapshot=snapshot))

    assert (
        criterion(
            result,
            PaperExecutionEligibilityCriterion.POLICY_SNAPSHOT_COMPATIBLE,
        ).passed
        is expected_pass
    )


@pytest.mark.parametrize(
    ("operation", "bound_factory"),
    (
        (
            PaperExecutionOperation.SUBMIT,
            lambda command: command_payload_fingerprint(command.intent.to_primitive()),
        ),
        (
            PaperExecutionOperation.CANCEL,
            lambda command: command_payload_fingerprint(
                command.aggregate_id.to_primitive()
            ),
        ),
        (
            PaperExecutionOperation.REPLACE,
            lambda command: command_payload_fingerprint(
                command.replacement_intent.to_primitive()
            ),
        ),
    ),
)
def test_approval_binding_targets_by_operation(operation, bound_factory) -> None:
    revision = (
        PaperExecutionRevision.initial()
        if operation is PaperExecutionOperation.SUBMIT
        else PaperExecutionRevision(1)
    )
    initial = build_command(operation=operation, revision=revision)
    result = evaluate(
        build_command(
            operation=operation,
            revision=revision,
            approval_bound=bound_factory(initial),
        )
    )

    assert criterion(
        result,
        PaperExecutionEligibilityCriterion.APPROVAL_BINDING_VALID,
    ).passed


@pytest.mark.parametrize(
    ("evaluated_at", "outcome"),
    (
        (
            datetime(2026, 7, 30, 9, 59, 59, tzinfo=UTC),
            PaperExecutionEligibilityCriterionOutcome.FAIL,
        ),
        (
            datetime(2026, 7, 30, 10, 0, 0, tzinfo=UTC),
            PaperExecutionEligibilityCriterionOutcome.PASS,
        ),
        (
            datetime(2026, 7, 30, 11, 59, 59, tzinfo=UTC),
            PaperExecutionEligibilityCriterionOutcome.PASS,
        ),
        (
            datetime(2026, 7, 30, 12, 0, 0, tzinfo=UTC),
            PaperExecutionEligibilityCriterionOutcome.FAIL,
        ),
    ),
)
def test_approval_time_boundary_matrix(
    evaluated_at: datetime,
    outcome: PaperExecutionEligibilityCriterionOutcome,
) -> None:
    result = evaluate(build_command(), evaluated_at=evaluated_at)

    assert (
        criterion(
            result, PaperExecutionEligibilityCriterion.APPROVAL_TIME_VALID
        ).outcome
        is outcome
    )


@pytest.mark.parametrize(
    "field",
    (
        "require_payload_fingerprint_consistency",
        "require_context_identity_consistency",
        "require_aggregate_identity_consistency",
        "require_correlation_identity_consistency",
        "require_policy_snapshot_compatibility",
        "require_supported_intent",
        "require_initial_submit_revision",
        "require_unexpired_approval",
        "require_approval_binding",
    ),
)
def test_optional_internal_checks_can_be_disabled_deterministically(field: str) -> None:
    policy = PaperExecutionEligibilityPolicy("eligibility-v1", **{field: False})
    result = evaluate(build_command(), policy)

    assert result.decision is PaperExecutionEligibilityDecision.ELIGIBLE


@pytest.mark.parametrize(
    "external_field",
    (
        "require_external_market_capability",
        "require_external_emergency_stop_clearance",
        "require_external_risk_clearance",
        "require_external_account_clearance",
    ),
)
def test_each_external_requirement_sets_exactly_one_unresolved_criterion(
    external_field: str,
) -> None:
    result = evaluate(
        build_command(),
        PaperExecutionEligibilityPolicy("eligibility-v1", **{external_field: True}),
    )

    assert result.decision is PaperExecutionEligibilityDecision.INDETERMINATE
    assert result.unresolved_criterion_count == 1


@pytest.mark.parametrize(
    "public_type",
    (PaperExecutionEligibilityPolicy,),
)
def test_policy_public_types_have_no_behavior_methods(public_type: type) -> None:
    prohibited = {
        "execute",
        "submit",
        "dispatch",
        "authorize",
        "persist",
        "reserve",
        "retry",
        "reconcile",
    }

    assert prohibited.isdisjoint(dir(public_type))


@pytest.mark.parametrize(
    ("field", "criterion_name"),
    (
        (
            "require_external_market_capability",
            PaperExecutionEligibilityCriterion.EXTERNAL_MARKET_CAPABILITY_STATUS,
        ),
        (
            "require_external_emergency_stop_clearance",
            PaperExecutionEligibilityCriterion.EXTERNAL_EMERGENCY_STOP_STATUS,
        ),
        (
            "require_external_risk_clearance",
            PaperExecutionEligibilityCriterion.EXTERNAL_RISK_STATUS,
        ),
        (
            "require_external_account_clearance",
            PaperExecutionEligibilityCriterion.EXTERNAL_ACCOUNT_STATUS,
        ),
    ),
)
def test_external_requirement_mapping_is_stable(
    field: str,
    criterion_name: PaperExecutionEligibilityCriterion,
) -> None:
    result = evaluate(
        build_command(),
        PaperExecutionEligibilityPolicy("eligibility-v1", **{field: True}),
    )

    mapped = criterion(result, criterion_name)

    assert mapped.outcome is PaperExecutionEligibilityCriterionOutcome.UNRESOLVED
    assert mapped.external_evidence_required is True
    assert mapped.severity.value == "UNRESOLVED"


@pytest.mark.parametrize(
    ("policy_kwargs", "command_kwargs", "expected_code"),
    (
        (
            {"allowed_operations": (PaperExecutionOperation.CANCEL,)},
            {},
            PaperExecutionEligibilityFailureCode.OPERATION_NOT_ALLOWED,
        ),
        (
            {},
            {"revision": PaperExecutionRevision(2)},
            PaperExecutionEligibilityFailureCode.INITIAL_SUBMIT_REVISION_REQUIRED,
        ),
        (
            {"require_idempotency_key_consistency": True},
            {},
            PaperExecutionEligibilityFailureCode.IDEMPOTENCY_KEY_UNVERIFIABLE,
        ),
    ),
)
def test_decision_precedence_matrix(
    policy_kwargs: dict[str, object],
    command_kwargs: dict[str, object],
    expected_code: PaperExecutionEligibilityFailureCode,
) -> None:
    result = evaluate(
        build_command(**command_kwargs),
        PaperExecutionEligibilityPolicy("eligibility-v1", **policy_kwargs),
    )

    codes = {item.code for item in result.criteria}

    assert expected_code in codes
    if any(
        item.outcome is PaperExecutionEligibilityCriterionOutcome.FAIL
        for item in result.criteria
    ):
        assert result.decision is PaperExecutionEligibilityDecision.INELIGIBLE


@pytest.mark.parametrize(
    "code",
    tuple(PaperExecutionEligibilityFailureCode),
)
def test_failure_codes_are_stable_safe_tokens(
    code: PaperExecutionEligibilityFailureCode,
) -> None:
    assert code.value == code.name
    assert code.value.isupper()
    assert " " not in code.value


@pytest.mark.parametrize(
    "criterion_name",
    tuple(PaperExecutionEligibilityCriterion),
)
def test_criterion_messages_are_safe_and_stable(
    criterion_name: PaperExecutionEligibilityCriterion,
) -> None:
    result = evaluate(build_command())
    message = criterion(result, criterion_name).safe_message

    assert message
    assert "object at 0x" not in message
    assert "API_KEY" not in message
    assert "SECRET" not in message


@pytest.mark.parametrize(
    "field",
    (
        "require_paper_mode",
        "require_explicit_approval",
        "require_approval_binding",
        "require_unexpired_approval",
        "require_policy_snapshot_compatibility",
        "require_expected_revision",
        "require_initial_submit_revision",
        "require_idempotency_key",
        "require_idempotency_key_consistency",
        "require_command_identity_consistency",
        "require_payload_fingerprint_consistency",
        "require_context_identity_consistency",
        "require_aggregate_identity_consistency",
        "require_correlation_identity_consistency",
        "require_supported_intent",
        "require_external_market_capability",
        "require_external_emergency_stop_clearance",
        "require_external_risk_clearance",
        "require_external_account_clearance",
    ),
)
def test_policy_boolean_fields_serialize_as_booleans(field: str) -> None:
    primitive = PaperExecutionEligibilityPolicy("eligibility-v1").to_primitive()

    assert isinstance(primitive[field], bool)


@pytest.mark.parametrize(
    "decision",
    tuple(PaperExecutionEligibilityDecision),
)
def test_decision_tokens_are_stable(
    decision: PaperExecutionEligibilityDecision,
) -> None:
    assert decision.value == decision.name
    assert decision.value in {"ELIGIBLE", "INELIGIBLE", "INDETERMINATE"}
