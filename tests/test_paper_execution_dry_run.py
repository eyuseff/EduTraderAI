"""Focused tests for deterministic Paper execution dry-run orchestration."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from volcanoes.application.execution import (
    PaperDryRunExecutor,
    PaperDryRunFailure,
    PaperDryRunFailureReason,
    PaperDryRunOutcomeKind,
    PaperDryRunRequest,
    PaperDryRunResult,
    PaperDryRunStep,
    PaperDryRunStepKind,
    PaperExecutionEffectMode,
)
from volcanoes.application.execution.contracts import (
    PaperExecutionApproval,
    PaperExecutionCommand,
    PaperExecutionContext,
    PaperExecutionInstrument,
    PaperExecutionIntent,
    PaperExecutionPolicySnapshot,
)
from volcanoes.application.execution.enums import (
    PaperExecutionApprovalKind,
    PaperExecutionOperation,
    PaperExecutionOrderType,
    PaperExecutionSide,
)
from volcanoes.application.execution.fingerprints import command_payload_fingerprint
from volcanoes.application.execution.identities import (
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionIdempotencyKey,
    PaperExecutionRevision,
)
from volcanoes.application.execution.lifecycle import (
    PaperExecutionLifecycle,
    PaperExecutionLifecycleState,
    PaperExecutionTransitionContext,
)
from volcanoes.application.execution.eligibility import (
    PaperExecutionEligibilityPolicy,
    PaperExecutionEligibilityService,
)

EVALUATED_AT = datetime(2026, 8, 4, 14, 30, tzinfo=UTC)


class CountingEligibilityService(PaperExecutionEligibilityService):
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        return super().evaluate(*args, **kwargs)


def ids(seed: str = "dry-run"):
    return (
        PaperExecutionAggregateId.from_seed(seed, "aggregate"),
        PaperExecutionCorrelationId.from_seed(seed, "correlation"),
    )


def intent(seed: str = "dry-run") -> PaperExecutionIntent:
    return PaperExecutionIntent(
        instrument=PaperExecutionInstrument(symbol="AAPL"),
        side=PaperExecutionSide.BUY,
        order_type=PaperExecutionOrderType.LIMIT,
        quantity=Decimal("1"),
        limit_price=Decimal("100"),
        strategy_reference=f"{seed}-strategy",
    )


def command(
    seed: str = "dry-run",
    *,
    approval_bound: str | None = None,
    approved_at: datetime = EVALUATED_AT - timedelta(minutes=5),
    expires_at: datetime | None = EVALUATED_AT + timedelta(minutes=5),
    expected_revision: int = 0,
) -> PaperExecutionCommand:
    aggregate_id, correlation_id = ids(seed)
    order_intent = intent(seed)
    bound = approval_bound or command_payload_fingerprint(order_intent.to_primitive())
    approval = PaperExecutionApproval(
        approval_kind=PaperExecutionApprovalKind.OPERATOR,
        approver_reference="operator-ref",
        approval_reference=f"{seed}-approval",
        bound_fingerprint=bound,
        approved_at=approved_at,
        expires_at=expires_at,
    )
    return PaperExecutionCommand(
        command_id=PaperExecutionCommandId.from_seed(seed, "command"),
        aggregate_id=aggregate_id,
        correlation_id=correlation_id,
        idempotency_key=PaperExecutionIdempotencyKey.from_seed(seed, "idempotency"),
        operation=PaperExecutionOperation.SUBMIT,
        expected_execution_revision=PaperExecutionRevision(expected_revision),
        approval=approval,
        policy_snapshot=PaperExecutionPolicySnapshot(
            policy_version="dry-run-policy",
            allowed_operations=(PaperExecutionOperation.SUBMIT,),
        ),
        context=PaperExecutionContext(
            aggregate_id=aggregate_id,
            correlation_id=correlation_id,
            source_component="dry-run-test",
            requested_at=EVALUATED_AT,
        ),
        intent=order_intent,
    )


def lifecycle_for(
    cmd: PaperExecutionCommand,
    state: PaperExecutionLifecycleState = PaperExecutionLifecycleState.CREATED,
    revision: int = 0,
) -> PaperExecutionLifecycle:
    return PaperExecutionLifecycle(
        aggregate_id=cmd.aggregate_id,
        state=state,
        revision=PaperExecutionRevision(revision),
        correlation_id=cmd.correlation_id,
        requested_quantity=Decimal("1"),
    )


def lifecycle_context(
    current: PaperExecutionLifecycle,
    **overrides: object,
) -> PaperExecutionTransitionContext:
    values: dict[str, Any] = {
        "expected_revision": current.revision,
        "approval_binding_valid": True,
        "approval_time_valid": True,
        "policy_compatible": True,
        "idempotency_reservation_confirmed": True,
        "emergency_stop_clearance": True,
        "external_prerequisites_satisfied": True,
        "requested_quantity": Decimal("1"),
    }
    values.update(overrides)
    return PaperExecutionTransitionContext(**values)


def policy(**overrides: object) -> PaperExecutionEligibilityPolicy:
    values: dict[str, Any] = {"policy_version": "dry-run-eligibility"}
    values.update(overrides)
    return PaperExecutionEligibilityPolicy(**values)


def request(
    seed: str = "dry-run",
    *,
    cmd: PaperExecutionCommand | None = None,
    initial_state: PaperExecutionLifecycleState = PaperExecutionLifecycleState.CREATED,
    initial_revision: int = 0,
    eligibility_policy: PaperExecutionEligibilityPolicy | None = None,
    context_overrides: dict[str, object] | None = None,
    prior_result: PaperDryRunResult | None = None,
) -> PaperDryRunRequest:
    cmd = cmd or command(seed, expected_revision=initial_revision)
    current = lifecycle_for(cmd, initial_state, initial_revision)
    return PaperDryRunRequest(
        command=cmd,
        eligibility_policy=eligibility_policy or policy(),
        evaluated_at=EVALUATED_AT,
        initial_lifecycle=current,
        lifecycle_context=lifecycle_context(current, **(context_overrides or {})),
        prior_result=prior_result,
    )


def run_success(seed: str = "dry-run") -> PaperDryRunResult:
    return PaperDryRunExecutor().execute(request(seed))


def test_effect_mode_contains_only_dry_run() -> None:
    assert tuple(PaperExecutionEffectMode) == (PaperExecutionEffectMode.DRY_RUN,)


@pytest.mark.parametrize("step_kind", tuple(PaperDryRunStepKind))
def test_step_kind_values_are_stable(step_kind: PaperDryRunStepKind) -> None:
    assert PaperDryRunStepKind(step_kind.value) is step_kind


@pytest.mark.parametrize("reason", tuple(PaperDryRunFailureReason))
def test_failure_reason_values_are_stable(reason: PaperDryRunFailureReason) -> None:
    assert PaperDryRunFailureReason(reason.value) is reason


@pytest.mark.parametrize(
    "forbidden",
    ("EXECUTE", "BROKER", "LIVE", "PRODUCTION", "REAL", "ACTIVE"),
)
def test_effect_mode_defines_no_execute_capable_values(forbidden: str) -> None:
    assert forbidden not in PaperExecutionEffectMode.__members__


@pytest.mark.parametrize(
    "outcome",
    (
        PaperDryRunOutcomeKind.WOULD_DISPATCH,
        PaperDryRunOutcomeKind.WOULD_REJECT,
        PaperDryRunOutcomeKind.WOULD_REQUIRE_EXTERNAL_EVIDENCE,
        PaperDryRunOutcomeKind.WOULD_REQUIRE_RECONCILIATION,
        PaperDryRunOutcomeKind.NO_ACTION_REPLAY,
    ),
)
def test_outcome_values_are_prefixed_or_no_action(
    outcome: PaperDryRunOutcomeKind,
) -> None:
    assert (
        outcome.value.startswith("WOULD_")
        or outcome is PaperDryRunOutcomeKind.NO_ACTION_REPLAY
    )


@pytest.mark.parametrize(
    "broker_truth",
    ("SUBMITTED", "ACKNOWLEDGED", "FILLED", "CANCELLED", "REPLACED"),
)
def test_dry_run_outcomes_do_not_claim_broker_truth(broker_truth: str) -> None:
    assert broker_truth not in PaperDryRunOutcomeKind.__members__


def test_request_is_immutable() -> None:
    dry_request = request()
    with pytest.raises(FrozenInstanceError):
        dry_request.effect_mode = PaperExecutionEffectMode.DRY_RUN  # type: ignore[misc]


def test_step_is_immutable() -> None:
    step = PaperDryRunStep(1, PaperDryRunStepKind.REQUEST_VALIDATED, "OK")
    with pytest.raises(FrozenInstanceError):
        step.reason_code = "NOPE"  # type: ignore[misc]


@pytest.mark.parametrize("bad_sequence", (0, -1, True))
def test_step_rejects_invalid_sequence(bad_sequence: int | bool) -> None:
    with pytest.raises(Exception):
        PaperDryRunStep(bad_sequence, PaperDryRunStepKind.REQUEST_VALIDATED, "BAD")  # type: ignore[arg-type]


@pytest.mark.parametrize("unsafe", ("API_KEY", "SECRET", "PASSWORD", "ACCESS_TOKEN"))
def test_step_rejects_sensitive_reason_codes(unsafe: str) -> None:
    with pytest.raises(Exception):
        PaperDryRunStep(1, PaperDryRunStepKind.REQUEST_VALIDATED, unsafe)


def test_receipt_is_immutable() -> None:
    result = run_success()
    assert result.receipt is not None
    with pytest.raises(FrozenInstanceError):
        result.receipt.action_executed = True  # type: ignore[misc]


def test_failure_is_immutable() -> None:
    result = PaperDryRunExecutor().execute(
        request(
            eligibility_policy=policy(
                allowed_operations=(PaperExecutionOperation.CANCEL,)
            )
        )
    )
    assert result.failure is not None
    with pytest.raises(FrozenInstanceError):
        result.failure.safe_message_code = "NOPE"  # type: ignore[misc]


@pytest.mark.parametrize("unsafe", ("API_KEY", "SECRET", "PASSWORD", "ACCESS_TOKEN"))
def test_failure_rejects_sensitive_message_codes(unsafe: str) -> None:
    dry_request = request()
    with pytest.raises(Exception):
        PaperDryRunFailure(
            request_fingerprint=dry_request.request_fingerprint,
            reason=PaperDryRunFailureReason.INVALID_REQUEST,
            safe_message_code=unsafe,
            command_id=dry_request.command.command_id,
            aggregate_id=dry_request.command.aggregate_id,
            correlation_id=dry_request.command.correlation_id,
        )


def test_result_is_immutable() -> None:
    result = run_success()
    with pytest.raises(FrozenInstanceError):
        result.action_executed = True  # type: ignore[misc]


@pytest.mark.parametrize(
    "contract",
    (
        lambda: request(),
        lambda: PaperDryRunStep(1, PaperDryRunStepKind.REQUEST_VALIDATED, "SAFE"),
        lambda: run_success().receipt,
        lambda: PaperDryRunExecutor()
        .execute(
            request(
                eligibility_policy=policy(
                    allowed_operations=(PaperExecutionOperation.CANCEL,)
                )
            )
        )
        .failure,
        lambda: run_success(),
    ),
)
def test_public_contract_repr_excludes_secret_terms(contract) -> None:  # type: ignore[no-untyped-def]
    text = repr(contract()).lower()
    assert "secret" not in text
    assert "api_key" not in text
    assert "password" not in text
    assert "authorization" not in text


def test_valid_submit_returns_would_dispatch() -> None:
    result = run_success()
    assert result.outcome_kind is PaperDryRunOutcomeKind.WOULD_DISPATCH
    assert (
        result.final_lifecycle.state is PaperExecutionLifecycleState.READY_FOR_DISPATCH
    )
    assert result.lifecycle_transition_ids == (
        "PX-TRN-002",
        "PX-TRN-005",
        "PX-TRN-006",
        "PX-TRN-007",
    )
    assert result.initial_revision == PaperExecutionRevision(0)
    assert result.final_revision == PaperExecutionRevision(4)


def test_eligibility_invoked_once_for_non_replayed_request() -> None:
    service = CountingEligibilityService()
    result = PaperDryRunExecutor(service).execute(request())
    assert result.outcome_kind is PaperDryRunOutcomeKind.WOULD_DISPATCH
    assert service.calls == 1


def test_successful_dry_run_has_no_broker_truth_state() -> None:
    result = run_success()
    forbidden = {
        PaperExecutionLifecycleState.DISPATCHED,
        PaperExecutionLifecycleState.BROKER_ACKNOWLEDGED,
        PaperExecutionLifecycleState.PARTIALLY_FILLED,
        PaperExecutionLifecycleState.FILLED,
        PaperExecutionLifecycleState.CANCELLED,
        PaperExecutionLifecycleState.REPLACED,
        PaperExecutionLifecycleState.BROKER_REJECTED,
    }
    assert result.final_lifecycle.state not in forbidden
    assert result.final_lifecycle.broker_order_reference is None


@pytest.mark.parametrize(
    "flag",
    (
        "execution_authorized",
        "action_executed",
        "broker_accessed",
        "simulator_accessed",
        "persistence_accessed",
        "runtime_changed",
        "live_authorized",
    ),
)
def test_successful_result_safety_invariants_are_false(flag: str) -> None:
    assert getattr(run_success(), flag) is False


def test_successful_receipt_is_dry_run_only() -> None:
    result = run_success()
    assert result.receipt is not None
    assert result.receipt.receipt_fingerprint.startswith("pdt-")
    assert result.receipt.broker_reference is None
    assert result.receipt.action_executed is False
    assert result.receipt.would_dispatch is True


@pytest.mark.parametrize(
    "seed",
    ("alpha", "bravo", "charlie", "delta", "echo"),
)
def test_successful_dry_run_path_is_stable_across_distinct_identities(
    seed: str,
) -> None:
    result = run_success(seed)
    assert result.outcome_kind is PaperDryRunOutcomeKind.WOULD_DISPATCH
    assert (
        result.final_lifecycle.state is PaperExecutionLifecycleState.READY_FOR_DISPATCH
    )
    assert result.final_revision.value == 4


@pytest.mark.parametrize(
    "step_index",
    (2, 3, 4, 5),
)
def test_lifecycle_steps_increment_revision_exactly_once(step_index: int) -> None:
    result = run_success()
    step = result.steps[step_index]
    assert step.previous_revision is not None
    assert step.next_revision is not None
    assert step.next_revision.value == step.previous_revision.value + 1


def test_step_order_is_stable_for_success() -> None:
    result = run_success()
    assert tuple(step.sequence for step in result.steps) == tuple(range(1, 8))
    assert tuple(step.kind for step in result.steps) == (
        PaperDryRunStepKind.REQUEST_VALIDATED,
        PaperDryRunStepKind.ELIGIBILITY_EVALUATED,
        PaperDryRunStepKind.LIFECYCLE_ELIGIBILITY_RECORDED,
        PaperDryRunStepKind.APPROVAL_RECORDED,
        PaperDryRunStepKind.IDEMPOTENCY_RESERVATION_SIMULATED,
        PaperDryRunStepKind.READY_FOR_DISPATCH_REACHED,
        PaperDryRunStepKind.WOULD_DISPATCH,
    )


@pytest.mark.parametrize(
    "bad_policy",
    (
        policy(allowed_operations=(PaperExecutionOperation.CANCEL,)),
        policy(require_initial_submit_revision=True),
    ),
)
def test_ineligible_returns_would_reject(
    bad_policy: PaperExecutionEligibilityPolicy,
) -> None:
    cmd = command(expected_revision=1)
    result = PaperDryRunExecutor().execute(
        request(cmd=cmd, initial_revision=1, eligibility_policy=bad_policy)
    )
    assert result.outcome_kind is PaperDryRunOutcomeKind.WOULD_REJECT
    assert result.failure is not None
    assert result.failure.reason is PaperDryRunFailureReason.COMMAND_INELIGIBLE
    assert result.action_executed is False


def test_ineligible_records_terminal_state_when_lifecycle_allows_it() -> None:
    result = PaperDryRunExecutor().execute(
        request(
            initial_state=PaperExecutionLifecycleState.ELIGIBILITY_EVALUATED,
            eligibility_policy=policy(
                allowed_operations=(PaperExecutionOperation.CANCEL,)
            ),
        )
    )
    assert result.final_lifecycle.state is PaperExecutionLifecycleState.INELIGIBLE
    assert result.lifecycle_transition_ids == ("PX-TRN-003",)


@pytest.mark.parametrize(
    "initial_state",
    (
        PaperExecutionLifecycleState.CREATED,
        PaperExecutionLifecycleState.APPROVAL_CONFIRMED,
        PaperExecutionLifecycleState.READY_FOR_DISPATCH,
    ),
)
def test_ineligible_without_accepted_terminal_record_does_not_force_lifecycle(
    initial_state: PaperExecutionLifecycleState,
) -> None:
    result = PaperDryRunExecutor().execute(
        request(
            initial_state=initial_state,
            eligibility_policy=policy(
                allowed_operations=(PaperExecutionOperation.CANCEL,)
            ),
        )
    )
    assert result.outcome_kind is PaperDryRunOutcomeKind.WOULD_REJECT
    assert result.final_lifecycle.state is initial_state
    assert result.lifecycle_transition_ids == ()


@pytest.mark.parametrize(
    "external_flag",
    (
        "require_external_market_capability",
        "require_external_emergency_stop_clearance",
        "require_external_risk_clearance",
        "require_external_account_clearance",
    ),
)
def test_indeterminate_returns_external_evidence_required(external_flag: str) -> None:
    result = PaperDryRunExecutor().execute(
        request(eligibility_policy=policy(**{external_flag: True}))
    )
    assert result.outcome_kind is PaperDryRunOutcomeKind.WOULD_REQUIRE_EXTERNAL_EVIDENCE
    assert result.external_evidence_required is True
    assert result.failure is not None
    assert result.failure.reason is PaperDryRunFailureReason.EXTERNAL_EVIDENCE_REQUIRED
    assert result.final_lifecycle.state is PaperExecutionLifecycleState.CREATED


@pytest.mark.parametrize(
    ("cmd", "reason_code"),
    (
        (
            command(approval_bound=command_payload_fingerprint(("wrong",))),
            "COMMAND_INELIGIBLE",
        ),
        (
            command(approved_at=EVALUATED_AT + timedelta(minutes=1)),
            "COMMAND_INELIGIBLE",
        ),
        (
            command(expires_at=EVALUATED_AT),
            "COMMAND_INELIGIBLE",
        ),
    ),
)
def test_invalid_approval_returns_rejection(
    cmd: PaperExecutionCommand,
    reason_code: str,
) -> None:
    result = PaperDryRunExecutor().execute(request(cmd=cmd))
    assert result.outcome_kind is PaperDryRunOutcomeKind.WOULD_REJECT
    assert result.failure is not None
    assert result.failure.safe_message_code == reason_code


@pytest.mark.parametrize(
    "approval_time",
    (
        EVALUATED_AT - timedelta(minutes=10),
        EVALUATED_AT - timedelta(seconds=1),
        EVALUATED_AT,
    ),
)
def test_valid_approval_times_are_accepted(approval_time: datetime) -> None:
    result = PaperDryRunExecutor().execute(
        request(cmd=command(approved_at=approval_time))
    )
    assert result.outcome_kind is PaperDryRunOutcomeKind.WOULD_DISPATCH


def test_executor_never_creates_approval() -> None:
    cmd = command()
    result = PaperDryRunExecutor().execute(request(cmd=cmd))
    assert result.eligibility_result is not None
    assert cmd.approval.approval_reference == "dry-run-approval"


@pytest.mark.parametrize(
    ("context_overrides", "expected"),
    (
        (
            {"idempotency_reservation_confirmed": False},
            PaperDryRunFailureReason.EXTERNAL_EVIDENCE_REQUIRED,
        ),
        (
            {"external_prerequisites_satisfied": False},
            PaperDryRunFailureReason.EXTERNAL_EVIDENCE_REQUIRED,
        ),
        (
            {"emergency_stop_clearance": False},
            PaperDryRunFailureReason.EXTERNAL_EVIDENCE_REQUIRED,
        ),
    ),
)
def test_missing_simulated_reservation_or_prerequisites_fail_safe(
    context_overrides: dict[str, object],
    expected: PaperDryRunFailureReason,
) -> None:
    result = PaperDryRunExecutor().execute(request(context_overrides=context_overrides))
    assert result.outcome_kind is PaperDryRunOutcomeKind.WOULD_REQUIRE_EXTERNAL_EVIDENCE
    assert result.failure is not None
    assert result.failure.reason is expected
    assert (
        result.final_lifecycle.state
        is not PaperExecutionLifecycleState.READY_FOR_DISPATCH
    )


def test_replay_does_not_invoke_eligibility_again_or_advance_revision() -> None:
    prior = run_success()
    service = CountingEligibilityService()
    replay_request = request(prior_result=prior)
    result = PaperDryRunExecutor(service).execute(replay_request)
    assert result.outcome_kind is PaperDryRunOutcomeKind.NO_ACTION_REPLAY
    assert result.replayed is True
    assert service.calls == 0
    assert result.final_revision == replay_request.initial_lifecycle.revision
    assert tuple(step.kind for step in result.steps) == (PaperDryRunStepKind.REPLAYED,)


@pytest.mark.parametrize(
    "seed",
    ("replay-a", "replay-b", "replay-c"),
)
def test_exact_replay_is_neutral_across_identities(seed: str) -> None:
    prior = run_success(seed)
    result = PaperDryRunExecutor(CountingEligibilityService()).execute(
        request(seed, prior_result=prior)
    )
    assert result.outcome_kind is PaperDryRunOutcomeKind.NO_ACTION_REPLAY
    assert result.lifecycle_transition_ids == ()
    assert result.final_revision == PaperExecutionRevision(0)


def test_prior_same_command_with_different_fingerprint_conflicts_before_eligibility() -> (
    None
):
    prior = run_success()
    service = CountingEligibilityService()
    changed = request(
        cmd=command(approved_at=EVALUATED_AT - timedelta(minutes=10)),
        prior_result=prior,
    )
    result = PaperDryRunExecutor(service).execute(changed)
    assert result.outcome_kind is PaperDryRunOutcomeKind.WOULD_REJECT
    assert result.failure is not None
    assert result.failure.reason is PaperDryRunFailureReason.COMMAND_CONFLICT
    assert service.calls == 0


def test_equivalent_separate_request_has_same_logical_outcome() -> None:
    first = run_success("same")
    second = run_success("same")
    assert first.outcome_kind is second.outcome_kind
    assert first.lifecycle_transition_ids == second.lifecycle_transition_ids
    assert first.final_lifecycle.state is second.final_lifecycle.state
    assert first.result_fingerprint == second.result_fingerprint


@pytest.mark.parametrize(
    "state",
    (
        PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
        PaperExecutionLifecycleState.RECONCILIATION_REQUIRED,
    ),
)
def test_reconciliation_states_do_not_query_eligibility_or_repair(
    state: PaperExecutionLifecycleState,
) -> None:
    service = CountingEligibilityService()
    result = PaperDryRunExecutor(service).execute(request(initial_state=state))
    assert result.outcome_kind is PaperDryRunOutcomeKind.WOULD_REQUIRE_RECONCILIATION
    assert result.reconciliation_required is True
    assert result.final_lifecycle.state is state
    assert service.calls == 0


@pytest.mark.parametrize(
    "initial_state",
    (
        PaperExecutionLifecycleState.DISPATCH_PENDING,
        PaperExecutionLifecycleState.DISPATCHED,
        PaperExecutionLifecycleState.BROKER_ACKNOWLEDGED,
        PaperExecutionLifecycleState.PARTIALLY_FILLED,
        PaperExecutionLifecycleState.FILLED,
        PaperExecutionLifecycleState.CANCELLED,
        PaperExecutionLifecycleState.REPLACED,
        PaperExecutionLifecycleState.BROKER_REJECTED,
    ),
)
def test_dry_run_does_not_advance_existing_broker_truth_states(
    initial_state: PaperExecutionLifecycleState,
) -> None:
    result = PaperDryRunExecutor().execute(request(initial_state=initial_state))
    assert result.outcome_kind is PaperDryRunOutcomeKind.WOULD_REJECT
    assert result.final_lifecycle.state is initial_state
    assert result.action_executed is False


def test_stale_revision_safe_failure_is_neutral() -> None:
    result = PaperDryRunExecutor().execute(
        request(context_overrides={"expected_revision": PaperExecutionRevision(99)})
    )
    assert result.outcome_kind is PaperDryRunOutcomeKind.WOULD_REJECT
    assert result.final_revision == PaperExecutionRevision(0)
    assert result.failure is not None
    assert result.failure.reason is PaperDryRunFailureReason.STALE_REVISION


def test_result_fingerprint_is_deterministic() -> None:
    assert run_success().result_fingerprint == run_success().result_fingerprint


def test_request_fingerprint_changes_when_material_input_changes() -> None:
    assert request("one").request_fingerprint != request("two").request_fingerprint


def test_timezone_equivalent_timestamp_has_same_result() -> None:
    base = request()
    shifted_time = EVALUATED_AT.astimezone(timezone(timedelta(hours=-4)))
    shifted = PaperDryRunRequest(
        command=base.command,
        eligibility_policy=base.eligibility_policy,
        evaluated_at=shifted_time,
        initial_lifecycle=base.initial_lifecycle,
        lifecycle_context=base.lifecycle_context,
    )
    assert (
        PaperDryRunExecutor().execute(base).result_fingerprint
        == PaperDryRunExecutor().execute(shifted).result_fingerprint
    )


@pytest.mark.parametrize(
    "tzinfo",
    (
        timezone(timedelta(hours=-8)),
        timezone(timedelta(hours=-4)),
        timezone(timedelta(hours=3)),
        timezone(timedelta(hours=9)),
    ),
)
def test_timezone_equivalent_request_fingerprint_is_stable(tzinfo: timezone) -> None:
    base = request()
    shifted = PaperDryRunRequest(
        command=base.command,
        eligibility_policy=base.eligibility_policy,
        evaluated_at=EVALUATED_AT.astimezone(tzinfo),
        initial_lifecycle=base.initial_lifecycle,
        lifecycle_context=base.lifecycle_context,
    )
    assert base.request_fingerprint == shifted.request_fingerprint


def test_golden_fingerprint_prefixes() -> None:
    result = run_success()
    assert request().request_fingerprint.startswith("pdr-")
    assert result.result_fingerprint.startswith("pdo-")
    assert result.receipt is not None
    assert result.receipt.receipt_fingerprint.startswith("pdt-")
    rejected = PaperDryRunExecutor().execute(
        request(
            eligibility_policy=policy(
                allowed_operations=(PaperExecutionOperation.CANCEL,)
            )
        )
    )
    assert rejected.failure is not None
    assert rejected.failure.failure_fingerprint.startswith("pdf-")


@pytest.mark.parametrize(
    "forbidden_text",
    ("submit_order", "BROKER_ACKNOWLEDGED", "FILL_OBSERVED", "CANCEL_CONFIRMED"),
)
def test_successful_result_makes_no_broker_truth_claims(forbidden_text: str) -> None:
    assert forbidden_text not in str(run_success().to_primitive())


@pytest.mark.parametrize(
    "outcome",
    tuple(PaperDryRunOutcomeKind),
)
def test_all_outcomes_preserve_safety_boolean_defaults(
    outcome: PaperDryRunOutcomeKind,
) -> None:
    result = run_success()
    forced = replace(result, outcome_kind=outcome)
    assert forced.execution_authorized is False
    assert forced.action_executed is False
    assert forced.broker_accessed is False
    assert forced.simulator_accessed is False
    assert forced.persistence_accessed is False
    assert forced.runtime_changed is False
    assert forced.live_authorized is False


@pytest.mark.parametrize(
    "flag",
    (
        "execution_authorized",
        "action_executed",
        "broker_accessed",
        "simulator_accessed",
        "persistence_accessed",
        "runtime_changed",
        "live_authorized",
    ),
)
def test_safety_booleans_are_not_caller_configurable(flag: str) -> None:
    result = replace(run_success(), **cast(Any, {flag: True}))
    assert getattr(result, flag) is False


def test_inputs_remain_unchanged_after_execution() -> None:
    dry_request = request()
    before = dry_request.to_primitive()
    PaperDryRunExecutor().execute(dry_request)
    assert dry_request.to_primitive() == before


def test_contract_serialization_is_deterministic() -> None:
    result = run_success()
    assert result.to_primitive() == run_success().to_primitive()


def test_no_repository_state_file_is_referenced_by_dry_run_sources() -> None:
    package = Path("volcanoes/application/execution/dry_run")
    source = "\n".join(path.read_text() for path in package.rglob("*.py"))
    assert "state/simulated_broker.json" not in source
    assert "simulated_broker" not in source


@pytest.mark.parametrize(
    "token",
    (
        "open(",
        "write_text",
        "os.environ",
        "getenv",
        "datetime.now",
        "time.time",
        "random",
        "import requests",
        "from requests",
        "import http",
        "from http",
        "socket",
        "subprocess",
        "EventPublisher",
        "OperationalMetrics",
        "TradingClient",
        "BrokerAdapter",
    ),
)
def test_dry_run_sources_have_no_runtime_effect_tokens(token: str) -> None:
    package = Path("volcanoes/application/execution/dry_run")
    source = "\n".join(path.read_text() for path in package.rglob("*.py"))
    assert token not in source


@pytest.mark.parametrize(
    "forbidden_name",
    (
        "PaperBrokerPort",
        "PaperExecutionRepository",
        "PaperExecutionPersistence",
        "BrokerAdapter",
        "EventPublisher",
        "OperationalMetrics",
        "TradingClient",
        "RuntimeActionRequest",
    ),
)
def test_dry_run_sources_define_no_runtime_ports_or_adapters(
    forbidden_name: str,
) -> None:
    package = Path("volcanoes/application/execution/dry_run")
    source = "\n".join(path.read_text() for path in package.rglob("*.py"))
    assert forbidden_name not in source
