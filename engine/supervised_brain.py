"""Scanner orchestration through the deterministic execution supervisor."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from hashlib import sha256
from time import monotonic_ns

from audit.trade_log import AuditLog
from engine.cycle_report import TradingCycleReport
from scanner_engine.automated_scanner import scan_market
from strategies.trend_momentum import StrategySignal
from volcanoes.application.operations import (
    CounterMetric,
    LatencyMetric,
    OperationalMetrics,
    fail_open,
)
from volcanoes.application.supervisor import (
    ExecutionMode,
    ExecutionRequest,
    ExecutionSnapshot,
    ExecutionSource,
    ExecutionSupervisor,
    TradeSide,
)


class SupervisedEduTraderBrain:
    """Turn scanner signals into supervised application requests."""

    def __init__(
        self,
        supervisor: ExecutionSupervisor,
        snapshot_provider: Callable[[], ExecutionSnapshot],
        audit_log: AuditLog | None = None,
        operational_metrics: OperationalMetrics | None = None,
    ) -> None:
        if not isinstance(supervisor, ExecutionSupervisor):
            raise TypeError("supervisor must be an ExecutionSupervisor instance.")
        if not callable(snapshot_provider):
            raise TypeError("snapshot_provider must be callable.")

        self._supervisor = supervisor
        self._snapshot_provider = snapshot_provider
        self.audit = audit_log or AuditLog()
        self._operational_metrics = fail_open(operational_metrics)

    def run_cycle(
        self,
        symbols: list[str],
        *,
        min_score: int = 80,
        max_new_trades: int = 3,
        submit_orders: bool = False,
    ) -> TradingCycleReport:
        """Scan once and route each qualified signal through the supervisor."""

        scan = scan_market(
            symbols,
            min_score=min_score,
            max_candidates=max_new_trades * 3,
        )
        report = TradingCycleReport(scan=scan)
        self._operational_metrics.increment(
            CounterMetric.SCANNER_SIGNALS,
            len(scan.qualified),
        )
        self.audit.write(
            "scan_completed",
            {
                "scanned": scan.scanned,
                "qualified": len(scan.qualified),
                "regime": scan.regime.label,
                "regime_score": scan.regime.score,
                "submit_orders": submit_orders,
            },
        )

        mode = ExecutionMode.SUBMIT if submit_orders else ExecutionMode.PREVIEW_ONLY
        for signal in scan.qualified:
            if len(report.submitted) >= max_new_trades:
                break

            started = monotonic_ns()
            try:
                snapshot = self._snapshot_provider()
                result = self._supervisor.execute(
                    snapshot.portfolio,
                    self._to_execution_request(signal, mode=mode),
                    open_order_symbols=snapshot.open_order_symbols,
                )
                self._operational_metrics.increment(CounterMetric.SCANNER_DECISIONS)
            finally:
                self._operational_metrics.observe_latency(
                    LatencyMetric.SCANNER_DECISION,
                    monotonic_ns() - started,
                )
            if not result.decision.approved:
                row: dict[str, object] = {
                    "symbol": signal.symbol,
                    "reasons": [result.decision.explanation],
                }
                report.rejected_by_risk.append(row)
                self.audit.write("risk_rejected", row)
                continue

            if submit_orders:
                submission = result.submission
                if submission is None or not submission.submitted:
                    raise RuntimeError(
                        "Approved supervised execution did not return a submission."
                    )
                row = {
                    "symbol": submission.symbol,
                    "quantity": submission.quantity,
                    "order_id": submission.order_id,
                }
                report.submitted.append(row)
                self.audit.write("paper_order_submitted", row)
            else:
                preview = result.preview
                if preview is None or not preview.approved:
                    raise RuntimeError(
                        "Approved supervised preview did not return a trade plan."
                    )
                report.submitted.append(
                    {
                        "symbol": signal.symbol,
                        "quantity": preview.quantity,
                        "order_id": "PREVIEW_ONLY",
                    }
                )

        return report

    @staticmethod
    def _to_execution_request(
        signal: StrategySignal,
        *,
        mode: ExecutionMode,
    ) -> ExecutionRequest:
        entry_price = Decimal(str(signal.entry_price))
        stop_price = Decimal(str(signal.stop_price))
        target_price = Decimal(str(signal.target_price))
        canonical = "|".join(
            (
                "scanner",
                mode.value,
                signal.symbol.strip().upper(),
                format(entry_price, "f"),
                format(stop_price, "f"),
                format(target_price, "f"),
            )
        )
        idempotency_key = f"scanner-{sha256(canonical.encode()).hexdigest()}"
        return ExecutionRequest(
            symbol=signal.symbol,
            side=TradeSide.BUY,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            idempotency_key=idempotency_key,
            source=ExecutionSource.AUTOMATION,
            mode=mode,
        )
