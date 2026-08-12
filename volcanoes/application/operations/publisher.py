"""Observational event-publisher adapter for operational counters."""

from __future__ import annotations

from time import monotonic_ns

from volcanoes.application.operations.metrics import (
    CounterMetric,
    LatencyMetric,
    OperationalMetrics,
    fail_open,
)
from volcanoes.events import DomainEvent, EventPublisher


class OperationalEventPublisher(EventPublisher):
    """Count publication attempts without changing publisher semantics."""

    def __init__(
        self,
        delegate: EventPublisher,
        metrics: OperationalMetrics,
    ) -> None:
        if not isinstance(delegate, EventPublisher):
            raise TypeError("delegate must be an EventPublisher instance.")
        self._delegate = delegate
        self._metrics = fail_open(metrics)

    @property
    def delegate(self) -> EventPublisher:
        return self._delegate

    def publish(self, event: DomainEvent) -> None:
        started = monotonic_ns()
        self._metrics.increment(CounterMetric.EVENT_PUBLICATION_ATTEMPTS)
        try:
            self._delegate.publish(event)
        finally:
            self._metrics.observe_latency(
                LatencyMetric.EVENT_PUBLICATION,
                monotonic_ns() - started,
            )
