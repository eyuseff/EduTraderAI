"""Tests for safe supervisory execution orchestration."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from threading import Event, Thread

import pytest

from adapters.broker_portfolio_view import BrokerPortfolioView
from adapters.paper_order_composition import build_paper_order_planner
from broker.base import AccountSnapshot
from trading.risk_manager import RiskLimits
from volcanoes.application.services import PreviewTradeService, SubmitTradeService
from volcanoes.application.supervisor import (
    ConcurrentSymbolPolicy,
    CooldownPolicy,
    DuplicateExecutionPolicy,
    ExecutionAborted,
    ExecutionCompleted,
    ExecutionMode,
    ExecutionRequest,
    ExecutionSkipped,
    ExecutionSource,
    ExecutionStarted,
    ExecutionSupervisor,
    MarketStatePolicy,
)
from volcanoes.domain import Order, OrderStatus, TradeSide
from volcanoes.events import (
    DomainEvent,
    EventPublisher,
    PolicyViolation,
    TradePreviewed,
    TradeRejected,
    TradeSubmitted,
)
from volcanoes.execution import Broker, ExecutionPipeline

CORRELATION_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class RecordingPublisher(EventPublisher):
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:
        self.events.append(event)


class RecordingBroker(Broker):
    def __init__(self) -> None:
        self.orders: list[Order] = []

    def submit_order(self, order: Order) -> Order:
        self.orders.append(order)
        order.status = OrderStatus.PENDING
        order.broker_order_id = f"supervised-{len(self.orders)}"
        order.broker_status = "accepted"
        order.broker_message = "Supervised paper execution."
        return order

    def get_cash_balance(self) -> Decimal:
        return Decimal("100000")

    def get_position_quantity(self, symbol: str) -> int:
        return 0


class MutableClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, duration: timedelta) -> None:
        self.now += duration


class BlockingPreviewTradeService(PreviewTradeService):
    def __init__(
        self,
        *args: object,
        entered: Event,
        release: Event,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._entered = entered
        self._release = release

    def preview(self, *args: object, **kwargs: object):
        self._entered.set()
        if not self._release.wait(timeout=5):
            raise TimeoutError("concurrency test did not release preview")
        return super().preview(*args, **kwargs)  # type: ignore[arg-type]


def portfolio() -> BrokerPortfolioView:
    return BrokerPortfolioView.from_snapshot(
        AccountSnapshot(
            equity=100_000.0,
            cash=100_000.0,
            buying_power=100_000.0,
        ),
        [],
    )


def execution_request(
    *,
    symbol: str = "AAPL",
    entry: str = "100",
    stop: str = "97.5",
    target: str = "105",
    idempotency_key: str = "request-1",
    correlation_id: str = CORRELATION_ID,
    market_state: str | None = None,
    source: ExecutionSource = ExecutionSource.HUMAN,
    mode: ExecutionMode = ExecutionMode.SUBMIT,
) -> ExecutionRequest:
    return ExecutionRequest(
        symbol=symbol,
        side=TradeSide.BUY,
        entry_price=Decimal(entry),
        stop_price=Decimal(stop),
        target_price=Decimal(target),
        idempotency_key=idempotency_key,
        source=source,
        mode=mode,
        correlation_id=correlation_id,
        market_state=market_state,
    )


def supervisor_stack(
    *,
    publisher: RecordingPublisher | None = None,
    cooldown: timedelta = timedelta(0),
    clock: MutableClock | None = None,
    preview_service: PreviewTradeService | None = None,
    market_policy: MarketStatePolicy | None = None,
) -> tuple[ExecutionSupervisor, RecordingBroker, RecordingPublisher]:
    events = publisher or RecordingPublisher()
    planner = (
        preview_service.planner
        if preview_service is not None
        else build_paper_order_planner(RiskLimits())
    )
    broker = RecordingBroker()
    preview = preview_service or PreviewTradeService(planner, events)
    submit = SubmitTradeService(
        planner,
        ExecutionPipeline(broker, planner=planner),
        events,
    )
    supervisor = ExecutionSupervisor(
        preview,
        submit,
        cooldown_policy=CooldownPolicy(cooldown),
        market_state_policy=market_policy,
        event_publisher=events,
        clock=clock or MutableClock(),
    )
    return supervisor, broker, events


@pytest.mark.parametrize(
    "source",
    [ExecutionSource.HUMAN, ExecutionSource.AUTOMATION],
)
def test_successful_execution_invokes_services_and_publishes_in_order(
    source: ExecutionSource,
) -> None:
    supervisor, broker, publisher = supervisor_stack()

    result = supervisor.execute(
        portfolio(),
        execution_request(source=source),
    )

    assert result.submitted is True
    assert result.decision.code == "EXECUTION_COMPLETED"
    assert result.preview is not None
    assert result.submission is not None
    assert [type(event) for event in publisher.events] == [
        ExecutionStarted,
        TradePreviewed,
        TradeSubmitted,
        ExecutionCompleted,
    ]
    assert {event.correlation_id for event in publisher.events} == {CORRELATION_ID}
    started = publisher.events[0]
    assert isinstance(started, ExecutionStarted)
    assert started.source == source.value
    assert len(broker.orders) == 1


def test_preview_rejection_aborts_without_submission() -> None:
    supervisor, broker, publisher = supervisor_stack()

    result = supervisor.execute(
        portfolio(),
        execution_request(entry="9", stop="8", target="11"),
    )

    assert result.submitted is False
    assert result.decision.policy == "MinimumPricePolicy"
    assert result.decision.configuration
    assert [type(event) for event in publisher.events] == [
        ExecutionStarted,
        TradePreviewed,
        PolicyViolation,
        TradeRejected,
        ExecutionAborted,
    ]
    assert broker.orders == []


def test_preview_only_mode_completes_without_submission() -> None:
    supervisor, broker, publisher = supervisor_stack()

    result = supervisor.execute(
        portfolio(),
        execution_request(mode=ExecutionMode.PREVIEW_ONLY),
    )

    assert result.decision.approved is True
    assert result.decision.code == "PREVIEW_COMPLETED"
    assert result.preview is not None
    assert result.preview.quantity == 100
    assert result.submission is None
    assert result.submitted is False
    assert broker.orders == []
    assert [type(event) for event in publisher.events] == [
        ExecutionStarted,
        TradePreviewed,
        ExecutionCompleted,
    ]
    completed = publisher.events[-1]
    assert isinstance(completed, ExecutionCompleted)
    assert completed.order_id is None
    assert completed.quantity == 100


def test_completed_idempotency_key_replays_without_reexecution() -> None:
    supervisor, broker, publisher = supervisor_stack()
    request = execution_request()

    first = supervisor.execute(portfolio(), request)
    replay = supervisor.execute(portfolio(), request)

    assert first.submitted is True
    assert replay.submitted is True
    assert replay.replayed is True
    assert replay.decision.code == "IDEMPOTENT_REPLAY"
    assert replay.correlation_id == first.correlation_id
    assert sum(isinstance(event, TradeSubmitted) for event in publisher.events) == 1
    assert isinstance(publisher.events[-1], ExecutionSkipped)
    assert len(broker.orders) == 1


def test_idempotency_key_cannot_be_reused_for_different_request() -> None:
    supervisor, broker, _ = supervisor_stack()
    supervisor.execute(portfolio(), execution_request())

    conflict = supervisor.execute(
        portfolio(),
        execution_request(
            symbol="MSFT",
            idempotency_key="request-1",
            correlation_id="different-correlation",
        ),
    )

    assert conflict.submitted is False
    assert conflict.decision.code == "IDEMPOTENCY_CONFLICT"
    assert len(broker.orders) == 1


def test_duplicate_execution_with_new_key_is_rejected() -> None:
    supervisor, broker, publisher = supervisor_stack()
    supervisor.execute(portfolio(), execution_request())

    duplicate = supervisor.execute(
        portfolio(),
        execution_request(
            idempotency_key="request-2",
            correlation_id="duplicate-correlation",
        ),
    )

    assert duplicate.submitted is False
    assert duplicate.decision.code == "DUPLICATE_EXECUTION"
    assert duplicate.decision.policy == "DuplicateExecutionPolicy"
    assert isinstance(publisher.events[-1], ExecutionSkipped)
    assert len(broker.orders) == 1


def test_cooldown_blocks_then_allows_distinct_request() -> None:
    clock = MutableClock()
    supervisor, broker, _ = supervisor_stack(
        cooldown=timedelta(minutes=5),
        clock=clock,
    )
    supervisor.execute(portfolio(), execution_request())
    second = execution_request(
        target="106",
        idempotency_key="request-2",
        correlation_id="cooldown-correlation",
    )

    blocked = supervisor.execute(portfolio(), second)
    clock.advance(timedelta(minutes=6))
    allowed = supervisor.execute(portfolio(), second)

    assert blocked.decision.code == "COOLDOWN_ACTIVE"
    assert blocked.decision.policy == "CooldownPolicy"
    assert allowed.submitted is True
    assert len(broker.orders) == 2


def test_concurrent_requests_for_same_symbol_never_overlap() -> None:
    entered = Event()
    release = Event()
    publisher = RecordingPublisher()
    planner = build_paper_order_planner(RiskLimits())
    blocking_preview = BlockingPreviewTradeService(
        planner,
        publisher,
        entered=entered,
        release=release,
    )
    supervisor, broker, _ = supervisor_stack(
        publisher=publisher,
        preview_service=blocking_preview,
    )
    first_result: list[object] = []

    thread = Thread(
        target=lambda: first_result.append(
            supervisor.execute(portfolio(), execution_request())
        )
    )
    thread.start()
    assert entered.wait(timeout=5)

    concurrent = supervisor.execute(
        portfolio(),
        execution_request(
            target="106",
            idempotency_key="request-2",
            correlation_id="concurrent-correlation",
        ),
    )
    release.set()
    thread.join(timeout=5)

    assert concurrent.submitted is False
    assert concurrent.decision.code == "SYMBOL_BUSY"
    assert concurrent.decision.policy == "ConcurrentSymbolPolicy"
    assert len(first_result) == 1
    assert len(broker.orders) == 1


def test_market_state_stub_can_fail_closed_without_invoking_services() -> None:
    supervisor, broker, publisher = supervisor_stack(
        market_policy=MarketStatePolicy(require_open=True)
    )

    result = supervisor.execute(
        portfolio(),
        execution_request(market_state="CLOSED"),
    )

    assert result.submitted is False
    assert result.decision.code == "MARKET_STATE_BLOCKED"
    assert [type(event) for event in publisher.events] == [ExecutionSkipped]
    assert broker.orders == []


@pytest.mark.parametrize(
    "value",
    [
        CooldownPolicy(timedelta(seconds=30)),
        DuplicateExecutionPolicy(),
        ConcurrentSymbolPolicy(),
        MarketStatePolicy(),
        execution_request(),
    ],
)
def test_supervisor_policies_and_contracts_are_immutable(value: object) -> None:
    with pytest.raises(FrozenInstanceError):
        value.changed = True  # type: ignore[attr-defined]
