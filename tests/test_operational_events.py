"""Operational safety, correlation, and structured-event tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TypedDict

import pytest

from adapters.paper_order_composition import build_paper_order_planner
from broker.base import AccountSnapshot
from trading.risk_manager import RiskLimits
from volcanoes.application.services import (
    ExpectedTradePlan,
    PreviewTradeRequest,
    PreviewTradeService,
    SubmitTradeRequest,
    SubmitTradeService,
)
from volcanoes.domain import Order, OrderStatus, TradeSide
from volcanoes.events import (
    DomainEvent,
    EventPublisher,
    NullEventPublisher,
    PlanDriftDetected,
    PolicyViolation,
    TradeCancelled,
    TradeFailed,
    TradeFilled,
    TradePreviewed,
    TradeRejected,
    TradeSubmitted,
    event_to_dict,
    serialize_event,
)
from volcanoes.execution import Broker, ExecutionPipeline

CORRELATION_ID = "11111111-2222-3333-4444-555555555555"
TIMESTAMP = datetime(2026, 7, 20, 12, 30, tzinfo=UTC)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CommonEventFields(TypedDict):
    correlation_id: str
    timestamp: datetime


class RecordingPublisher(EventPublisher):
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:
        self.events.append(event)


class RecordingExecutionBroker(Broker):
    def __init__(
        self,
        *,
        status: OrderStatus = OrderStatus.PENDING,
        error: Exception | None = None,
    ) -> None:
        self.status = status
        self.error = error
        self.orders: list[Order] = []

    def submit_order(self, order: Order) -> Order:
        self.orders.append(order)
        if self.error is not None:
            raise self.error
        order.status = self.status
        order.broker_order_id = "event-order-1"
        order.broker_status = self.status.value.lower()
        order.broker_message = "Operational event broker."
        return order

    def get_cash_balance(self) -> Decimal:
        return Decimal("100000")

    def get_position_quantity(self, symbol: str) -> int:
        return 0


def portfolio(*, buying_power: float = 100_000.0):
    from adapters.broker_portfolio_view import BrokerPortfolioView

    return BrokerPortfolioView.from_snapshot(
        AccountSnapshot(
            equity=100_000.0,
            cash=buying_power,
            buying_power=buying_power,
        ),
        [],
    )


def preview_request(
    *,
    entry: str = "100",
    stop: str = "95",
    target: str = "110",
    correlation_id: str = CORRELATION_ID,
) -> PreviewTradeRequest:
    return PreviewTradeRequest(
        symbol="AAPL",
        side=TradeSide.BUY,
        entry_price=Decimal(entry),
        stop_price=Decimal(stop),
        target_price=Decimal(target),
        correlation_id=correlation_id,
    )


def submit_request_from_preview(
    preview_result,
    request: PreviewTradeRequest,
) -> SubmitTradeRequest:
    return SubmitTradeRequest(
        symbol=request.symbol,
        side=request.side,
        entry_price=request.entry_price,
        stop_price=request.stop_price,
        target_price=request.target_price,
        expected_plan=ExpectedTradePlan(
            approved=preview_result.approved,
            quantity=preview_result.quantity,
            dollar_risk=preview_result.dollar_risk,
            position_value=preview_result.position_value,
            reasons=preview_result.reasons,
            risk_code=preview_result.risk_code,
            correlation_id=preview_result.correlation_id,
        ),
    )


def sample_events() -> tuple[DomainEvent, ...]:
    common: CommonEventFields = {
        "correlation_id": CORRELATION_ID,
        "timestamp": TIMESTAMP,
    }
    return (
        TradePreviewed(
            **common,
            symbol="AAPL",
            side="BUY",
            entry_price=Decimal("100"),
            stop_price=Decimal("95"),
            target_price=Decimal("110"),
            approved=True,
            quantity=20,
            dollar_risk=Decimal("100"),
            position_value=Decimal("2000"),
        ),
        TradeRejected(
            **common,
            operation="preview",
            symbol="AAPL",
            policy="MinimumPricePolicy",
            explanation="Price is too low.",
            configuration=(("minimum_price", "10"),),
        ),
        TradeSubmitted(
            **common,
            order_id="order-1",
            symbol="AAPL",
            side="BUY",
            quantity=20,
            price=Decimal("100"),
            stop_price=Decimal("95"),
            target_price=Decimal("110"),
            broker_status="accepted",
        ),
        TradeFilled(
            **common,
            order_id="order-1",
            symbol="AAPL",
            side="BUY",
            quantity=20,
            price=Decimal("100"),
        ),
        TradeCancelled(
            **common,
            order_id="order-1",
            symbol="AAPL",
            explanation="Cancelled by paper broker.",
        ),
        TradeFailed(
            **common,
            operation="submission",
            symbol="AAPL",
            policy="BrokerExecution",
            explanation="Endpoint unavailable.",
            configuration=(("error_type", "RuntimeError"),),
        ),
        PlanDriftDetected(
            **common,
            symbol="AAPL",
            differences=("quantity",),
            expected=(("quantity", "20"),),
            actual=(("quantity", "10"),),
        ),
        PolicyViolation(
            **common,
            operation="preview",
            symbol="AAPL",
            policy="MinimumPricePolicy",
            explanation="Price is too low.",
            configuration=(("minimum_price", "10"),),
        ),
    )


@pytest.mark.parametrize("event", sample_events())
def test_every_operational_event_is_immutable_and_correlated(
    event: DomainEvent,
) -> None:
    assert event.correlation_id == CORRELATION_ID
    assert event.timestamp == TIMESTAMP

    with pytest.raises(FrozenInstanceError):
        event.correlation_id = "changed"  # type: ignore[misc]


def test_event_payload_rejects_mutable_or_infrastructure_objects() -> None:
    with pytest.raises(TypeError, match="immutable deterministic values"):
        TradeFailed(
            correlation_id=CORRELATION_ID,
            operation="submission",
            symbol="AAPL",
            policy="BrokerExecution",
            explanation="Invalid payload.",
            configuration=(("broker", object()),),  # type: ignore[arg-type]
        )


def test_event_serialization_is_deterministic_and_canonical() -> None:
    event = sample_events()[0]

    first = serialize_event(event)
    second = serialize_event(event)

    assert first == second
    assert first == (
        '{"approved":true,"correlation_id":"11111111-2222-3333-4444-'
        '555555555555","dollar_risk":"100","entry_price":"100",'
        '"event_type":"TradePreviewed","position_value":"2000",'
        '"quantity":20,"side":"BUY","stop_price":"95","symbol":"AAPL",'
        '"target_price":"110","timestamp":"2026-07-20T12:30:00Z"}'
    )
    assert event_to_dict(event)["timestamp"] == "2026-07-20T12:30:00Z"


def test_null_publisher_accepts_domain_events_without_side_effects() -> None:
    publisher = NullEventPublisher()

    publisher.publish(sample_events()[0])

    with pytest.raises(TypeError, match="DomainEvent"):
        publisher.publish(object())  # type: ignore[arg-type]


def test_preview_publishes_preview_before_configured_rejection() -> None:
    publisher = RecordingPublisher()
    planner = build_paper_order_planner(RiskLimits())
    service = PreviewTradeService(planner, publisher)

    result = service.preview(
        portfolio(),
        preview_request(entry="9", stop="8", target="11"),
    )

    assert result.approved is False
    assert result.correlation_id == CORRELATION_ID
    assert [type(event) for event in publisher.events] == [
        TradePreviewed,
        PolicyViolation,
        TradeRejected,
    ]
    violation = publisher.events[1]
    assert isinstance(violation, PolicyViolation)
    assert violation.policy == "MinimumPricePolicy"
    assert ("minimum_price", "10.0") in violation.configuration
    assert result.rejections[0].configuration == violation.configuration


def test_preview_and_submission_publish_one_correlated_lifecycle() -> None:
    publisher = RecordingPublisher()
    planner = build_paper_order_planner(RiskLimits())
    view = portfolio()
    request = preview_request()
    preview_result = PreviewTradeService(planner, publisher).preview(view, request)
    broker = RecordingExecutionBroker()
    pipeline = ExecutionPipeline(broker, planner=planner)
    submit_result = SubmitTradeService(planner, pipeline, publisher).submit(
        view,
        submit_request_from_preview(preview_result, request),
    )

    assert submit_result.submitted is True
    assert preview_result.correlation_id == submit_result.correlation_id
    assert [type(event) for event in publisher.events] == [
        TradePreviewed,
        TradeSubmitted,
    ]
    assert {event.correlation_id for event in publisher.events} == {CORRELATION_ID}
    assert len(broker.orders) == 1


def test_filled_order_publishes_submitted_then_filled_once() -> None:
    publisher = RecordingPublisher()
    planner = build_paper_order_planner(RiskLimits())
    view = portfolio()
    request = preview_request()
    preview_result = PreviewTradeService(planner).preview(view, request)
    broker = RecordingExecutionBroker(status=OrderStatus.FILLED)
    service = SubmitTradeService(
        planner,
        ExecutionPipeline(broker, planner=planner),
        publisher,
    )

    result = service.submit(
        view,
        submit_request_from_preview(preview_result, request),
    )

    assert result.submitted is True
    assert [type(event) for event in publisher.events] == [
        TradeSubmitted,
        TradeFilled,
    ]
    assert len({id(event) for event in publisher.events}) == 2


def test_plan_drift_publishes_drift_violation_rejection_in_order() -> None:
    publisher = RecordingPublisher()
    planner = build_paper_order_planner(RiskLimits())
    preview_view = portfolio()
    request = preview_request()
    preview_result = PreviewTradeService(planner).preview(preview_view, request)
    broker = RecordingExecutionBroker()
    service = SubmitTradeService(
        planner,
        ExecutionPipeline(broker, planner=planner),
        publisher,
    )

    result = service.submit(
        portfolio(buying_power=500.0),
        submit_request_from_preview(preview_result, request),
    )

    assert result.submitted is False
    assert result.correlation_id == CORRELATION_ID
    assert [type(event) for event in publisher.events] == [
        PlanDriftDetected,
        PolicyViolation,
        TradeRejected,
    ]
    assert publisher.events[1].correlation_id == CORRELATION_ID
    assert broker.orders == []


def test_broker_failure_publishes_one_trade_failed_event() -> None:
    publisher = RecordingPublisher()
    planner = build_paper_order_planner(RiskLimits())
    view = portfolio()
    request = preview_request()
    preview_result = PreviewTradeService(planner).preview(view, request)
    broker = RecordingExecutionBroker(error=RuntimeError("paper endpoint down"))
    service = SubmitTradeService(
        planner,
        ExecutionPipeline(broker, planner=planner),
        publisher,
    )

    result = service.submit(
        view,
        submit_request_from_preview(preview_result, request),
    )

    assert result.submitted is False
    assert result.rejections[0].policy == "BrokerExecution"
    assert [type(event) for event in publisher.events] == [TradeFailed]


def test_repeated_confirmation_does_not_republish_submission() -> None:
    publisher = RecordingPublisher()
    planner = build_paper_order_planner(RiskLimits())
    view = portfolio()
    request = preview_request()
    preview_result = PreviewTradeService(planner).preview(view, request)
    broker = RecordingExecutionBroker()
    service = SubmitTradeService(
        planner,
        ExecutionPipeline(broker, planner=planner),
        publisher,
    )
    submission = submit_request_from_preview(preview_result, request)

    first = service.submit(view, submission)
    second = service.submit(view, submission)

    assert first.submitted is True
    assert second.submitted is False
    assert [type(event) for event in publisher.events] == [
        TradeSubmitted,
        PolicyViolation,
        TradeRejected,
    ]
    assert sum(isinstance(event, TradeSubmitted) for event in publisher.events) == 1
    assert len(broker.orders) == 1


def test_streamlit_wires_one_correlation_id_to_preview_and_submission() -> None:
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")

    assert source.count("correlation_id=trade_correlation_id") == 2
