from __future__ import annotations

import builtins
from datetime import UTC, datetime

from tests.test_paper_execution_eligibility_service import build_command, evaluate
from volcanoes.application.execution import (
    PaperExecutionEligibilityDecision,
    PaperExecutionEligibilityPolicy,
)


def test_same_inputs_produce_same_decision_criteria_counts_and_fingerprint() -> None:
    command = build_command()
    first = evaluate(command)
    second = evaluate(command)

    assert first.decision is second.decision
    assert first.passed_criterion_count == second.passed_criterion_count
    assert first.failed_criterion_count == second.failed_criterion_count
    assert first.unresolved_criterion_count == second.unresolved_criterion_count
    assert first.to_primitive() == second.to_primitive()
    assert first.result_fingerprint == second.result_fingerprint


def test_unresolved_only_result_is_indeterminate() -> None:
    result = evaluate(
        build_command(),
        PaperExecutionEligibilityPolicy(
            "eligibility-v1",
            require_external_market_capability=True,
        ),
    )

    assert result.decision is PaperExecutionEligibilityDecision.INDETERMINATE
    assert result.failed_criterion_count == 0
    assert result.unresolved_criterion_count == 1


def test_service_does_not_mutate_command_or_policy() -> None:
    command = build_command()
    policy = PaperExecutionEligibilityPolicy("eligibility-v1")
    before_command = command.to_primitive()
    before_policy = policy.to_primitive()

    evaluate(command, policy)

    assert command.to_primitive() == before_command
    assert policy.to_primitive() == before_policy


def test_service_requires_explicit_time_and_does_not_use_hidden_clock() -> None:
    result = evaluate(build_command(), evaluated_at=None)

    assert result.decision is PaperExecutionEligibilityDecision.INDETERMINATE


def test_service_does_not_read_files_or_environment(monkeypatch) -> None:
    def fail_open(*args, **kwargs):  # noqa: ANN002, ANN003
        raise AssertionError("file access attempted")

    monkeypatch.setattr(builtins, "open", fail_open)

    result = evaluate(
        build_command(), evaluated_at=datetime(2026, 7, 30, 11, tzinfo=UTC)
    )

    assert result.eligible is True


def test_service_does_not_log_emit_metrics_or_publish_events() -> None:
    result = evaluate(build_command())

    assert result.execution_authorized is False
    assert result.action_executed is False
