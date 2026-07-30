from __future__ import annotations

import builtins
import os
import random
import socket
import subprocess
import time
import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import adapters.paper_order_preview as preview_adapter
from adapters.paper_order_preview import preview_paper_order
from broker.base import AccountSnapshot, BrokerOrder, BrokerPosition
from trading.execution import PaperExecutionEngine
from trading.risk_manager import RiskDecision, RiskLimits, RiskManager, TradeProposal
from volcanoes.application.qualification import (
    QualificationResult,
    QualificationState,
    StateRevision,
)
from volcanoes.application.qualification.integration import (
    BoundaryResultValidationError,
    PaperIntegrationEnvironment,
    PaperPreviewObservationFacts,
    PaperQualificationObservationStatus,
    PaperQualificationShadowGate,
    PaperQualificationShadowRequest,
    PaperQualificationShadowResult,
    QualificationRuntimeBoundaryMode,
    QualificationRuntimeBoundaryRequest,
    QualificationRuntimeBoundaryResult,
    QualificationRuntimeBoundaryStatus,
    QualificationRuntimeIntegrationBoundary,
    RuntimeActionKind,
    ShadowComparisonStatus,
    ShadowMismatch,
    ShadowMismatchClassification,
    observe_paper_preview_decision,
)

OCCURRED_AT = datetime(2026, 7, 29, 20, 0, tzinfo=UTC)


class RecordingBroker:
    name = "Recording broker"
    is_paper = True

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.account = AccountSnapshot(
            equity=100_000.0,
            cash=100_000.0,
            buying_power=100_000.0,
            daily_pnl=0.0,
            paper=True,
        )

    def get_account(self) -> AccountSnapshot:
        self.calls.append("get_account")
        return self.account

    def get_positions(self) -> list[BrokerPosition]:
        self.calls.append("get_positions")
        return []

    def get_open_orders(self) -> list[BrokerOrder]:
        self.calls.append("get_open_orders")
        return []

    def submit_bracket_order(
        self,
        *,
        symbol: str,
        quantity: int,
        entry_price: float,
        stop_price: float,
        target_price: float,
    ) -> BrokerOrder:
        self.calls.append("submit_bracket_order")
        raise AssertionError("shadow observation submitted a broker order")

    def cancel_all_orders(self) -> int:
        self.calls.append("cancel_all_orders")
        raise AssertionError("shadow observation cancelled orders")

    def close_all_positions(self) -> int:
        self.calls.append("close_all_positions")
        raise AssertionError("shadow observation closed positions")


class ControlledBoundary(QualificationRuntimeIntegrationBoundary):
    def __init__(
        self,
        *,
        status: ShadowComparisonStatus = ShadowComparisonStatus.MATCH,
        classifications: tuple[ShadowMismatchClassification, ...] = (),
        error: BaseException | None = None,
    ) -> None:
        self.status = status
        self.classifications = classifications
        self.error = error
        self.requests: list[QualificationRuntimeBoundaryRequest] = []

    def evaluate_shadow(
        self,
        request: QualificationRuntimeBoundaryRequest,
    ) -> QualificationRuntimeBoundaryResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        shadow = request.shadow_request
        shadow_result = shadow_result_from_request(
            shadow,
            status=self.status,
            classifications=self.classifications,
        )
        return boundary_result_from_shadow(request, shadow_result)


def proposal(
    *,
    symbol: str = "AAPL",
    entry: float = 100.0,
    stop: float = 97.5,
    target: float = 105.0,
) -> TradeProposal:
    return TradeProposal(
        symbol=symbol,
        entry_price=entry,
        stop_price=stop,
        target_price=target,
    )


def preview_stack(
    broker: RecordingBroker,
) -> tuple[RiskLimits, PaperExecutionEngine]:
    limits = RiskLimits()
    return limits, PaperExecutionEngine(broker, RiskManager(limits))


def run_preview(
    broker: RecordingBroker,
    *,
    boundary: QualificationRuntimeIntegrationBoundary | None = None,
    gate: PaperQualificationShadowGate = PaperQualificationShadowGate.DISABLED,
    trade: TradeProposal | None = None,
) -> RiskDecision:
    limits, engine = preview_stack(broker)
    return preview_paper_order(
        broker=broker,
        proposal=trade or proposal(),
        limits=limits,
        legacy_preview=engine.preview,
        use_deterministic_preview=True,
        development_mode=False,
        correlation_id="corr-f4b-preview",
        qualification_shadow_gate=gate,
        qualification_boundary=boundary,
        qualification_observed_at=OCCURRED_AT,
    )


def facts(**overrides: Any) -> PaperPreviewObservationFacts:
    values: dict[str, Any] = {
        "environment": PaperIntegrationEnvironment.PAPER,
        "symbol": "AAPL",
        "entry_price": Decimal("100"),
        "stop_price": Decimal("97.5"),
        "target_price": Decimal("105"),
        "approved": True,
        "quantity": 100,
        "correlation_id": "corr-f4b-preview",
        "occurred_at": OCCURRED_AT,
    }
    values.update(overrides)
    return PaperPreviewObservationFacts(**values)


def shadow_result_from_request(
    shadow: PaperQualificationShadowRequest,
    *,
    status: ShadowComparisonStatus,
    classifications: tuple[ShadowMismatchClassification, ...] = (),
) -> PaperQualificationShadowResult:
    mismatches = tuple(
        ShadowMismatch(classification, classification.value.lower(), "safe-reason")
        for classification in classifications
    )
    return PaperQualificationShadowResult(
        shadow_invocation_id=shadow.shadow_invocation_id,
        legacy_decision=shadow.legacy_decision,
        qualification_facade_result=None,
        comparison_status=status,
        classifications=classifications,
        matched_fields=("identity",),
        mismatches=mismatches,
        qualification_run_id=shadow.runtime_request.qualification_run_id,
        command_id=shadow.runtime_request.command_id,
        correlation_id=shadow.runtime_request.correlation_id,
        idempotency_key=shadow.runtime_request.idempotency_key,
        transition_id="PQ-TRN-001",
        previous_revision=shadow.runtime_request.expected_revision,
        next_revision=StateRevision(1),
        legacy_action_type=shadow.legacy_decision.action_type,
        qualification_action_type=RuntimeActionKind.NO_RUNTIME_ACTION_REQUIRED,
        qualification_state=QualificationState.PRECHECK_PENDING,
        qualification_result=QualificationResult.PENDING,
        replayed=False,
        safe_operator_summary="safe shadow summary",
        action_executed=False,
        legacy_behavior_changed=False,
    )


def boundary_result_from_shadow(
    request: QualificationRuntimeBoundaryRequest,
    shadow_result: PaperQualificationShadowResult,
) -> QualificationRuntimeBoundaryResult:
    return QualificationRuntimeBoundaryResult(
        boundary_invocation_id=request.boundary_invocation_id,
        boundary_mode=QualificationRuntimeBoundaryMode.SHADOW_ONLY,
        boundary_status=QualificationRuntimeBoundaryStatus.SHADOW_MATCH,
        shadow_result=shadow_result,
        qualification_run_id=shadow_result.qualification_run_id,
        runtime_request_id=shadow_result.legacy_decision.runtime_request_id,
        command_id=shadow_result.command_id,
        correlation_id=shadow_result.correlation_id,
        idempotency_key=shadow_result.idempotency_key,
        comparison_status=shadow_result.comparison_status,
        mismatch_classifications=shadow_result.classifications,
        expected_revision=request.shadow_request.runtime_request.expected_revision,
        previous_revision=shadow_result.previous_revision,
        next_revision=shadow_result.next_revision,
        transition_id=shadow_result.transition_id,
        action_described=shadow_result.qualification_action_type,
        safe_summary="safe boundary summary",
        action_executed=False,
        legacy_behavior_authoritative=True,
        legacy_behavior_changed=False,
        runtime_connected=False,
    )


def test_gate_defaults_to_disabled_and_does_not_invoke_boundary() -> None:
    boundary = ControlledBoundary()

    observation = observe_paper_preview_decision(boundary=boundary, facts=facts())

    assert observation.gate is PaperQualificationShadowGate.DISABLED
    assert observation.status is PaperQualificationObservationStatus.DISABLED
    assert observation.boundary_invoked is False
    assert boundary.requests == []


def test_disabled_runtime_call_site_preserves_legacy_return_and_calls() -> None:
    broker = RecordingBroker()
    boundary = ControlledBoundary()

    disabled_result = run_preview(broker, boundary=boundary)
    calls = list(broker.calls)

    assert disabled_result == run_preview(RecordingBroker())
    assert calls == ["get_account", "get_positions", "get_open_orders"]
    assert boundary.requests == []


def test_disabled_gate_does_not_construct_observation_contracts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("observation adapter should not run")

    monkeypatch.setattr(preview_adapter, "observe_paper_preview_decision", fail)

    result = run_preview(RecordingBroker())

    assert result.approved is True


def test_enabled_gate_invokes_boundary_exactly_once_and_preserves_legacy_result() -> (
    None
):
    broker = RecordingBroker()
    boundary = ControlledBoundary()
    expected = run_preview(RecordingBroker())

    result = run_preview(
        broker,
        boundary=boundary,
        gate=PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY,
    )

    assert result == expected
    assert len(boundary.requests) == 1
    request = boundary.requests[0]
    assert request.mode is QualificationRuntimeBoundaryMode.SHADOW_ONLY
    assert (
        request.shadow_request.runtime_request.environment
        is PaperIntegrationEnvironment.PAPER
    )
    assert request.shadow_request.runtime_request.correlation_id == "corr-f4b-preview"
    assert request.shadow_request.legacy_decision.correlation_id == "corr-f4b-preview"
    assert request.shadow_request.runtime_request.expected_revision == 0


@pytest.mark.parametrize(
    "status",
    [
        ShadowComparisonStatus.MATCH,
        ShadowComparisonStatus.MATCH_WITH_NONCONSEQUENTIAL_DIFFERENCE,
        ShadowComparisonStatus.MISMATCH,
        ShadowComparisonStatus.INCOMPARABLE,
        ShadowComparisonStatus.QUALIFICATION_ERROR,
    ],
)
def test_enabled_shadow_statuses_do_not_change_legacy_result(
    status: ShadowComparisonStatus,
) -> None:
    expected = run_preview(RecordingBroker())
    boundary = ControlledBoundary(
        status=status,
        classifications=(
            (ShadowMismatchClassification.ACTION_KIND_MISMATCH,)
            if status is ShadowComparisonStatus.MISMATCH
            else ()
        ),
    )

    result = run_preview(
        RecordingBroker(),
        boundary=boundary,
        gate=PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY,
    )

    assert result == expected
    assert len(boundary.requests) == 1


def test_boundary_typed_failure_is_contained_without_changing_preview() -> None:
    boundary = ControlledBoundary(
        error=BoundaryResultValidationError(
            reason_code="BOUNDARY_RESULT_IDENTITY_CONTINUITY_FAILED",
            safe_message="Safe boundary failure.",
        )
    )
    expected = run_preview(RecordingBroker())

    result = run_preview(
        RecordingBroker(),
        boundary=boundary,
        gate=PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY,
    )

    assert result == expected
    assert len(boundary.requests) == 1


def test_legacy_exception_is_not_swallowed_by_shadow_containment() -> None:
    def failing_legacy_preview(_: TradeProposal) -> RiskDecision:
        raise RuntimeError("legacy failure")

    limits, _engine = preview_stack(RecordingBroker())

    with pytest.raises(RuntimeError, match="legacy failure"):
        preview_paper_order(
            broker=RecordingBroker(),
            proposal=proposal(),
            limits=limits,
            legacy_preview=failing_legacy_preview,
            use_deterministic_preview=False,
            development_mode=False,
            qualification_shadow_gate=PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY,
            qualification_boundary=ControlledBoundary(),
            qualification_observed_at=OCCURRED_AT,
        )


def test_base_exception_from_boundary_is_not_swallowed() -> None:
    class BoundaryExit(BaseException):
        pass

    boundary = ControlledBoundary(error=BoundaryExit())

    with pytest.raises(BoundaryExit):
        run_preview(
            RecordingBroker(),
            boundary=boundary,
            gate=PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY,
        )


@pytest.mark.parametrize(
    "environment", [PaperIntegrationEnvironment.LIVE, "UNKNOWN", None]
)
def test_non_paper_input_never_reaches_boundary(environment: object) -> None:
    boundary = ControlledBoundary()

    observation = observe_paper_preview_decision(
        gate=PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY,
        boundary=boundary,
        facts=facts(environment=environment),
    )

    assert observation.status is PaperQualificationObservationStatus.BOUNDARY_ERROR
    assert observation.boundary_invoked is False
    assert boundary.requests == []


def test_missing_timestamp_skips_before_boundary() -> None:
    boundary = ControlledBoundary()

    observation = observe_paper_preview_decision(
        gate=PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY,
        boundary=boundary,
        facts=facts(occurred_at=None),
    )

    assert (
        observation.status is PaperQualificationObservationStatus.SKIPPED_INVALID_INPUT
    )
    assert observation.safe_reason_code == "MISSING_OBSERVATION_TIMESTAMP"
    assert observation.boundary_invoked is False
    assert boundary.requests == []


def test_observation_result_is_immutable_and_non_executing() -> None:
    observation = observe_paper_preview_decision()

    with pytest.raises(FrozenInstanceError):
        observation.boundary_invoked = True  # type: ignore[misc]
    assert observation.action_executed is False
    assert observation.legacy_behavior_authoritative is True
    assert observation.legacy_behavior_changed is False


def test_identities_are_deterministic_and_materially_sensitive() -> None:
    boundary = ControlledBoundary()
    first = observe_paper_preview_decision(
        gate=PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY,
        boundary=boundary,
        facts=facts(),
    )
    second_boundary = ControlledBoundary()
    second = observe_paper_preview_decision(
        gate=PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY,
        boundary=second_boundary,
        facts=facts(),
    )
    changed_boundary = ControlledBoundary()
    changed = observe_paper_preview_decision(
        gate=PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY,
        boundary=changed_boundary,
        facts=facts(symbol="MSFT"),
    )

    assert first.boundary_result is not None
    assert second.boundary_result is not None
    assert changed.boundary_result is not None
    assert (
        first.boundary_result.shadow_result.shadow_invocation_id
        == second.boundary_result.shadow_result.shadow_invocation_id
    )
    assert (
        first.boundary_result.boundary_invocation_id
        == second.boundary_result.boundary_invocation_id
    )
    assert (
        first.boundary_result.shadow_result.shadow_invocation_id
        != changed.boundary_result.shadow_result.shadow_invocation_id
    )


def test_secret_absent_from_observation_error_and_identity() -> None:
    observation = observe_paper_preview_decision(
        gate=PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY,
        boundary=ControlledBoundary(),
        facts=facts(metadata=(("note", "SENTINEL_F4B_SECRET_DO_NOT_EXPOSE"),)),
    )

    rendered = repr(observation)
    assert observation.status is PaperQualificationObservationStatus.BOUNDARY_ERROR
    assert "SENTINEL_F4B_SECRET_DO_NOT_EXPOSE" not in rendered
    assert "SENTINEL_F4B_TOKEN_DO_NOT_EXPOSE" not in rendered
    assert "SENTINEL_F4B_PASSWORD_DO_NOT_EXPOSE" not in rendered


def test_no_external_effects_from_qualification_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("external effect attempted")

    monkeypatch.setattr(builtins, "open", fail)
    monkeypatch.setattr(Path, "read_text", fail)
    monkeypatch.setattr(Path, "write_text", fail)
    monkeypatch.setattr(Path, "write_bytes", fail)
    monkeypatch.setattr(socket, "socket", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(os, "getenv", fail)
    monkeypatch.setattr(time, "time", fail)
    monkeypatch.setattr(uuid, "uuid4", fail)
    monkeypatch.setattr(random, "random", fail)

    result = run_preview(
        RecordingBroker(),
        boundary=ControlledBoundary(status=ShadowComparisonStatus.MISMATCH),
        gate=PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY,
    )

    assert result.approved is True


def test_runtime_facts_are_not_mutated() -> None:
    input_facts = facts()
    before = repr(input_facts)

    observe_paper_preview_decision(
        gate=PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY,
        boundary=ControlledBoundary(),
        facts=input_facts,
    )

    assert repr(input_facts) == before


def test_rejected_preview_observation_changes_nothing() -> None:
    trade = proposal(entry=5.0, stop=4.0, target=7.0)
    expected = run_preview(RecordingBroker(), trade=trade)
    boundary = ControlledBoundary(status=ShadowComparisonStatus.MISMATCH)

    result = run_preview(
        RecordingBroker(),
        boundary=boundary,
        gate=PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY,
        trade=trade,
    )

    assert result == expected
    assert result.approved is False
    assert len(boundary.requests) == 1
    assert boundary.requests[0].shadow_request.runtime_request.order_intent is None


def test_default_preview_observation_uses_no_broker_mutation() -> None:
    broker = RecordingBroker()

    run_preview(
        broker,
        boundary=ControlledBoundary(),
        gate=PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY,
    )

    assert broker.calls == ["get_account", "get_positions", "get_open_orders"]
