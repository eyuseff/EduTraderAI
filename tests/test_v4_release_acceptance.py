"""End-to-end acceptance tests for the unified v4.0 release candidate."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from threading import Lock

import pytest

from adapters.broker_portfolio_view import BrokerPortfolioView
from adapters.paper_broker_execution import PaperBrokerExecutionAdapter
from adapters.paper_order_composition import build_paper_order_planner
from adapters.paper_order_preview import preview_paper_order
from adapters.paper_order_submission import submit_paper_order
from adapters.scanner_execution import build_scanner_execution_runtime
from audit.trade_log import AuditLog
from broker.base import AccountSnapshot, BrokerOrder, BrokerPosition
from engine import brain as legacy_brain
from engine import supervised_brain
from engine.brain import EduTraderBrain
from engine.supervised_brain import SupervisedEduTraderBrain
from market.regime import MarketRegime
from scanner_engine.automated_scanner import ScanResult
from strategies.trend_momentum import StrategySignal
from trading.execution import PaperExecutionEngine
from trading.risk_manager import RiskDecision, RiskLimits, RiskManager, TradeProposal
from volcanoes.application.services import (
    ExpectedTradePlan,
    PreviewTradeRequest,
    PreviewTradeService,
    SubmitTradeRequest,
    SubmitTradeResult,
    SubmitTradeService,
)
from volcanoes.application.supervisor import (
    ExecutionAborted,
    ExecutionCompleted,
    ExecutionSkipped,
    ExecutionStarted,
)
from volcanoes.domain import TradeSide
from volcanoes.events import (
    DomainEvent,
    EventPublisher,
    PlanDriftDetected,
    PolicyViolation,
    TradeFailed,
    TradePreviewed,
    TradeRejected,
    TradeSubmitted,
)
from volcanoes.execution import ExecutionPipeline

CORRELATION_ID = "release-acceptance-correlation"


class RecordingPublisher(EventPublisher):
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []
        self._lock = Lock()

    def publish(self, event: DomainEvent) -> None:
        with self._lock:
            self.events.append(event)


class RecordingAuditLog(AuditLog):
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict]] = []

    def write(self, event: str, payload: dict) -> None:
        self.rows.append((event, payload))


@dataclass
class ControlledPaperBroker:
    """Deterministic root paper broker with controllable submission outcomes."""

    response_status: str = "accepted"
    submission_error: Exception | None = None

    name = "Controlled release broker"
    is_paper = True

    def __post_init__(self) -> None:
        self.account = AccountSnapshot(
            equity=100_000.0,
            cash=100_000.0,
            buying_power=100_000.0,
            daily_pnl=0.0,
            paper=True,
        )
        self.positions: list[BrokerPosition] = []
        self.orders: list[BrokerOrder] = []
        self.submissions: list[dict[str, object]] = []

    def get_account(self) -> AccountSnapshot:
        return self.account

    def get_positions(self) -> list[BrokerPosition]:
        return list(self.positions)

    def get_open_orders(self) -> list[BrokerOrder]:
        return list(self.orders)

    def submit_bracket_order(
        self,
        *,
        symbol: str,
        quantity: int,
        entry_price: float,
        stop_price: float,
        target_price: float,
    ) -> BrokerOrder:
        self.submissions.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "entry_price": entry_price,
                "stop_price": stop_price,
                "target_price": target_price,
            }
        )
        if self.submission_error is not None:
            raise self.submission_error

        order = BrokerOrder(
            order_id=f"release-{len(self.submissions)}",
            symbol=symbol,
            quantity=quantity,
            side="buy",
            status=self.response_status,
            order_type="bracket-limit",
            submitted_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            message=(
                "Controlled broker rejected the order."
                if self.response_status == "rejected"
                else "Controlled broker accepted the order."
            ),
        )
        if self.response_status in {"accepted", "new", "open"}:
            self.orders.append(order)
        return order

    def cancel_all_orders(self) -> int:
        raise AssertionError("acceptance test unexpectedly cancelled orders")

    def close_all_positions(self) -> int:
        raise AssertionError("acceptance test unexpectedly closed positions")


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


def signal(
    *,
    symbol: str = "AAPL",
    entry: float = 100.0,
    stop: float = 97.5,
    target: float = 105.0,
) -> StrategySignal:
    return StrategySignal(
        symbol=symbol,
        score=95,
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        average_volume=2_000_000.0,
        daily_change_pct=1.0,
        reasons=["Controlled release signal."],
    )


def scan(*signals: StrategySignal) -> ScanResult:
    return ScanResult(
        regime=MarketRegime("Bullish", 100, True, ["Trading gate open."]),
        qualified=list(signals),
        rejected=[],
        scanned=len(signals),
    )


def legacy_engine(broker: ControlledPaperBroker) -> PaperExecutionEngine:
    return PaperExecutionEngine(broker, RiskManager(RiskLimits()))


def deterministic_preview(
    broker: ControlledPaperBroker,
    *,
    trade: TradeProposal | None = None,
    publisher: EventPublisher | None = None,
    correlation_id: str = CORRELATION_ID,
) -> RiskDecision:
    engine = legacy_engine(broker)
    return preview_paper_order(
        broker=broker,
        proposal=trade or proposal(),
        limits=RiskLimits(),
        legacy_preview=engine.preview,
        use_deterministic_preview=True,
        development_mode=False,
        correlation_id=correlation_id,
        event_publisher=publisher,
    )


def submit_service_stack(
    broker: ControlledPaperBroker,
    publisher: RecordingPublisher,
) -> tuple[PreviewTradeService, SubmitTradeService]:
    planner = build_paper_order_planner(RiskLimits())
    preview_service = PreviewTradeService(planner, publisher)
    submit_service = SubmitTradeService(
        planner,
        ExecutionPipeline(
            PaperBrokerExecutionAdapter(broker),
            planner=planner,
        ),
        publisher,
    )
    return preview_service, submit_service


def canonical_request() -> PreviewTradeRequest:
    return PreviewTradeRequest(
        symbol="AAPL",
        side=TradeSide.BUY,
        entry_price=Decimal("100"),
        stop_price=Decimal("97.5"),
        target_price=Decimal("105"),
        correlation_id=CORRELATION_ID,
    )


def submission_request_from_preview(
    preview: object,
) -> SubmitTradeRequest:
    approved = getattr(preview, "approved")
    quantity = getattr(preview, "quantity")
    dollar_risk = getattr(preview, "dollar_risk")
    position_value = getattr(preview, "position_value")
    reasons = getattr(preview, "reasons")
    risk_code = getattr(preview, "risk_code")
    request = canonical_request()
    return SubmitTradeRequest(
        symbol=request.symbol,
        side=request.side,
        entry_price=request.entry_price,
        stop_price=request.stop_price,
        target_price=request.target_price,
        expected_plan=ExpectedTradePlan(
            approved=approved,
            quantity=quantity,
            dollar_risk=dollar_risk,
            position_value=position_value,
            reasons=reasons,
            risk_code=risk_code,
            correlation_id=CORRELATION_ID,
        ),
    )


def test_manual_approved_trade_reaches_root_broker_through_adapter() -> None:
    broker = ControlledPaperBroker()
    publisher = RecordingPublisher()
    displayed = deterministic_preview(broker, publisher=publisher)

    result = submit_paper_order(
        broker=broker,
        proposal=proposal(),
        displayed_preview=displayed,
        limits=RiskLimits(),
        confirmation="PAPER TRADE",
        legacy_submit=lambda *_: (_ for _ in ()).throw(
            AssertionError("legacy submission was selected")
        ),
        use_deterministic_submission=True,
        correlation_id=CORRELATION_ID,
        event_publisher=publisher,
    )

    assert isinstance(result, SubmitTradeResult)
    assert result.submitted is True
    assert result.order_id == "release-1"
    assert broker.submissions == [
        {
            "symbol": "AAPL",
            "quantity": displayed.quantity,
            "entry_price": 100.0,
            "stop_price": 97.5,
            "target_price": 105.0,
        }
    ]
    assert [type(event) for event in publisher.events] == [
        TradePreviewed,
        TradeSubmitted,
    ]
    assert {event.correlation_id for event in publisher.events} == {CORRELATION_ID}


def test_manual_policy_rejection_never_reaches_broker() -> None:
    broker = ControlledPaperBroker()
    publisher = RecordingPublisher()

    displayed = deterministic_preview(
        broker,
        trade=proposal(entry=9.0, stop=8.0, target=11.0),
        publisher=publisher,
    )

    assert displayed.approved is False
    assert broker.submissions == []
    assert [type(event) for event in publisher.events] == [
        TradePreviewed,
        PolicyViolation,
        TradeRejected,
    ]


def test_manual_plan_drift_rejects_before_broker_submission() -> None:
    broker = ControlledPaperBroker()
    publisher = RecordingPublisher()
    displayed = deterministic_preview(broker, publisher=publisher)
    broker.account = AccountSnapshot(
        equity=100_000.0,
        cash=500.0,
        buying_power=500.0,
        paper=True,
    )

    with pytest.raises(ValueError, match="changed the previewed plan"):
        submit_paper_order(
            broker=broker,
            proposal=proposal(),
            displayed_preview=displayed,
            limits=RiskLimits(),
            confirmation="PAPER TRADE",
            legacy_submit=lambda *_: (_ for _ in ()).throw(
                AssertionError("legacy submission was selected")
            ),
            use_deterministic_submission=True,
            correlation_id=CORRELATION_ID,
            event_publisher=publisher,
        )

    assert broker.submissions == []
    assert any(isinstance(event, PlanDriftDetected) for event in publisher.events)


def test_supervised_scanner_preview_only_has_no_broker_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = ControlledPaperBroker()
    publisher = RecordingPublisher()
    runtime = build_scanner_execution_runtime(
        broker,
        RiskLimits(),
        event_publisher=publisher,
    )
    brain = SupervisedEduTraderBrain(
        runtime.supervisor,
        runtime.snapshot_provider,
        RecordingAuditLog(),
    )
    monkeypatch.setattr(
        supervised_brain,
        "scan_market",
        lambda *args, **kwargs: scan(signal()),
    )

    report = brain.run_cycle(["AAPL"], submit_orders=False)

    assert report.submitted == [
        {"symbol": "AAPL", "quantity": 100, "order_id": "PREVIEW_ONLY"}
    ]
    assert broker.submissions == []
    assert [type(event) for event in publisher.events] == [
        ExecutionStarted,
        TradePreviewed,
        ExecutionCompleted,
    ]


def test_supervised_scanner_submission_maps_signal_to_broker_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = ControlledPaperBroker()
    publisher = RecordingPublisher()
    runtime = build_scanner_execution_runtime(
        broker,
        RiskLimits(),
        event_publisher=publisher,
    )
    brain = SupervisedEduTraderBrain(
        runtime.supervisor,
        runtime.snapshot_provider,
        RecordingAuditLog(),
    )
    monkeypatch.setattr(
        supervised_brain,
        "scan_market",
        lambda *args, **kwargs: scan(signal()),
    )

    report = brain.run_cycle(["AAPL"], submit_orders=True)

    assert report.submitted == [
        {"symbol": "AAPL", "quantity": 100, "order_id": "release-1"}
    ]
    assert broker.submissions[0] == {
        "symbol": "AAPL",
        "quantity": 100,
        "entry_price": 100.0,
        "stop_price": 97.5,
        "target_price": 105.0,
    }


def test_repeated_scanner_signal_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = ControlledPaperBroker()
    publisher = RecordingPublisher()
    runtime = build_scanner_execution_runtime(
        broker,
        RiskLimits(),
        event_publisher=publisher,
    )
    brain = SupervisedEduTraderBrain(
        runtime.supervisor,
        runtime.snapshot_provider,
        RecordingAuditLog(),
    )
    monkeypatch.setattr(
        supervised_brain,
        "scan_market",
        lambda *args, **kwargs: scan(signal()),
    )

    first = brain.run_cycle(["AAPL"], submit_orders=True)
    repeated = brain.run_cycle(["AAPL"], submit_orders=True)

    assert len(first.submitted) == 1
    assert repeated.submitted == []
    assert len(broker.submissions) == 1
    assert isinstance(publisher.events[-1], ExecutionSkipped)
    assert publisher.events[-1].code == "IDEMPOTENT_REPLAY"  # type: ignore[attr-defined]


def test_human_order_and_scanner_signal_collide_safely_on_open_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = ControlledPaperBroker()
    publisher = RecordingPublisher()
    displayed = deterministic_preview(broker, publisher=publisher)
    submit_paper_order(
        broker=broker,
        proposal=proposal(),
        displayed_preview=displayed,
        limits=RiskLimits(),
        confirmation="PAPER TRADE",
        legacy_submit=lambda *_: (_ for _ in ()).throw(
            AssertionError("legacy submission was selected")
        ),
        use_deterministic_submission=True,
        correlation_id=CORRELATION_ID,
        event_publisher=publisher,
    )
    runtime = build_scanner_execution_runtime(
        broker,
        RiskLimits(),
        event_publisher=publisher,
    )
    brain = SupervisedEduTraderBrain(
        runtime.supervisor,
        runtime.snapshot_provider,
        RecordingAuditLog(),
    )
    monkeypatch.setattr(
        supervised_brain,
        "scan_market",
        lambda *args, **kwargs: scan(signal()),
    )

    scanner_report = brain.run_cycle(["AAPL"], submit_orders=True)

    assert scanner_report.submitted == []
    assert len(broker.submissions) == 1
    assert any(
        isinstance(event, ExecutionAborted) and event.policy == "DuplicateOrderPolicy"
        for event in publisher.events
    )


@pytest.mark.parametrize(
    ("broker", "expected_code", "expected_event"),
    [
        (
            ControlledPaperBroker(response_status="rejected"),
            SubmitTradeService.BROKER_REJECTED,
            TradeRejected,
        ),
        (
            ControlledPaperBroker(submission_error=RuntimeError("broker offline")),
            SubmitTradeService.BROKER_ERROR,
            TradeFailed,
        ),
    ],
)
def test_broker_failure_modes_are_mapped_without_escape(
    broker: ControlledPaperBroker,
    expected_code: str,
    expected_event: type[DomainEvent],
) -> None:
    publisher = RecordingPublisher()
    preview_service, submit_service = submit_service_stack(broker, publisher)
    view = BrokerPortfolioView.from_broker(broker)
    preview = preview_service.preview(view, canonical_request())

    result = submit_service.submit(
        view,
        submission_request_from_preview(preview),
    )

    assert result.submitted is False
    assert result.code == expected_code
    assert len(broker.submissions) == 1
    assert any(isinstance(event, expected_event) for event in publisher.events)


def test_supervisor_and_service_events_reconstruct_one_correlation_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = ControlledPaperBroker()
    publisher = RecordingPublisher()
    runtime = build_scanner_execution_runtime(
        broker,
        RiskLimits(),
        event_publisher=publisher,
    )
    brain = SupervisedEduTraderBrain(
        runtime.supervisor,
        runtime.snapshot_provider,
        RecordingAuditLog(),
    )
    monkeypatch.setattr(
        supervised_brain,
        "scan_market",
        lambda *args, **kwargs: scan(signal()),
    )

    brain.run_cycle(["AAPL"], submit_orders=True)

    assert [type(event) for event in publisher.events] == [
        ExecutionStarted,
        TradePreviewed,
        TradeSubmitted,
        ExecutionCompleted,
    ]
    correlation_ids = {event.correlation_id for event in publisher.events}
    assert len(correlation_ids) == 1
    submitted = next(
        event for event in publisher.events if isinstance(event, TradeSubmitted)
    )
    completed = next(
        event for event in publisher.events if isinstance(event, ExecutionCompleted)
    )
    assert submitted.order_id == completed.order_id == "release-1"


def test_manual_and_scanner_legacy_rollbacks_remain_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manual_broker = ControlledPaperBroker()
    engine = legacy_engine(manual_broker)
    legacy_preview_calls: list[TradeProposal] = []

    def legacy_preview(trade: TradeProposal) -> RiskDecision:
        legacy_preview_calls.append(trade)
        return engine.preview(trade)

    displayed = preview_paper_order(
        broker=manual_broker,
        proposal=proposal(),
        limits=RiskLimits(),
        legacy_preview=legacy_preview,
        use_deterministic_preview=False,
        development_mode=False,
    )
    manual_order = submit_paper_order(
        broker=manual_broker,
        proposal=proposal(),
        displayed_preview=displayed,
        limits=RiskLimits(),
        confirmation="PAPER TRADE",
        legacy_submit=engine.submit,
        use_deterministic_submission=False,
    )

    scanner_broker = ControlledPaperBroker()
    scanner_engine = legacy_engine(scanner_broker)
    scanner_brain = EduTraderBrain(scanner_engine, RecordingAuditLog())
    monkeypatch.setattr(
        legacy_brain,
        "scan_market",
        lambda *args, **kwargs: scan(signal()),
    )
    scanner_report = scanner_brain.run_cycle(["AAPL"], submit_orders=True)

    assert legacy_preview_calls == [proposal()]
    assert isinstance(manual_order, BrokerOrder)
    assert len(manual_broker.submissions) == 1
    assert scanner_report.submitted == [
        {"symbol": "AAPL", "quantity": 100, "order_id": "release-1"}
    ]
    assert len(scanner_broker.submissions) == 1
