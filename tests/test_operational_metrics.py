"""Operational validation metrics and export tests."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from threading import Thread

import pytest

from adapters.broker_portfolio_view import BrokerPortfolioView
from adapters.paper_order_composition import build_paper_order_planner
from broker.base import AccountSnapshot
from engine import supervised_brain
from engine.supervised_brain import SupervisedEduTraderBrain
from market.regime import MarketRegime
from scanner_engine.automated_scanner import ScanResult
from strategies.trend_momentum import StrategySignal
from trading.risk_manager import RiskLimits
from volcanoes.application.operations import (
    CounterMetric,
    LatencyMetric,
    OperationalEventPublisher,
    OperationalMetrics,
    ProcessLocalOperationalMetrics,
    VerificationMetadata,
    build_operational_dashboard_snapshot,
    build_validation_snapshot,
    export_validation_snapshot,
    fail_open,
    serialize_validation_snapshot,
)
from volcanoes.application.platform import (
    BrokerMode,
    DeterministicFeatureFlags,
    PlatformConfiguration,
    ScannerExecutionMode,
    TradingPolicyConfiguration,
    build_platform_health_report,
)
from volcanoes.application.services import (
    ExpectedTradePlan,
    PreviewTradeRequest,
    PreviewTradeService,
    SubmitTradeRequest,
    SubmitTradeService,
)
from volcanoes.application.supervisor import (
    ExecutionDecision,
    ExecutionRequest,
    ExecutionResult,
    ExecutionSnapshot,
    ExecutionSource,
    ExecutionSupervisor,
)
from volcanoes.domain import Order, OrderStatus, TradeSide
from volcanoes.events import NullEventPublisher, TradeRejected
from volcanoes.execution import Broker, ExecutionPipeline


class RecordingBroker(Broker):
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.orders: list[Order] = []

    def submit_order(self, order: Order) -> Order:
        self.orders.append(order)
        if self.fail:
            raise RuntimeError("controlled paper failure")
        order.status = OrderStatus.PENDING
        order.broker_order_id = "metrics-order"
        order.broker_status = "accepted"
        return order

    def get_cash_balance(self) -> Decimal:
        return Decimal("100000")

    def get_position_quantity(self, symbol: str) -> int:
        del symbol
        return 0


class ExplodingMetrics(OperationalMetrics):
    def increment(self, metric: CounterMetric, amount: int = 1) -> None:
        del metric, amount
        raise RuntimeError("metrics unavailable")

    def observe_latency(self, metric: LatencyMetric, elapsed_ns: int) -> None:
        del metric, elapsed_ns
        raise RuntimeError("metrics unavailable")

    def snapshot(self):
        raise RuntimeError("metrics unavailable")


class NoOpAudit:
    def write(self, event: str, payload: dict[str, object]) -> None:
        del event, payload


def portfolio() -> BrokerPortfolioView:
    return BrokerPortfolioView.from_snapshot(
        AccountSnapshot(
            equity=100_000,
            cash=100_000,
            buying_power=100_000,
        ),
        [],
    )


def preview_request(
    correlation_id: str = "operational-validation",
) -> PreviewTradeRequest:
    return PreviewTradeRequest(
        symbol="AAPL",
        side=TradeSide.BUY,
        entry_price=Decimal("100"),
        stop_price=Decimal("97.5"),
        target_price=Decimal("105"),
        correlation_id=correlation_id,
    )


def test_counter_and_latency_aggregation_are_exact_and_immutable() -> None:
    metrics = ProcessLocalOperationalMetrics()
    metrics.increment(CounterMetric.PREVIEWS)
    metrics.increment(CounterMetric.PREVIEWS, 2)
    metrics.observe_latency(LatencyMetric.PREVIEW, 1_000_000)
    metrics.observe_latency(LatencyMetric.PREVIEW, 3_000_000)

    snapshot = metrics.snapshot()
    preview_latency = next(
        item for item in snapshot.latencies if item.name == LatencyMetric.PREVIEW
    )

    assert snapshot.counter(CounterMetric.PREVIEWS) == 3
    assert preview_latency.count == 2
    assert preview_latency.total_ms == 4
    assert preview_latency.minimum_ms == 1
    assert preview_latency.maximum_ms == 3
    assert preview_latency.mean_ms == 2
    with pytest.raises(FrozenInstanceError):
        preview_latency.count = 3  # type: ignore[misc]


def test_process_local_recording_is_thread_safe() -> None:
    metrics = ProcessLocalOperationalMetrics()

    def record() -> None:
        for _ in range(1_000):
            metrics.increment(CounterMetric.SCANNER_DECISIONS)

    threads = [Thread(target=record) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert metrics.snapshot().counter(CounterMetric.SCANNER_DECISIONS) == 8_000


def test_instrumentation_failure_fails_open_and_is_observable() -> None:
    metrics = fail_open(ExplodingMetrics())
    result = PreviewTradeService(
        build_paper_order_planner(RiskLimits()),
        operational_metrics=metrics,
    ).preview(portfolio(), preview_request())

    assert result.approved is True
    assert metrics.snapshot().counter(CounterMetric.INSTRUMENTATION_FAILURES) >= 3


def test_metrics_do_not_change_preview_or_submission_outcomes() -> None:
    planner = build_paper_order_planner(RiskLimits())
    view = portfolio()
    request = preview_request()
    baseline = PreviewTradeService(planner).preview(view, request)
    metrics = ProcessLocalOperationalMetrics()
    observed = PreviewTradeService(
        planner,
        operational_metrics=metrics,
    ).preview(view, request)

    assert observed == baseline

    broker = RecordingBroker()
    submission = SubmitTradeService(
        planner,
        ExecutionPipeline(broker, planner=planner),
        operational_metrics=metrics,
    ).submit(
        view,
        SubmitTradeRequest(
            symbol=request.symbol,
            side=request.side,
            entry_price=request.entry_price,
            stop_price=request.stop_price,
            target_price=request.target_price,
            expected_plan=ExpectedTradePlan(
                approved=baseline.approved,
                quantity=baseline.quantity,
                dollar_risk=baseline.dollar_risk,
                position_value=baseline.position_value,
                reasons=baseline.reasons,
                risk_code=baseline.risk_code,
                correlation_id=request.correlation_id,
            ),
        ),
    )

    assert submission.submitted is True
    assert submission.quantity == baseline.quantity
    assert len(broker.orders) == 1
    snapshot = metrics.snapshot()
    assert snapshot.counter(CounterMetric.PREVIEWS) == 1
    assert snapshot.counter(CounterMetric.APPROVED_PLANS) == 1
    assert snapshot.counter(CounterMetric.SUBMISSIONS) == 1


def test_broker_failures_and_event_attempts_are_counted() -> None:
    metrics = ProcessLocalOperationalMetrics()
    planner = build_paper_order_planner(RiskLimits())
    view = portfolio()
    preview = PreviewTradeService(planner).preview(view, preview_request())
    request = preview_request()
    service = SubmitTradeService(
        planner,
        ExecutionPipeline(RecordingBroker(fail=True), planner=planner),
        operational_metrics=metrics,
    )

    result = service.submit(
        view,
        SubmitTradeRequest(
            symbol=request.symbol,
            side=request.side,
            entry_price=request.entry_price,
            stop_price=request.stop_price,
            target_price=request.target_price,
            expected_plan=ExpectedTradePlan(
                approved=preview.approved,
                quantity=preview.quantity,
                dollar_risk=preview.dollar_risk,
                position_value=preview.position_value,
                reasons=preview.reasons,
                risk_code=preview.risk_code,
                correlation_id=request.correlation_id,
            ),
        ),
    )
    publisher = OperationalEventPublisher(NullEventPublisher(), metrics)
    publisher.publish(
        TradeRejected(
            correlation_id="event-attempt",
            operation="test",
            symbol="",
            policy="TestPolicy",
            explanation="Controlled rejection.",
        )
    )

    snapshot = metrics.snapshot()
    assert result.code == SubmitTradeService.BROKER_ERROR
    assert snapshot.counter(CounterMetric.BROKER_FAILURES) == 1
    assert snapshot.counter(CounterMetric.EVENT_PUBLICATION_ATTEMPTS) == 1


def test_idempotent_replay_does_not_duplicate_submission_metrics() -> None:
    metrics = ProcessLocalOperationalMetrics()
    planner = build_paper_order_planner(RiskLimits())
    broker = RecordingBroker()
    preview_service = PreviewTradeService(
        planner,
        operational_metrics=metrics,
    )
    submit_service = SubmitTradeService(
        planner,
        ExecutionPipeline(broker, planner=planner),
        operational_metrics=metrics,
    )
    supervisor = ExecutionSupervisor(
        preview_service,
        submit_service,
        operational_metrics=metrics,
    )
    request = ExecutionRequest(
        symbol="AAPL",
        side=TradeSide.BUY,
        entry_price=Decimal("100"),
        stop_price=Decimal("97.5"),
        target_price=Decimal("105"),
        idempotency_key="operational-replay",
        source=ExecutionSource.HUMAN,
        correlation_id="operational-replay",
    )

    first = supervisor.execute(portfolio(), request)
    replay = supervisor.execute(portfolio(), request)

    snapshot = metrics.snapshot()
    assert first.submitted is True
    assert replay.replayed is True
    assert snapshot.counter(CounterMetric.SUBMISSIONS) == 1
    assert snapshot.counter(CounterMetric.PREVIEWS) == 1
    assert snapshot.counter(CounterMetric.IDEMPOTENT_REPLAYS) == 1
    assert len(broker.orders) == 1


@pytest.mark.parametrize(
    ("code", "metric"),
    [
        ("IDEMPOTENCY_CONFLICT", CounterMetric.IDEMPOTENCY_CONFLICTS),
        ("DUPLICATE_EXECUTION", CounterMetric.DUPLICATE_EXECUTIONS),
        ("SYMBOL_BUSY", CounterMetric.SYMBOL_BUSY_REJECTIONS),
        ("COOLDOWN_ACTIVE", CounterMetric.COOLDOWN_REJECTIONS),
    ],
)
def test_supervisor_rejection_codes_map_to_one_counter(
    code: str,
    metric: CounterMetric,
) -> None:
    metrics = ProcessLocalOperationalMetrics()
    planner = build_paper_order_planner(RiskLimits())
    broker = RecordingBroker()
    supervisor = ExecutionSupervisor(
        PreviewTradeService(planner),
        SubmitTradeService(
            planner,
            ExecutionPipeline(broker, planner=planner),
        ),
        operational_metrics=metrics,
    )
    request = ExecutionRequest(
        symbol="AAPL",
        side=TradeSide.BUY,
        entry_price=Decimal("100"),
        stop_price=Decimal("97.5"),
        target_price=Decimal("105"),
        idempotency_key=f"mapping-{code}",
        source=ExecutionSource.HUMAN,
    )

    supervisor._record_decision(  # noqa: SLF001 - focused instrumentation seam
        ExecutionResult(
            request=request,
            decision=ExecutionDecision(
                approved=False,
                code=code,
                policy="TestPolicy",
                explanation="Controlled mapping test.",
                correlation_id=request.correlation_id,
            ),
        )
    )

    assert metrics.snapshot().counter(metric) == 1


def test_plan_drift_is_counted_without_broker_submission() -> None:
    metrics = ProcessLocalOperationalMetrics()
    planner = build_paper_order_planner(RiskLimits())
    broker = RecordingBroker()
    original_view = portfolio()
    request = preview_request("drift-metric")
    preview = PreviewTradeService(planner).preview(original_view, request)
    drifted_view = BrokerPortfolioView.from_snapshot(
        AccountSnapshot(equity=100_000, cash=500, buying_power=500),
        [],
    )
    result = SubmitTradeService(
        planner,
        ExecutionPipeline(broker, planner=planner),
        operational_metrics=metrics,
    ).submit(
        drifted_view,
        SubmitTradeRequest(
            symbol=request.symbol,
            side=request.side,
            entry_price=request.entry_price,
            stop_price=request.stop_price,
            target_price=request.target_price,
            expected_plan=ExpectedTradePlan(
                approved=preview.approved,
                quantity=preview.quantity,
                dollar_risk=preview.dollar_risk,
                position_value=preview.position_value,
                reasons=preview.reasons,
                risk_code=preview.risk_code,
                correlation_id=request.correlation_id,
            ),
        ),
    )

    assert result.code == SubmitTradeService.PLAN_DRIFT
    assert metrics.snapshot().counter(CounterMetric.PLAN_DRIFT) == 1
    assert broker.orders == []


def test_scanner_signals_decisions_and_latency_are_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metrics = ProcessLocalOperationalMetrics()
    planner = build_paper_order_planner(RiskLimits())
    broker = RecordingBroker()
    supervisor = ExecutionSupervisor(
        PreviewTradeService(planner, operational_metrics=metrics),
        SubmitTradeService(
            planner,
            ExecutionPipeline(broker, planner=planner),
            operational_metrics=metrics,
        ),
        operational_metrics=metrics,
    )
    monkeypatch.setattr(
        supervised_brain,
        "scan_market",
        lambda *args, **kwargs: ScanResult(
            regime=MarketRegime("Bullish", 100, True, ["Controlled fixture."]),
            qualified=[
                StrategySignal(
                    symbol="MSFT",
                    score=95,
                    entry_price=100,
                    stop_price=97.5,
                    target_price=105,
                    average_volume=2_000_000,
                    daily_change_pct=1,
                    reasons=["Controlled fixture."],
                )
            ],
            rejected=[],
            scanned=1,
        ),
    )
    brain = SupervisedEduTraderBrain(
        supervisor,
        lambda: ExecutionSnapshot(portfolio()),
        NoOpAudit(),  # type: ignore[arg-type]
        operational_metrics=metrics,
    )

    report = brain.run_cycle(["MSFT"], submit_orders=False)

    snapshot = metrics.snapshot()
    scanner_latency = next(
        item
        for item in snapshot.latencies
        if item.name == LatencyMetric.SCANNER_DECISION
    )
    assert report.submitted[0]["order_id"] == "PREVIEW_ONLY"
    assert snapshot.counter(CounterMetric.SCANNER_SIGNALS) == 1
    assert snapshot.counter(CounterMetric.SCANNER_DECISIONS) == 1
    assert scanner_latency.count == 1
    assert broker.orders == []


def test_dashboard_composition_and_validation_export_are_sanitized(
    tmp_path: Path,
) -> None:
    health = build_platform_health_report(
        PlatformConfiguration(
            feature_flags=DeterministicFeatureFlags(),
            policy=TradingPolicyConfiguration(),
            broker_mode=BrokerMode.SIMULATED_PAPER,
            scanner_execution_mode=ScannerExecutionMode.SUPERVISED,
        ),
        event_publisher_type="NullEventPublisher",
    )
    metrics = ProcessLocalOperationalMetrics()
    metrics.increment(CounterMetric.PREVIEWS, 4)
    verification = VerificationMetadata(
        status="PASS",
        command="make verify",
        test_count=380,
        combined_coverage_percent=80.0,
    )
    dashboard = build_operational_dashboard_snapshot(
        health,
        metrics.snapshot(),
        verification,
    )
    validation = build_validation_snapshot(
        "4.0.0-rc1",
        dashboard,
        timestamp=datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
    )

    encoded = serialize_validation_snapshot(validation)
    destination = export_validation_snapshot(tmp_path / "validation.json", validation)
    payload = json.loads(destination.read_text(encoding="utf-8"))

    assert payload["application_version"] == "4.0.0-rc1"
    assert payload["active_feature_flags"] == {
        "preview": True,
        "scanner": True,
        "submission": True,
    }
    assert payload["metrics"]["counters"]["previews"] == 4
    assert payload["verification"]["status"] == "PASS"
    for forbidden in ("api_key", "secret", "password", "account_id"):
        assert forbidden not in encoded.lower()


def test_validation_metadata_rejects_untrusted_commands() -> None:
    with pytest.raises(ValueError, match="make verify"):
        VerificationMetadata(
            status="PASS",
            command="curl example.invalid?api_key=not-allowed",
        )
