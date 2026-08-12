"""Measure reproducible v4.0 deterministic runtime latency baselines."""

# ruff: noqa: E402

from __future__ import annotations

import argparse
import json
import platform
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from statistics import median
from time import perf_counter_ns
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.broker_portfolio_view import BrokerPortfolioView
from adapters.paper_broker_execution import PaperBrokerExecutionAdapter
from adapters.paper_order_composition import build_paper_order_planner
from adapters.scanner_execution import build_scanner_execution_runtime
from audit.trade_log import AuditLog
from broker.base import AccountSnapshot, BrokerOrder, BrokerPosition
from engine import supervised_brain
from engine.supervised_brain import SupervisedEduTraderBrain
from market.regime import MarketRegime
from scanner_engine.automated_scanner import ScanResult
from strategies.trend_momentum import StrategySignal
from trading.risk_manager import RiskLimits
from volcanoes.application.services import (
    ExpectedTradePlan,
    PreviewTradeRequest,
    PreviewTradeService,
    SubmitTradeRequest,
    SubmitTradeService,
)
from volcanoes.application.supervisor import (
    ExecutionRequest,
    ExecutionSource,
    ExecutionSupervisor,
)
from volcanoes.domain import TradeIntent, TradeSide
from volcanoes.events import NullEventPublisher
from volcanoes.execution import ExecutionPipeline


class NoOpAuditLog(AuditLog):
    def __init__(self) -> None:
        pass

    def write(self, event: str, payload: dict) -> None:
        del event, payload


@dataclass
class BenchmarkBroker:
    """Zero-delay paper broker used only for deterministic baselines."""

    name = "Benchmark paper broker"
    is_paper = True

    def __post_init__(self) -> None:
        self.account = AccountSnapshot(
            equity=100_000.0,
            cash=100_000.0,
            buying_power=100_000.0,
            paper=True,
        )
        self.submissions = 0

    def get_account(self) -> AccountSnapshot:
        return self.account

    def get_positions(self) -> list[BrokerPosition]:
        return []

    def get_open_orders(self) -> list[BrokerOrder]:
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
        self.submissions += 1
        return BrokerOrder(
            order_id=f"benchmark-{self.submissions}",
            symbol=symbol,
            quantity=quantity,
            side="buy",
            status="accepted",
            order_type="bracket-limit",
            submitted_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            message="Zero-delay benchmark response.",
        )

    def cancel_all_orders(self) -> int:
        return 0

    def close_all_positions(self) -> int:
        return 0


def preview_request(correlation_id: str = "benchmark") -> PreviewTradeRequest:
    return PreviewTradeRequest(
        symbol="AAPL",
        side=TradeSide.BUY,
        entry_price=Decimal("100"),
        stop_price=Decimal("97.5"),
        target_price=Decimal("105"),
        correlation_id=correlation_id,
    )


def scanner_fixture(*args: object, **kwargs: object) -> ScanResult:
    del args, kwargs
    return ScanResult(
        regime=MarketRegime("Bullish", 100, True, ["Benchmark fixture."]),
        qualified=[
            StrategySignal(
                symbol="AAPL",
                score=95,
                entry_price=100.0,
                stop_price=97.5,
                target_price=105.0,
                average_volume=2_000_000.0,
                daily_change_pct=1.0,
                reasons=["Benchmark fixture."],
            )
        ],
        rejected=[],
        scanned=1,
    )


def percentile(values: list[float], percentile_value: float) -> float:
    index = max(0, min(len(values) - 1, round((len(values) - 1) * percentile_value)))
    return sorted(values)[index]


def measure(
    callables: list[Callable[[], object]], warmup: int
) -> dict[str, float | int]:
    samples: list[float] = []
    for index, operation in enumerate(callables):
        started = perf_counter_ns()
        operation()
        elapsed_microseconds = (perf_counter_ns() - started) / 1_000
        if index >= warmup:
            samples.append(elapsed_microseconds)
    return {
        "iterations": len(samples),
        "median_us": round(median(samples), 3),
        "p95_us": round(percentile(samples, 0.95), 3),
        "p99_us": round(percentile(samples, 0.99), 3),
    }


def build_submit_operation(index: int) -> Callable[[], object]:
    broker = BenchmarkBroker()
    planner = build_paper_order_planner(RiskLimits())
    publisher = NullEventPublisher()
    view = BrokerPortfolioView.from_broker(broker)
    preview = PreviewTradeService(planner, publisher).preview(
        view,
        preview_request(f"submit-{index}"),
    )
    service = SubmitTradeService(
        planner,
        ExecutionPipeline(
            PaperBrokerExecutionAdapter(broker),
            planner=planner,
        ),
        publisher,
    )
    request = preview_request(f"submit-{index}")
    command = SubmitTradeRequest(
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
    )
    return lambda: service.submit(view, command)


def build_supervisor_operation(index: int) -> Callable[[], object]:
    broker = BenchmarkBroker()
    planner = build_paper_order_planner(RiskLimits())
    publisher = NullEventPublisher()
    preview = PreviewTradeService(planner, publisher)
    submit = SubmitTradeService(
        planner,
        ExecutionPipeline(
            PaperBrokerExecutionAdapter(broker),
            planner=planner,
        ),
        publisher,
    )
    supervisor = ExecutionSupervisor(preview, submit, event_publisher=publisher)
    view = BrokerPortfolioView.from_broker(broker)
    request = ExecutionRequest(
        symbol="AAPL",
        side=TradeSide.BUY,
        entry_price=Decimal("100"),
        stop_price=Decimal("97.5"),
        target_price=Decimal("105"),
        idempotency_key=f"supervisor-{index}",
        source=ExecutionSource.AUTOMATION,
        correlation_id=f"supervisor-{index}",
    )
    return lambda: supervisor.execute(view, request)


def build_scanner_operation() -> Callable[[], object]:
    broker = BenchmarkBroker()
    runtime = build_scanner_execution_runtime(broker, RiskLimits())
    brain = SupervisedEduTraderBrain(
        runtime.supervisor,
        runtime.snapshot_provider,
        NoOpAuditLog(),
    )
    return lambda: brain.run_cycle(["AAPL"], submit_orders=True)


def benchmark(iterations: int, warmup: int) -> dict[str, object]:
    sample_count = iterations + warmup
    broker = BenchmarkBroker()
    planner = build_paper_order_planner(RiskLimits())
    view = BrokerPortfolioView.from_broker(broker)
    intent = TradeIntent(
        symbol="AAPL",
        side=TradeSide.BUY,
        entry_price=Decimal("100"),
        stop_price=Decimal("97.5"),
    )
    preview_service = PreviewTradeService(planner)
    request = preview_request()

    original_scan_market = supervised_brain.scan_market
    supervised_brain.scan_market = scanner_fixture
    try:
        results = {
            "trade_planner": measure(
                [
                    lambda: planner.plan(
                        view,
                        intent,
                        target_price=Decimal("105"),
                    )
                    for _ in range(sample_count)
                ],
                warmup,
            ),
            "preview_trade_service": measure(
                [
                    lambda: preview_service.preview(view, request)
                    for _ in range(sample_count)
                ],
                warmup,
            ),
            "submit_trade_service_no_broker_delay": measure(
                [build_submit_operation(index) for index in range(sample_count)],
                warmup,
            ),
            "execution_supervisor": measure(
                [build_supervisor_operation(index) for index in range(sample_count)],
                warmup,
            ),
            "scanner_signal_to_decision": measure(
                [build_scanner_operation() for _ in range(sample_count)],
                warmup,
            ),
        }
    finally:
        supervised_brain.scan_market = original_scan_market

    return {
        "release": "4.0.0-rc1",
        "units": "microseconds",
        "fixture": "100k equity, AAPL 100/97.5/105, zero-delay paper broker",
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor() or "unreported",
        },
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=300)
    parser.add_argument("--warmup", type=int, default=30)
    arguments = parser.parse_args()
    if arguments.iterations < 20:
        parser.error("--iterations must be at least 20")
    if arguments.warmup < 0:
        parser.error("--warmup cannot be negative")

    print(
        json.dumps(
            benchmark(arguments.iterations, arguments.warmup),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
