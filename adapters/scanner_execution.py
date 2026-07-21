"""Outer composition for supervised scanner execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from adapters.broker_portfolio_view import BrokerPortfolioView
from adapters.paper_broker_execution import PaperBrokerExecutionAdapter
from adapters.paper_order_composition import build_paper_order_planner
from broker.base import PaperBroker
from trading.risk_manager import RiskLimits
from volcanoes.application.operations import OperationalMetrics
from volcanoes.application.services import PreviewTradeService, SubmitTradeService
from volcanoes.application.supervisor import (
    CooldownPolicy,
    ExecutionSnapshot,
    ExecutionSupervisor,
)
from volcanoes.events import EventPublisher, NullEventPublisher
from volcanoes.execution import ExecutionPipeline


@dataclass(frozen=True, slots=True)
class BrokerExecutionSnapshotProvider:
    """Copy current read-only broker state for one supervised request."""

    broker: PaperBroker

    def __post_init__(self) -> None:
        if not isinstance(self.broker, PaperBroker):
            raise TypeError("broker must satisfy the PaperBroker protocol.")
        if not self.broker.is_paper:
            raise ValueError("Scanner automation requires a paper broker.")

    def __call__(self) -> ExecutionSnapshot:
        portfolio = BrokerPortfolioView.from_broker(self.broker)
        open_order_symbols = frozenset(
            order.symbol.strip().upper()
            for order in self.broker.get_open_orders()
            if order.symbol.strip()
        )
        return ExecutionSnapshot(
            portfolio=portfolio,
            open_order_symbols=open_order_symbols,
        )


@dataclass(frozen=True, slots=True)
class ScannerExecutionRuntime:
    """Long-lived supervisor and fresh-snapshot provider for the scanner UI."""

    supervisor: ExecutionSupervisor
    snapshot_provider: BrokerExecutionSnapshotProvider


def build_scanner_execution_runtime(
    broker: PaperBroker,
    limits: RiskLimits,
    *,
    event_publisher: EventPublisher | None = None,
    cooldown: timedelta = timedelta(0),
    operational_metrics: OperationalMetrics | None = None,
) -> ScannerExecutionRuntime:
    """Compose the deterministic scanner stack at the infrastructure edge."""

    publisher = event_publisher or NullEventPublisher()
    planner = build_paper_order_planner(limits)
    execution_broker = PaperBrokerExecutionAdapter(broker)
    preview_service = PreviewTradeService(
        planner,
        publisher,
        operational_metrics=operational_metrics,
    )
    submit_service = SubmitTradeService(
        planner,
        ExecutionPipeline(execution_broker, planner=planner),
        publisher,
        operational_metrics=operational_metrics,
    )
    supervisor = ExecutionSupervisor(
        preview_service,
        submit_service,
        cooldown_policy=CooldownPolicy(cooldown),
        event_publisher=publisher,
        operational_metrics=operational_metrics,
    )
    return ScannerExecutionRuntime(
        supervisor=supervisor,
        snapshot_provider=BrokerExecutionSnapshotProvider(broker),
    )
