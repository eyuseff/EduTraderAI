"""Integration coverage for scanner automation through ExecutionSupervisor."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from threading import Event, Lock, Thread

import pytest

from adapters.paper_broker_execution import PaperBrokerExecutionAdapter
from adapters.paper_order_composition import build_paper_order_planner
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
from trading.risk_manager import RiskLimits, RiskManager
from volcanoes.application.services import PreviewTradeService, SubmitTradeService
from volcanoes.application.supervisor import (
    ExecutionAborted,
    ExecutionCompleted,
    ExecutionSkipped,
    ExecutionStarted,
    ExecutionSupervisor,
)
from volcanoes.events import (
    DomainEvent,
    EventPublisher,
    PolicyViolation,
    TradePreviewed,
    TradeRejected,
    TradeSubmitted,
)
from volcanoes.execution import ExecutionPipeline

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RecordingPublisher(EventPublisher):
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:
        self.events.append(event)


class RecordingAuditLog(AuditLog):
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict]] = []

    def write(self, event: str, payload: dict) -> None:
        self.rows.append((event, payload))


class RecordingPaperBroker:
    name = "Scanner paper broker"
    is_paper = True

    def __init__(self) -> None:
        self.account = AccountSnapshot(
            equity=100_000.0,
            cash=100_000.0,
            buying_power=100_000.0,
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
        order = BrokerOrder(
            order_id=f"scanner-{len(self.submissions)}",
            symbol=symbol,
            quantity=quantity,
            side="buy",
            status="accepted",
            order_type="bracket-limit",
            submitted_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            message="Scanner paper order accepted.",
        )
        self.orders.append(order)
        return order

    def cancel_all_orders(self) -> int:
        raise AssertionError("scanner cancelled orders")

    def close_all_positions(self) -> int:
        raise AssertionError("scanner closed positions")


class BlockingPreviewTradeService(PreviewTradeService):
    def __init__(self, *args: object, entered: Event, release: Event) -> None:
        super().__init__(*args)  # type: ignore[arg-type]
        self.entered = entered
        self.release = release

    def preview(self, *args: object, **kwargs: object):
        self.entered.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("scanner concurrency test did not release preview")
        return super().preview(*args, **kwargs)  # type: ignore[arg-type]


@dataclass
class SequenceScan:
    scans: list[ScanResult]

    def __post_init__(self) -> None:
        self._lock = Lock()

    def __call__(self, *args: object, **kwargs: object) -> ScanResult:
        del args, kwargs
        with self._lock:
            return self.scans.pop(0)


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
        reasons=["Qualified scanner signal."],
    )


def scan(*signals: StrategySignal) -> ScanResult:
    return ScanResult(
        regime=MarketRegime("Bullish", 100, True, ["Trading gate open."]),
        qualified=list(signals),
        rejected=[],
        scanned=len(signals),
    )


def brain_stack(
    broker: RecordingPaperBroker,
    publisher: RecordingPublisher,
    *,
    cooldown: timedelta = timedelta(0),
) -> SupervisedEduTraderBrain:
    runtime = build_scanner_execution_runtime(
        broker,
        RiskLimits(),
        event_publisher=publisher,
        cooldown=cooldown,
    )
    return SupervisedEduTraderBrain(
        runtime.supervisor,
        runtime.snapshot_provider,
        RecordingAuditLog(),
    )


def test_identical_scans_execute_once_and_second_scan_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = RecordingPaperBroker()
    publisher = RecordingPublisher()
    brain = brain_stack(broker, publisher)
    monkeypatch.setattr(
        supervised_brain, "scan_market", lambda *args, **kwargs: scan(signal())
    )

    first = brain.run_cycle(["AAPL"], submit_orders=True)
    duplicate = brain.run_cycle(["AAPL"], submit_orders=True)

    assert first.submitted == [
        {"symbol": "AAPL", "quantity": 100, "order_id": "scanner-1"}
    ]
    assert duplicate.submitted == []
    assert duplicate.rejected_by_risk == [
        {
            "symbol": "AAPL",
            "reasons": ["The completed result for this idempotency key was replayed."],
        }
    ]
    assert len(broker.submissions) == 1
    assert sum(isinstance(event, TradeSubmitted) for event in publisher.events) == 1
    assert isinstance(brain.audit, RecordingAuditLog)
    assert [event for event, _ in brain.audit.rows] == [
        "scan_completed",
        "paper_order_submitted",
        "scan_completed",
        "risk_rejected",
    ]
    skipped = publisher.events[-1]
    assert isinstance(skipped, ExecutionSkipped)
    assert skipped.code == "IDEMPOTENT_REPLAY"
    configuration = dict(skipped.configuration)
    assert configuration["attempted_correlation_id"] != skipped.correlation_id


def test_preview_scan_uses_supervisor_without_broker_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = RecordingPaperBroker()
    publisher = RecordingPublisher()
    brain = brain_stack(broker, publisher)
    monkeypatch.setattr(
        supervised_brain, "scan_market", lambda *args, **kwargs: scan(signal())
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


def test_scanner_requests_are_subject_to_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = RecordingPaperBroker()
    publisher = RecordingPublisher()
    brain = brain_stack(broker, publisher, cooldown=timedelta(minutes=5))
    sequence = SequenceScan([scan(signal()), scan(signal(target=106.0))])
    monkeypatch.setattr(supervised_brain, "scan_market", sequence)

    first = brain.run_cycle(["AAPL"], submit_orders=True)
    blocked = brain.run_cycle(["AAPL"], submit_orders=True)

    assert len(first.submitted) == 1
    assert blocked.submitted == []
    assert len(broker.submissions) == 1
    skipped = publisher.events[-1]
    assert isinstance(skipped, ExecutionSkipped)
    assert skipped.code == "COOLDOWN_ACTIVE"


def test_scanner_requests_for_one_symbol_are_serialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = RecordingPaperBroker()
    publisher = RecordingPublisher()
    runtime = build_scanner_execution_runtime(
        broker,
        RiskLimits(),
        event_publisher=publisher,
    )
    planner = build_paper_order_planner(RiskLimits())
    entered = Event()
    release = Event()
    blocking_preview = BlockingPreviewTradeService(
        planner,
        publisher,
        entered=entered,
        release=release,
    )
    supervisor = ExecutionSupervisor(
        blocking_preview,
        SubmitTradeService(
            planner,
            ExecutionPipeline(
                PaperBrokerExecutionAdapter(broker),
                planner=planner,
            ),
            publisher,
        ),
        event_publisher=publisher,
    )
    brain = SupervisedEduTraderBrain(
        supervisor,
        runtime.snapshot_provider,
        RecordingAuditLog(),
    )
    sequence = SequenceScan([scan(signal()), scan(signal(target=106.0))])
    monkeypatch.setattr(supervised_brain, "scan_market", sequence)
    first_reports: list[object] = []
    first = Thread(
        target=lambda: first_reports.append(
            brain.run_cycle(["AAPL"], submit_orders=True)
        )
    )

    first.start()
    assert entered.wait(timeout=5)
    concurrent = brain.run_cycle(["AAPL"], submit_orders=True)
    release.set()
    first.join(timeout=5)

    assert concurrent.submitted == []
    assert any(
        isinstance(event, ExecutionSkipped) and event.code == "SYMBOL_BUSY"
        for event in publisher.events
    )
    assert len(first_reports) == 1
    assert len(broker.submissions) == 1


def test_policy_rejection_is_explainable_and_submits_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = RecordingPaperBroker()
    publisher = RecordingPublisher()
    brain = brain_stack(broker, publisher)
    monkeypatch.setattr(
        supervised_brain,
        "scan_market",
        lambda *args, **kwargs: scan(signal(entry=9.0, stop=8.0, target=11.0)),
    )

    report = brain.run_cycle(["AAPL"], submit_orders=True)

    assert report.submitted == []
    assert len(report.rejected_by_risk) == 1
    reasons = report.rejected_by_risk[0]["reasons"]
    assert isinstance(reasons, list)
    assert any("minimum" in str(reason).lower() for reason in reasons)
    assert broker.submissions == []
    assert [type(event) for event in publisher.events] == [
        ExecutionStarted,
        TradePreviewed,
        PolicyViolation,
        TradeRejected,
        ExecutionAborted,
    ]
    aborted = publisher.events[-1]
    assert isinstance(aborted, ExecutionAborted)
    assert aborted.policy == "MinimumPricePolicy"
    assert aborted.configuration


def test_success_events_share_one_scanner_correlation_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = RecordingPaperBroker()
    publisher = RecordingPublisher()
    brain = brain_stack(broker, publisher)
    monkeypatch.setattr(
        supervised_brain, "scan_market", lambda *args, **kwargs: scan(signal())
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
    assert next(iter(correlation_ids))


def test_app_defaults_to_supervised_scanner_and_keeps_legacy_rollback() -> None:
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments = {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance((target := node.targets[0]), ast.Name)
        and isinstance(node.value, ast.Constant)
    }

    assert assignments["USE_DETERMINISTIC_SCANNER"] is True
    assert "if USE_DETERMINISTIC_SCANNER:" in source
    assert "SupervisedEduTraderBrain(" in source
    assert "else:\n                brain = EduTraderBrain(engine)" in source
    assert "@st.cache_resource\ndef deterministic_scanner_runtime" in source


def test_rollback_brain_retains_legacy_scanner_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = RecordingPaperBroker()
    audit = RecordingAuditLog()
    brain = EduTraderBrain(
        PaperExecutionEngine(broker, RiskManager(RiskLimits())),
        audit,
    )
    monkeypatch.setattr(
        legacy_brain,
        "scan_market",
        lambda *args, **kwargs: scan(signal()),
    )

    report = brain.run_cycle(["AAPL"], submit_orders=True)

    assert report.submitted == [
        {"symbol": "AAPL", "quantity": 100, "order_id": "scanner-1"}
    ]
    assert len(broker.submissions) == 1
    assert [event for event, _ in audit.rows] == [
        "scan_completed",
        "paper_order_submitted",
    ]
