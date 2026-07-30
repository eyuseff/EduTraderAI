"""Controlled runtime observation adapter for Paper qualification shadow mode."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from volcanoes.application.qualification.contracts import (
    ActorType,
    CommandId,
    CorrelationId,
    Guard,
    IdempotencyKey,
    QualificationRunId,
    QualificationScenarioId,
    StateRevision,
)
from volcanoes.application.qualification.integration.boundary import (
    QualificationRuntimeBoundaryRequest,
    QualificationRuntimeBoundaryResult,
    QualificationRuntimeIntegrationBoundary,
)
from volcanoes.application.qualification.integration.contracts import (
    IntegrationOrderType,
    IntegrationTimeInForce,
    PaperIntegrationEnvironment,
    PaperRuntimeRequest,
    RuntimeRequestKind,
    SafeMetadata,
    SafeOrderIntent,
    require_paper_environment,
)
from volcanoes.application.qualification.integration.errors import (
    QualificationIntegrationError,
)
from volcanoes.application.qualification.integration.shadow import (
    LegacyPaperActionType,
    LegacyPaperDecision,
    LegacyPaperDecisionType,
    PaperQualificationShadowRequest,
)
from volcanoes.application.qualification.integration.translation import (
    derive_integration_identity,
)


class PaperQualificationShadowGate(StrEnum):
    """Small explicit gate for controlled shadow observation."""

    DISABLED = "disabled"
    ENABLED_OBSERVE_ONLY = "enabled_observe_only"


class PaperQualificationObservationStatus(StrEnum):
    """Safe status for one optional runtime observation attempt."""

    DISABLED = "DISABLED"
    OBSERVED = "OBSERVED"
    SKIPPED_INVALID_INPUT = "SKIPPED_INVALID_INPUT"
    BOUNDARY_ERROR = "BOUNDARY_ERROR"


@dataclass(frozen=True, slots=True)
class PaperPreviewObservationFacts:
    """Safe facts already available after deterministic Paper preview."""

    environment: PaperIntegrationEnvironment
    symbol: str
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    approved: bool
    quantity: int
    correlation_id: str
    occurred_at: datetime | None = None
    reasons: tuple[str, ...] = ()
    metadata: SafeMetadata = ()


@dataclass(frozen=True, slots=True)
class PaperQualificationRuntimeObservation:
    """Immutable non-authoritative result of optional shadow observation."""

    gate: PaperQualificationShadowGate
    status: PaperQualificationObservationStatus
    boundary_invoked: bool
    boundary_result: QualificationRuntimeBoundaryResult | None
    safe_reason_code: str | None = None
    action_executed: Literal[False] = False
    legacy_behavior_authoritative: Literal[True] = True
    legacy_behavior_changed: Literal[False] = False


def observe_paper_preview_decision(
    *,
    gate: PaperQualificationShadowGate = PaperQualificationShadowGate.DISABLED,
    boundary: QualificationRuntimeIntegrationBoundary | None = None,
    facts: PaperPreviewObservationFacts | None = None,
) -> PaperQualificationRuntimeObservation:
    """Optionally observe one deterministic Paper preview without changing it."""

    if gate is PaperQualificationShadowGate.DISABLED:
        return _disabled_observation()
    if gate is not PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY:
        return _skipped("UNSUPPORTED_SHADOW_GATE")
    if boundary is None or facts is None:
        return _skipped("MISSING_SHADOW_OBSERVATION_DEPENDENCY")
    if not isinstance(boundary, QualificationRuntimeIntegrationBoundary):
        return _skipped("INVALID_SHADOW_BOUNDARY")

    try:
        require_paper_environment(facts.environment)
    except QualificationIntegrationError as error:
        return _error_observation(gate, error.reason_code, boundary_invoked=False)
    if facts.occurred_at is None:
        return _skipped("MISSING_OBSERVATION_TIMESTAMP")
    occurred_at = facts.occurred_at
    try:
        shadow_request = _shadow_request_from_preview(facts, occurred_at=occurred_at)
    except QualificationIntegrationError as error:
        return _error_observation(gate, error.reason_code, boundary_invoked=False)
    try:
        boundary_result = boundary.evaluate_shadow(
            QualificationRuntimeBoundaryRequest(shadow_request=shadow_request)
        )
    except QualificationIntegrationError as error:
        return _error_observation(gate, error.reason_code, boundary_invoked=True)
    return PaperQualificationRuntimeObservation(
        gate=gate,
        status=PaperQualificationObservationStatus.OBSERVED,
        boundary_invoked=True,
        boundary_result=boundary_result,
        safe_reason_code=None,
        action_executed=False,
        legacy_behavior_authoritative=True,
        legacy_behavior_changed=False,
    )


def _shadow_request_from_preview(
    facts: PaperPreviewObservationFacts,
    *,
    occurred_at: datetime,
) -> PaperQualificationShadowRequest:
    identities = _preview_identities(facts)
    order_intent = _order_intent_from_preview(facts)
    runtime_request = PaperRuntimeRequest(
        environment=facts.environment,
        runtime_request_id=identities.runtime_request_id,
        qualification_run_id=QualificationRunId(identities.qualification_run_id),
        qualification_scenario_id=QualificationScenarioId("PQ-SCN-005"),
        request_kind=RuntimeRequestKind.START_QUALIFICATION,
        command_id=CommandId(identities.command_id),
        correlation_id=CorrelationId(facts.correlation_id),
        idempotency_key=IdempotencyKey(identities.idempotency_key),
        expected_revision=StateRevision(0),
        actor_type=ActorType.APPLICATION,
        occurred_at=occurred_at,
        order_intent=order_intent,
        satisfied_guards=frozenset({Guard.PAPER_ENVIRONMENT}),
        reason_code=_reason_code(facts),
        metadata=facts.metadata,
    )
    legacy_decision = LegacyPaperDecision(
        environment=facts.environment,
        legacy_decision_id=identities.legacy_decision_id,
        runtime_request_id=identities.runtime_request_id,
        qualification_run_id=QualificationRunId(identities.qualification_run_id),
        command_id=CommandId(identities.command_id),
        correlation_id=CorrelationId(facts.correlation_id),
        idempotency_key=IdempotencyKey(identities.idempotency_key),
        expected_revision=StateRevision(0),
        decision_type=(
            LegacyPaperDecisionType.PROCEED
            if facts.approved
            else LegacyPaperDecisionType.BLOCK
        ),
        action_type=(
            LegacyPaperActionType.SUBMIT_ORDER
            if facts.approved
            else LegacyPaperActionType.BLOCK_CONSEQUENTIAL_ACTION
        ),
        order_intent=order_intent,
        approved=facts.approved,
        reason_code=_reason_code(facts),
        metadata=facts.metadata,
    )
    return PaperQualificationShadowRequest(
        runtime_request=runtime_request,
        legacy_decision=legacy_decision,
    )


@dataclass(frozen=True, slots=True)
class _PreviewIdentities:
    runtime_request_id: str
    legacy_decision_id: str
    qualification_run_id: str
    command_id: str
    idempotency_key: str


def _preview_identities(facts: PaperPreviewObservationFacts) -> _PreviewIdentities:
    base = (
        facts.environment.value,
        facts.correlation_id,
        facts.symbol,
        str(facts.entry_price),
        str(facts.stop_price),
        str(facts.target_price),
        str(facts.approved),
        str(facts.quantity),
    )
    return _PreviewIdentities(
        runtime_request_id=derive_integration_identity("qir", ("runtime", *base)),
        legacy_decision_id=derive_integration_identity("qld", ("legacy", *base)),
        qualification_run_id=derive_integration_identity("pqr", ("run", *base)),
        command_id=derive_integration_identity("qic", ("command", *base)),
        idempotency_key=derive_integration_identity("qik", ("idempotency", *base)),
    )


def _order_intent_from_preview(
    facts: PaperPreviewObservationFacts,
) -> SafeOrderIntent | None:
    if not facts.approved or facts.quantity <= 0:
        return None
    return SafeOrderIntent(
        symbol=facts.symbol,
        quantity=facts.quantity,
        order_type=IntegrationOrderType.LIMIT,
        limit_price=facts.entry_price,
        time_in_force=IntegrationTimeInForce.DAY,
    )


def _reason_code(facts: PaperPreviewObservationFacts) -> str | None:
    if facts.approved:
        return "PAPER_PREVIEW_APPROVED"
    if facts.reasons:
        return derive_integration_identity("qrc", ("rejected", *facts.reasons))
    return "PAPER_PREVIEW_REJECTED"


def _disabled_observation() -> PaperQualificationRuntimeObservation:
    return PaperQualificationRuntimeObservation(
        gate=PaperQualificationShadowGate.DISABLED,
        status=PaperQualificationObservationStatus.DISABLED,
        boundary_invoked=False,
        boundary_result=None,
        safe_reason_code=None,
        action_executed=False,
        legacy_behavior_authoritative=True,
        legacy_behavior_changed=False,
    )


def _skipped(reason_code: str) -> PaperQualificationRuntimeObservation:
    return PaperQualificationRuntimeObservation(
        gate=PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY,
        status=PaperQualificationObservationStatus.SKIPPED_INVALID_INPUT,
        boundary_invoked=False,
        boundary_result=None,
        safe_reason_code=reason_code,
        action_executed=False,
        legacy_behavior_authoritative=True,
        legacy_behavior_changed=False,
    )


def _error_observation(
    gate: PaperQualificationShadowGate,
    reason_code: str,
    *,
    boundary_invoked: bool,
) -> PaperQualificationRuntimeObservation:
    return PaperQualificationRuntimeObservation(
        gate=gate,
        status=PaperQualificationObservationStatus.BOUNDARY_ERROR,
        boundary_invoked=boundary_invoked,
        boundary_result=None,
        safe_reason_code=reason_code,
        action_executed=False,
        legacy_behavior_authoritative=True,
        legacy_behavior_changed=False,
    )
