"""Outer-layer composition for the Streamlit Paper Order preview."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from adapters.broker_portfolio_view import BrokerPortfolioView
from adapters.paper_order_composition import (
    build_paper_order_planner,
    to_preview_request,
)
from broker.base import PaperBroker
from trading.risk_manager import (
    RiskDecision,
    RiskLimits,
    TradeProposal,
)
from volcanoes.application.services import (
    PreviewTradeResult,
    PreviewTradeService,
)
from volcanoes.application.qualification.integration import (
    PaperIntegrationEnvironment,
    PaperPreviewObservationFacts,
    PaperQualificationShadowGate,
    QualificationRuntimeIntegrationBoundary,
    observe_paper_preview_decision,
)
from volcanoes.application.operations import OperationalMetrics
from volcanoes.domain import TradeSide
from volcanoes.events import EventPublisher, new_correlation_id


class ParityClassification(StrEnum):
    """Classification applied to a preview parity difference."""

    POLICY_DIFFERENCE = "POLICY_DIFFERENCE"
    IMPLEMENTATION_DEFECT = "IMPLEMENTATION_DEFECT"


@dataclass(frozen=True, slots=True)
class PreviewParityDifference:
    """One field-level difference between legacy and deterministic previews."""

    field: str
    legacy_value: object
    deterministic_value: object
    classification: ParityClassification
    policy_reasons: tuple[str, ...] = ()


LegacyPreview = Callable[[TradeProposal], RiskDecision]

_SIZING_POLICY_REASON = "legacy sizing clamps quantity while deterministic risk rejects"
_DIRECTION_POLICY_REASON = "legacy preview applies an explicit long-only policy"
_DECISION_FIELDS = {"approval", "rejection_reason"}
_NUMERIC_POLICY_REASONS = {
    _DIRECTION_POLICY_REASON,
    _SIZING_POLICY_REASON,
}


def preview_paper_order(
    *,
    broker: PaperBroker,
    proposal: TradeProposal,
    limits: RiskLimits,
    legacy_preview: LegacyPreview,
    use_deterministic_preview: bool,
    development_mode: bool,
    logger: logging.Logger | None = None,
    correlation_id: str | None = None,
    event_publisher: EventPublisher | None = None,
    operational_metrics: OperationalMetrics | None = None,
    qualification_shadow_gate: PaperQualificationShadowGate = (
        PaperQualificationShadowGate.DISABLED
    ),
    qualification_boundary: QualificationRuntimeIntegrationBoundary | None = None,
    qualification_observed_at: datetime | None = None,
) -> RiskDecision:
    """Select a preview implementation without changing submission behavior."""

    if not use_deterministic_preview:
        return legacy_preview(proposal)

    deterministic_result = _deterministic_preview(
        broker=broker,
        proposal=proposal,
        limits=limits,
        correlation_id=correlation_id or new_correlation_id(),
        event_publisher=event_publisher,
        operational_metrics=operational_metrics,
    )
    deterministic_decision = _to_legacy_decision(deterministic_result)

    if qualification_shadow_gate is PaperQualificationShadowGate.ENABLED_OBSERVE_ONLY:
        observe_paper_preview_decision(
            gate=qualification_shadow_gate,
            boundary=qualification_boundary,
            facts=PaperPreviewObservationFacts(
                environment=PaperIntegrationEnvironment.PAPER,
                symbol=proposal.symbol,
                entry_price=Decimal(str(proposal.entry_price)),
                stop_price=Decimal(str(proposal.stop_price)),
                target_price=Decimal(str(proposal.target_price)),
                approved=deterministic_decision.approved,
                quantity=deterministic_decision.quantity,
                correlation_id=deterministic_result.correlation_id,
                occurred_at=qualification_observed_at,
                reasons=tuple(deterministic_decision.reasons),
            ),
        )

    if development_mode:
        _run_parity_diagnostics(
            proposal=proposal,
            limits=limits,
            legacy_preview=legacy_preview,
            deterministic_decision=deterministic_decision,
            deterministic_result=deterministic_result,
            logger=logger or logging.getLogger(__name__),
        )

    return deterministic_decision


def _run_parity_diagnostics(
    *,
    proposal: TradeProposal,
    limits: RiskLimits,
    legacy_preview: LegacyPreview,
    deterministic_decision: RiskDecision,
    deterministic_result: PreviewTradeResult,
    logger: logging.Logger,
) -> None:
    """Log parity differences without changing the active preview result."""

    try:
        legacy_decision = legacy_preview(proposal)
        differences = compare_preview_decisions(
            proposal=proposal,
            limits=limits,
            legacy=legacy_decision,
            deterministic=deterministic_decision,
            deterministic_result=deterministic_result,
        )
        _log_differences(differences, logger)
    except Exception:
        logger.exception(
            "Preview parity diagnostics failed; deterministic preview remains active."
        )


def compare_preview_decisions(
    *,
    proposal: TradeProposal,
    limits: RiskLimits,
    legacy: RiskDecision,
    deterministic: RiskDecision,
    deterministic_result: PreviewTradeResult,
) -> tuple[PreviewParityDifference, ...]:
    """Return classified field-level differences for development diagnostics."""

    all_policy_reasons = _policy_reasons(
        proposal=proposal,
        limits=limits,
        legacy=legacy,
        deterministic_result=deterministic_result,
    )
    comparisons = (
        ("quantity", legacy.quantity, deterministic.quantity),
        (
            "dollar_risk",
            round(legacy.maximum_loss, 2),
            round(deterministic.maximum_loss, 2),
        ),
        (
            "exposure",
            round(legacy.capital_required, 2),
            round(deterministic.capital_required, 2),
        ),
        ("approval", legacy.approved, deterministic.approved),
        (
            "rejection_reason",
            tuple(legacy.reasons),
            tuple(deterministic.reasons),
        ),
    )

    differences: list[PreviewParityDifference] = []
    for field, legacy_value, deterministic_value in comparisons:
        if legacy_value == deterministic_value:
            continue

        field_policy_reasons = _policy_reasons_for_field(
            field,
            all_policy_reasons,
        )
        differences.append(
            PreviewParityDifference(
                field=field,
                legacy_value=legacy_value,
                deterministic_value=deterministic_value,
                classification=(
                    ParityClassification.POLICY_DIFFERENCE
                    if field_policy_reasons
                    else ParityClassification.IMPLEMENTATION_DEFECT
                ),
                policy_reasons=field_policy_reasons,
            )
        )

    return tuple(differences)


def _policy_reasons_for_field(
    field: str,
    policy_reasons: tuple[str, ...],
) -> tuple[str, ...]:
    """Return only policy causes capable of explaining this field."""

    if field in _DECISION_FIELDS:
        return policy_reasons

    return tuple(
        reason for reason in policy_reasons if reason in _NUMERIC_POLICY_REASONS
    )


def _deterministic_preview(
    *,
    broker: PaperBroker,
    proposal: TradeProposal,
    limits: RiskLimits,
    correlation_id: str,
    event_publisher: EventPublisher | None,
    operational_metrics: OperationalMetrics | None,
) -> PreviewTradeResult:
    portfolio_view = BrokerPortfolioView.from_broker(broker)
    request = to_preview_request(
        proposal,
        correlation_id=correlation_id,
    )
    service = PreviewTradeService(
        build_paper_order_planner(limits),
        event_publisher=event_publisher,
        operational_metrics=operational_metrics,
    )
    open_order_symbols = (
        frozenset(order.symbol for order in broker.get_open_orders())
        if portfolio_view.equity > Decimal("0") and isinstance(request.side, TradeSide)
        else frozenset()
    )
    return service.preview(
        portfolio_view,
        request,
        open_order_symbols=open_order_symbols,
    )


def _to_legacy_decision(result: PreviewTradeResult) -> RiskDecision:
    return RiskDecision(
        approved=result.approved,
        quantity=result.quantity,
        maximum_loss=round(float(result.dollar_risk), 2),
        capital_required=round(float(result.position_value), 2),
        reward_risk=round(float(result.reward_risk), 2),
        reasons=list(result.reasons),
    )


def _policy_reasons(
    *,
    proposal: TradeProposal,
    limits: RiskLimits,
    legacy: RiskDecision,
    deterministic_result: PreviewTradeResult,
) -> tuple[str, ...]:
    reasons: list[str] = []
    risk_per_share = abs(proposal.entry_price - proposal.stop_price)
    reward_per_share = abs(proposal.target_price - proposal.entry_price)
    reward_risk = reward_per_share / risk_per_share if risk_per_share > 0 else 0.0

    if proposal.entry_price < limits.minimum_price:
        reasons.append("minimum-price policy exists only in legacy preview")

    if reward_risk < limits.minimum_reward_risk:
        reasons.append("minimum reward/risk policy exists only in legacy preview")

    if limits.long_only and proposal.side.lower() != "buy":
        reasons.append(_DIRECTION_POLICY_REASON)

    legacy_reasons = " ".join(legacy.reasons).lower()
    if "position in this symbol already exists" in legacy_reasons:
        reasons.append("duplicate-position policies differ")

    if "open order for this symbol already exists" in legacy_reasons:
        reasons.append("open-order state is intentionally absent from preview")

    legacy_daily_loss = "daily loss lock is active" in legacy_reasons
    deterministic_daily_loss = deterministic_result.risk_code == "MAX_DAILY_LOSS"
    if legacy_daily_loss or deterministic_daily_loss:
        reasons.append("daily-loss threshold bases and rejection messages differ")

    if (
        "maximum number of open positions" in legacy_reasons
        or deterministic_result.risk_code == "MAX_OPEN_POSITIONS"
    ):
        reasons.append("maximum-open-position rejection messages differ")

    if (
        deterministic_result.risk_code == "INVALID_PORTFOLIO"
        and legacy.reasons != list(deterministic_result.reasons)
    ):
        reasons.append("invalid-account rejection reporting differs")

    if len(legacy.reasons) > 1 and not deterministic_result.approved:
        reasons.append(
            "legacy aggregates rejections while deterministic planning fails fast"
        )

    if (
        deterministic_result.risk_code
        in {
            "INSUFFICIENT_BUYING_POWER",
            "MAX_POSITION_SIZE",
            "MAX_PORTFOLIO_EXPOSURE",
        }
        and legacy.quantity != deterministic_result.quantity
    ):
        reasons.append(_SIZING_POLICY_REASON)

    return tuple(reasons)


def _log_differences(
    differences: tuple[PreviewParityDifference, ...],
    logger: logging.Logger,
) -> None:
    for difference in differences:
        logger.warning(
            "Preview parity difference [%s] field=%s legacy=%r "
            "deterministic=%r policies=%s",
            difference.classification.value,
            difference.field,
            difference.legacy_value,
            difference.deterministic_value,
            difference.policy_reasons,
        )
