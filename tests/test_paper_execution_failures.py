from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from volcanoes.application.execution import (
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionFailure,
    PaperExecutionFailureKind,
    PaperExecutionFailureSeverity,
    PaperExecutionInvariantError,
)


def failure(
    kind: PaperExecutionFailureKind = PaperExecutionFailureKind.OUTCOME_UNKNOWN,
) -> PaperExecutionFailure:
    return PaperExecutionFailure(
        failure_kind=kind,
        severity=PaperExecutionFailureSeverity.ERROR,
        code=kind.value,
        safe_message="Safe operator-facing explanation.",
        retryable=False,
        reconciliation_required=kind is PaperExecutionFailureKind.OUTCOME_UNKNOWN,
        operator_action_required=True,
        terminal=False,
        authority_impacting=True,
        command_id=PaperExecutionCommandId.from_seed("command"),
        aggregate_id=PaperExecutionAggregateId.from_seed("aggregate"),
        correlation_id=PaperExecutionCorrelationId.from_seed("correlation"),
    )


@pytest.mark.parametrize("kind", tuple(PaperExecutionFailureKind))
def test_failure_kinds_are_stable_serializable_and_fingerprinted(
    kind: PaperExecutionFailureKind,
) -> None:
    result = failure(kind)

    assert result.failure_kind is kind
    assert result.failure_fingerprint.startswith("pfl-")
    assert result.to_primitive()["failure_fingerprint"] == result.failure_fingerprint
    assert result.to_primitive()["safe_message"] == "Safe operator-facing explanation."


def test_failure_flags_are_descriptive_only_and_immutable() -> None:
    result = failure()

    assert result.retryable is False
    assert result.reconciliation_required is True
    assert result.operator_action_required is True
    assert result.terminal is False
    assert result.authority_impacting is True
    with pytest.raises(FrozenInstanceError):
        result.retryable = True  # type: ignore[misc]


@pytest.mark.parametrize(
    "message",
    (
        "contains api_key sentinel",
        "contains SECRET sentinel",
        "authorization: bearer token",
        "private_key should not appear",
    ),
)
def test_failure_rejects_credential_like_safe_messages(message: str) -> None:
    with pytest.raises(PaperExecutionInvariantError):
        PaperExecutionFailure(
            failure_kind=PaperExecutionFailureKind.CONTRACT_VALIDATION,
            severity=PaperExecutionFailureSeverity.ERROR,
            code="CONTRACT_VALIDATION",
            safe_message=message,
            retryable=False,
            reconciliation_required=False,
            operator_action_required=False,
            terminal=True,
            authority_impacting=True,
        )


def test_failure_rejects_raw_exception_objects() -> None:
    with pytest.raises(Exception):
        PaperExecutionFailure(
            failure_kind=PaperExecutionFailureKind.CONTRACT_VALIDATION,
            severity=PaperExecutionFailureSeverity.ERROR,
            code="CONTRACT_VALIDATION",
            safe_message=RuntimeError("boom"),  # type: ignore[arg-type]
            retryable=False,
            reconciliation_required=False,
            operator_action_required=False,
            terminal=True,
            authority_impacting=True,
        )


def test_failure_fingerprint_is_deterministic_and_changes_with_material_fields() -> (
    None
):
    first = failure(PaperExecutionFailureKind.BROKER_REJECTED)
    second = failure(PaperExecutionFailureKind.BROKER_REJECTED)
    changed = failure(PaperExecutionFailureKind.RATE_LIMITED)

    assert first.failure_fingerprint == second.failure_fingerprint
    assert first.failure_fingerprint != changed.failure_fingerprint
    assert "secret" not in repr(first).lower()
