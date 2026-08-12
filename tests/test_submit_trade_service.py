"""Tests for deterministic application-level trade submission."""

from __future__ import annotations

from decimal import Decimal

from adapters.broker_portfolio_view import BrokerPortfolioView
from adapters.paper_order_composition import build_paper_order_planner
from broker.base import AccountSnapshot
from trading.risk_manager import RiskLimits
from volcanoes.application.services import (
    ExpectedTradePlan,
    SubmitTradeRequest,
    SubmitTradeService,
)
from volcanoes.domain import Order, OrderStatus, TradeIntent, TradeSide
from volcanoes.execution import Broker, ExecutionPipeline, TradePlanner


class RecordingBroker(Broker):
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
        order.broker_order_id = "paper-123"
        order.broker_status = self.status.value.lower()
        order.broker_message = "Paper broker response."
        if self.status is OrderStatus.REJECTED:
            order.rejection_reason = "Broker rejected the bracket."
        return order

    def get_cash_balance(self) -> Decimal:
        return Decimal("100000")

    def get_position_quantity(self, symbol: str) -> int:
        return 0


def portfolio(*, buying_power: float = 100_000.0) -> BrokerPortfolioView:
    return BrokerPortfolioView.from_snapshot(
        AccountSnapshot(
            equity=100_000.0,
            cash=buying_power,
            buying_power=buying_power,
        ),
        [],
    )


def intent() -> TradeIntent:
    return TradeIntent(
        symbol="AAPL",
        side=TradeSide.BUY,
        entry_price=Decimal("100"),
        stop_price=Decimal("95"),
    )


def request_for(
    planner: TradePlanner,
    view: BrokerPortfolioView,
    *,
    open_order_symbols: frozenset[str] = frozenset(),
) -> SubmitTradeRequest:
    trade_intent = intent()
    plan = planner.plan(
        view,
        trade_intent,
        target_price=Decimal("110"),
        open_order_symbols=open_order_symbols,
    )
    return SubmitTradeRequest(
        symbol=trade_intent.symbol,
        side=trade_intent.side,
        entry_price=trade_intent.entry_price,
        stop_price=trade_intent.stop_price,
        target_price=Decimal("110"),
        expected_plan=ExpectedTradePlan.from_plan(plan),
    )


def service_stack(
    broker: RecordingBroker,
) -> tuple[TradePlanner, SubmitTradeService]:
    planner = build_paper_order_planner(RiskLimits())
    pipeline = ExecutionPipeline(broker, planner=planner)
    return planner, SubmitTradeService(planner, pipeline)


def test_approved_request_submits_once_with_exact_plan_values() -> None:
    broker = RecordingBroker()
    planner, service = service_stack(broker)
    view = portfolio()
    request = request_for(planner, view)

    result = service.submit(view, request)

    assert result.submitted is True
    assert result.code == SubmitTradeService.SUBMITTED
    assert result.order_id == "paper-123"
    assert result.symbol == "AAPL"
    assert result.side is TradeSide.BUY
    assert result.quantity == request.expected_plan.quantity
    assert result.price == Decimal("100")
    assert result.stop_price == Decimal("95")
    assert result.target_price == Decimal("110")
    assert result.broker_status == "pending"
    assert result.message == "Paper broker response."
    assert result.plan is not None
    assert (
        ExpectedTradePlan.from_plan(
            result.plan,
            correlation_id=result.correlation_id,
        )
        == request.expected_plan
    )
    assert len(broker.orders) == 1


def test_rejected_plan_never_reaches_broker() -> None:
    broker = RecordingBroker()
    planner, service = service_stack(broker)
    view = portfolio()
    open_orders = frozenset({"AAPL"})
    request = request_for(planner, view, open_order_symbols=open_orders)

    result = service.submit(
        view,
        request,
        open_order_symbols=open_orders,
    )

    assert result.submitted is False
    assert result.code == "DUPLICATE_ORDER"
    assert broker.orders == []


def test_fresh_snapshot_plan_drift_rejects_without_submission() -> None:
    broker = RecordingBroker()
    planner, service = service_stack(broker)
    preview_view = portfolio()
    request = request_for(planner, preview_view)

    result = service.submit(portfolio(buying_power=500.0), request)

    assert result.submitted is False
    assert result.code == SubmitTradeService.PLAN_DRIFT
    assert "fresh account snapshot" in result.explanation
    assert "quantity" in result.explanation
    assert broker.orders == []


def test_same_immutable_request_cannot_submit_twice() -> None:
    broker = RecordingBroker()
    planner, service = service_stack(broker)
    view = portfolio()
    request = request_for(planner, view)

    first = service.submit(view, request)
    second = service.submit(view, request)

    assert first.submitted is True
    assert second.submitted is False
    assert second.code == SubmitTradeService.DUPLICATE_SUBMISSION
    assert len(broker.orders) == 1


def test_broker_rejection_is_explainably_mapped() -> None:
    broker = RecordingBroker(status=OrderStatus.REJECTED)
    planner, service = service_stack(broker)
    view = portfolio()

    result = service.submit(view, request_for(planner, view))

    assert result.submitted is False
    assert result.code == SubmitTradeService.BROKER_REJECTED
    assert result.explanation == "Broker rejected the bracket."
    assert result.broker_status == "rejected"
    assert len(broker.orders) == 1


def test_broker_exception_is_explainably_mapped_and_can_be_retried() -> None:
    broker = RecordingBroker(error=RuntimeError("paper endpoint unavailable"))
    planner, service = service_stack(broker)
    view = portfolio()
    request = request_for(planner, view)

    first = service.submit(view, request)
    broker.error = None
    second = service.submit(view, request)

    assert first.submitted is False
    assert first.code == SubmitTradeService.BROKER_ERROR
    assert first.explanation == "paper endpoint unavailable"
    assert second.submitted is True
    assert len(broker.orders) == 2


def test_invalid_request_is_rejected_without_broker_submission() -> None:
    broker = RecordingBroker()
    planner, service = service_stack(broker)
    view = portfolio()
    valid = request_for(planner, view)
    invalid = SubmitTradeRequest(
        symbol=valid.symbol,
        side=valid.side,
        entry_price=valid.entry_price,
        stop_price=valid.stop_price,
        target_price=Decimal("90"),
        expected_plan=valid.expected_plan,
    )

    result = service.submit(view, invalid)

    assert result.submitted is False
    assert result.code == SubmitTradeService.INVALID_REQUEST
    assert broker.orders == []


def test_service_requires_pipeline_to_share_exact_planner_instance() -> None:
    broker = RecordingBroker()
    planner = TradePlanner()
    other_planner = TradePlanner()

    try:
        SubmitTradeService(
            planner,
            ExecutionPipeline(broker, planner=other_planner),
        )
    except ValueError as error:
        assert "exact TradePlanner instance" in str(error)
    else:
        raise AssertionError("mismatched planners were accepted")
