from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from tests.test_paper_execution_eligibility_service import build_command, evaluate
from volcanoes.application.execution import (
    PaperExecutionEligibilityCriterionOutcome,
    PaperExecutionEligibilityDecision,
    PaperExecutionEligibilityResult,
)


def test_result_is_immutable_serializable_and_fingerprinted() -> None:
    result = evaluate(build_command())

    assert isinstance(result, PaperExecutionEligibilityResult)
    assert result.result_fingerprint.startswith("per-")
    primitive = result.to_primitive()
    assert primitive["result_fingerprint"] == result.result_fingerprint
    assert primitive["passed_criterion_count"] == result.passed_criterion_count
    with pytest.raises(FrozenInstanceError):
        result.decision = PaperExecutionEligibilityDecision.INELIGIBLE  # type: ignore[misc]


def test_result_fixed_golden_fingerprint() -> None:
    result = evaluate(
        build_command(), evaluated_at=datetime(2026, 7, 30, 11, tzinfo=UTC)
    )

    assert (
        result.result_fingerprint
        == "per-08c1c0d2c89a0230ae2e9c1bee137b97aa9d4cf3c8fc34d7fe2c6d3c4e2a8d75"
    )


def test_result_invariants_are_not_caller_configurable() -> None:
    result = evaluate(build_command())

    assert result.advisory_only is True
    assert result.execution_authorized is False
    assert result.action_executed is False
    assert result.eligible is True


def test_result_has_no_execution_behavior_methods() -> None:
    prohibited = {
        "execute",
        "authorize",
        "submit",
        "dispatch",
        "persist",
        "reserve",
        "retry",
        "reconcile",
    }

    assert prohibited.isdisjoint(dir(PaperExecutionEligibilityResult))


def test_criterion_results_are_immutable_safe_and_three_state() -> None:
    result = evaluate(build_command())
    criterion = result.criteria[0]

    assert criterion.outcome in tuple(PaperExecutionEligibilityCriterionOutcome)
    assert criterion.safe_message.isupper()
    assert "secret" not in repr(criterion).lower()
    with pytest.raises(FrozenInstanceError):
        criterion.safe_message = "CHANGED"  # type: ignore[misc]


def test_no_secret_values_in_result_repr() -> None:
    result = evaluate(build_command())

    assert "api_key" not in repr(result).lower()
    assert "secret" not in repr(result).lower()
