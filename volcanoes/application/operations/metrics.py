"""Process-local operational metrics contracts and recording implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock


class CounterMetric(StrEnum):
    """Fixed-cardinality counters for release-candidate observation."""

    PREVIEWS = "previews"
    APPROVED_PLANS = "approved_plans"
    REJECTED_PLANS = "rejected_plans"
    SUBMISSIONS = "submissions"
    BROKER_FAILURES = "broker_failures"
    PLAN_DRIFT = "plan_drift"
    IDEMPOTENT_REPLAYS = "idempotent_replays"
    IDEMPOTENCY_CONFLICTS = "idempotency_conflicts"
    DUPLICATE_EXECUTIONS = "duplicate_executions"
    SYMBOL_BUSY_REJECTIONS = "symbol_busy_rejections"
    COOLDOWN_REJECTIONS = "cooldown_rejections"
    SCANNER_SIGNALS = "scanner_signals"
    SCANNER_DECISIONS = "scanner_decisions"
    EVENT_PUBLICATION_ATTEMPTS = "event_publication_attempts"
    INSTRUMENTATION_FAILURES = "instrumentation_failures"


class LatencyMetric(StrEnum):
    """Fixed-cardinality latency observations measured with monotonic clocks."""

    PREVIEW = "preview"
    SUBMISSION = "submission"
    SUPERVISOR = "supervisor"
    SCANNER_DECISION = "scanner_decision"
    EVENT_PUBLICATION = "event_publication"


@dataclass(frozen=True, slots=True)
class LatencySummary:
    """Immutable aggregate for one latency metric."""

    name: str
    count: int
    total_ms: float
    minimum_ms: float
    maximum_ms: float
    mean_ms: float

    def to_dict(self) -> dict[str, int | float | str]:
        return {
            "name": self.name,
            "count": self.count,
            "total_ms": self.total_ms,
            "minimum_ms": self.minimum_ms,
            "maximum_ms": self.maximum_ms,
            "mean_ms": self.mean_ms,
        }


@dataclass(frozen=True, slots=True)
class OperationalMetricsSnapshot:
    """Immutable copy of current process-local operational measurements."""

    counters: tuple[tuple[str, int], ...]
    latencies: tuple[LatencySummary, ...]

    def counter(self, metric: CounterMetric) -> int:
        return dict(self.counters)[metric.value]

    def to_dict(self) -> dict[str, object]:
        return {
            "counters": dict(self.counters),
            "latencies": [summary.to_dict() for summary in self.latencies],
        }


class OperationalMetrics(ABC):
    """Presentation-neutral port for observational metrics."""

    @abstractmethod
    def increment(self, metric: CounterMetric, amount: int = 1) -> None:
        """Increment one fixed counter."""

    @abstractmethod
    def observe_latency(self, metric: LatencyMetric, elapsed_ns: int) -> None:
        """Record one monotonic duration in nanoseconds."""

    @abstractmethod
    def snapshot(self) -> OperationalMetricsSnapshot:
        """Return an immutable point-in-time copy."""


class _LatencyAccumulator:
    __slots__ = ("count", "maximum_ns", "minimum_ns", "total_ns")

    def __init__(self) -> None:
        self.count = 0
        self.total_ns = 0
        self.minimum_ns = 0
        self.maximum_ns = 0

    def observe(self, elapsed_ns: int) -> None:
        self.count += 1
        self.total_ns += elapsed_ns
        if self.count == 1:
            self.minimum_ns = elapsed_ns
            self.maximum_ns = elapsed_ns
        else:
            self.minimum_ns = min(self.minimum_ns, elapsed_ns)
            self.maximum_ns = max(self.maximum_ns, elapsed_ns)


class ProcessLocalOperationalMetrics(OperationalMetrics):
    """Thread-safe, bounded process-local metrics recorder."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters = {metric: 0 for metric in CounterMetric}
        self._latencies = {metric: _LatencyAccumulator() for metric in LatencyMetric}

    def increment(self, metric: CounterMetric, amount: int = 1) -> None:
        if not isinstance(metric, CounterMetric):
            raise TypeError("metric must be a CounterMetric value.")
        if not isinstance(amount, int) or amount < 0:
            raise ValueError("amount must be a non-negative integer.")
        with self._lock:
            self._counters[metric] += amount

    def observe_latency(self, metric: LatencyMetric, elapsed_ns: int) -> None:
        if not isinstance(metric, LatencyMetric):
            raise TypeError("metric must be a LatencyMetric value.")
        if not isinstance(elapsed_ns, int) or elapsed_ns < 0:
            raise ValueError("elapsed_ns must be a non-negative integer.")
        with self._lock:
            self._latencies[metric].observe(elapsed_ns)

    def snapshot(self) -> OperationalMetricsSnapshot:
        with self._lock:
            counters = tuple(
                (metric.value, self._counters[metric]) for metric in CounterMetric
            )
            latencies = tuple(
                self._latency_summary(metric, self._latencies[metric])
                for metric in LatencyMetric
            )
        return OperationalMetricsSnapshot(counters=counters, latencies=latencies)

    @staticmethod
    def _latency_summary(
        metric: LatencyMetric,
        accumulator: _LatencyAccumulator,
    ) -> LatencySummary:
        divisor = 1_000_000
        mean_ns = accumulator.total_ns / accumulator.count if accumulator.count else 0
        return LatencySummary(
            name=metric.value,
            count=accumulator.count,
            total_ms=accumulator.total_ns / divisor,
            minimum_ms=accumulator.minimum_ns / divisor,
            maximum_ms=accumulator.maximum_ns / divisor,
            mean_ms=mean_ns / divisor,
        )


class NullOperationalMetrics(OperationalMetrics):
    """No-op implementation preserving the complete fixed metric vocabulary."""

    def increment(self, metric: CounterMetric, amount: int = 1) -> None:
        del metric, amount

    def observe_latency(self, metric: LatencyMetric, elapsed_ns: int) -> None:
        del metric, elapsed_ns

    def snapshot(self) -> OperationalMetricsSnapshot:
        return ProcessLocalOperationalMetrics().snapshot()


class FailOpenOperationalMetrics(OperationalMetrics):
    """Isolate instrumentation faults and expose their count when possible."""

    def __init__(self, delegate: OperationalMetrics) -> None:
        if not isinstance(delegate, OperationalMetrics):
            raise TypeError("delegate must be an OperationalMetrics instance.")
        self._delegate = delegate
        self._failures = ProcessLocalOperationalMetrics()

    def increment(self, metric: CounterMetric, amount: int = 1) -> None:
        try:
            self._delegate.increment(metric, amount)
        except Exception:
            self._record_failure()

    def observe_latency(self, metric: LatencyMetric, elapsed_ns: int) -> None:
        try:
            self._delegate.observe_latency(metric, elapsed_ns)
        except Exception:
            self._record_failure()

    def snapshot(self) -> OperationalMetricsSnapshot:
        try:
            delegate_snapshot = self._delegate.snapshot()
        except Exception:
            self._record_failure()
            delegate_snapshot = NullOperationalMetrics().snapshot()

        failure_count = self._failures.snapshot().counter(
            CounterMetric.INSTRUMENTATION_FAILURES
        )
        counters = dict(delegate_snapshot.counters)
        counters[CounterMetric.INSTRUMENTATION_FAILURES.value] += failure_count
        return OperationalMetricsSnapshot(
            counters=tuple(
                (metric.value, counters[metric.value]) for metric in CounterMetric
            ),
            latencies=delegate_snapshot.latencies,
        )

    def _record_failure(self) -> None:
        self._failures.increment(CounterMetric.INSTRUMENTATION_FAILURES)


def fail_open(
    metrics: OperationalMetrics | None,
) -> FailOpenOperationalMetrics:
    """Return one fail-open boundary for an optional injected recorder."""

    if isinstance(metrics, FailOpenOperationalMetrics):
        return metrics
    return FailOpenOperationalMetrics(metrics or NullOperationalMetrics())
