"""Outer composition for deterministic manual Paper Order submission."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from adapters.broker_portfolio_view import BrokerPortfolioView
from adapters.paper_broker_execution import PaperBrokerExecutionAdapter
from adapters.paper_order_composition import (
    build_paper_order_planner,
    to_preview_request,
)
from broker.base import BrokerOrder, PaperBroker
from trading.risk_manager import RiskDecision, RiskLimits, TradeProposal
from volcanoes.application.operations import OperationalMetrics
from volcanoes.application.services import (
    ExpectedTradePlan,
    SubmitTradeRequest,
    SubmitTradeResult,
    SubmitTradeService,
)
from volcanoes.events import EventPublisher, new_correlation_id
from volcanoes.execution import ExecutionPipeline

LegacySubmit = Callable[[TradeProposal, str], BrokerOrder]


def submit_paper_order(
    *,
    broker: PaperBroker,
    proposal: TradeProposal,
    displayed_preview: RiskDecision,
    limits: RiskLimits,
    confirmation: str,
    legacy_submit: LegacySubmit,
    use_deterministic_submission: bool,
    correlation_id: str | None = None,
    event_publisher: EventPublisher | None = None,
    operational_metrics: OperationalMetrics | None = None,
) -> BrokerOrder | SubmitTradeResult:
    """Select deterministic or untouched legacy manual submission."""

    if not use_deterministic_submission:
        return legacy_submit(proposal, confirmation)

    if confirmation.strip().upper() != "PAPER TRADE":
        raise PermissionError('Type "PAPER TRADE" to authorize submission.')

    lifecycle_id = correlation_id or new_correlation_id()
    canonical = to_preview_request(
        proposal,
        correlation_id=lifecycle_id,
    )
    expected_plan = ExpectedTradePlan(
        approved=displayed_preview.approved,
        quantity=displayed_preview.quantity,
        dollar_risk=Decimal(str(displayed_preview.maximum_loss)),
        position_value=Decimal(str(displayed_preview.capital_required)),
        reasons=tuple(displayed_preview.reasons),
        correlation_id=lifecycle_id,
    )
    request = SubmitTradeRequest(
        symbol=canonical.symbol,
        side=canonical.side,
        entry_price=canonical.entry_price,
        stop_price=canonical.stop_price,
        target_price=canonical.target_price,
        expected_plan=expected_plan,
    )

    portfolio_view = BrokerPortfolioView.from_broker(broker)
    open_order_symbols = frozenset(order.symbol for order in broker.get_open_orders())
    planner = build_paper_order_planner(limits)
    pipeline = ExecutionPipeline(
        PaperBrokerExecutionAdapter(broker),
        planner=planner,
    )
    result = SubmitTradeService(
        planner,
        pipeline,
        event_publisher=event_publisher,
        operational_metrics=operational_metrics,
    ).submit(
        portfolio_view,
        request,
        open_order_symbols=open_order_symbols,
    )

    if not result.submitted:
        raise ValueError(result.explanation)

    return result
