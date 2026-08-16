"""Offline tests for bounded event-delivery observability."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from volcanoes.application.operations.event_delivery import (
    EventDeliveryCapability,
    EventDeliveryStatus,
    ObservableEventPublisher,
    RetryableEventPublicationError,
    derive_event_delivery_id,
)
from volcanoes.events import DomainEvent, EventPublisher, NullEventPublisher, TradeRejected


FIXED_TIME = datetime(2026, 8, 16, 16, 30, tzinfo=UTC)


def event() -> TradeRejected:
    return TradeRejected(
        correlation_id="event-delivery-correlation",
        timestamp=FIXED_TIME,
        operation="test",
        symbol="AAPL",
        policy="TestPolicy",
        explanation="Controlled event delivery test.",
    )


class RecordingPublisher(EventPublisher):
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def publish(self, published: DomainEvent) -> None:
        self.events.append(published)


class RetryThenRecordPublisher(EventPublisher):
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0
        self.events: list[DomainEvent] = []

    def publish(self, published: DomainEvent) -> None:
        self.calls += 1
        self.events.append(published)
        if self.calls <= self.failures:
            raise RetryableEventPublicationError("provably not sent")


class ExplodingPublisher(EventPublisher):
    def __init__(self) -> None:
        self.calls = 0

    def publish(self, published: DomainEvent) -> None:
        del published
        self.calls += 1
        raise RuntimeError("ambiguous external failure")


def test_delivery_identity_is_stable_for_same_canonical_event() -> None:
    first = event()
    second = event()

    assert derive_event_delivery_id(first) == derive_event_delivery_id(second)
    assert derive_event_delivery_id(first).startswith("evt-")
    assert len(derive_event_delivery_id(first)) == 68


def test_null_publisher_is_explicitly_local_not_external_delivery() -> None:
    publisher = ObservableEventPublisher(
        NullEventPublisher(),
        capability=EventDeliveryCapability.NULL,
    )

    publisher.publish(event())

    snapshot = publisher.snapshot()
    assert snapshot.attempts == 1
    assert snapshot.local_accepted == 1
    assert snapshot.external_delivered == 0
    assert snapshot.failures == 0
    diagnostic = snapshot.diagnostics[-1]
    assert diagnostic.status is EventDeliveryStatus.LOCAL_ACCEPTED
    assert diagnostic.reason_code == "NULL_NO_EXTERNAL_DELIVERY"


def test_local_recording_and_external_delivery_are_separate_statuses() -> None:
    local_delegate = RecordingPublisher()
    external_delegate = RecordingPublisher()
    local = ObservableEventPublisher(
        local_delegate,
        capability=EventDeliveryCapability.LOCAL_RECORDING,
    )
    external = ObservableEventPublisher(
        external_delegate,
        capability=EventDeliveryCapability.EXTERNAL_DELIVERY,
    )

    local.publish(event())
    external.publish(event())

    assert local.snapshot().diagnostics[-1].status is EventDeliveryStatus.LOCAL_ACCEPTED
    assert (
        external.snapshot().diagnostics[-1].status
        is EventDeliveryStatus.EXTERNAL_DELIVERED
    )
    assert len(local_delegate.events) == 1
    assert len(external_delegate.events) == 1


def test_retryable_known_not_sent_failure_is_bounded_and_reported() -> None:
    delegate = RetryThenRecordPublisher(failures=2)
    publisher = ObservableEventPublisher(
        delegate,
        capability=EventDeliveryCapability.EXTERNAL_DELIVERY,
        max_attempts=3,
    )

    publisher.publish(event())

    snapshot = publisher.snapshot()
    assert delegate.calls == 3
    assert snapshot.attempts == 3
    assert snapshot.retries == 2
    assert snapshot.external_delivered == 1
    diagnostic = snapshot.diagnostics[-1]
    assert diagnostic.attempts == 3
    assert diagnostic.retries == 2
    assert len({derive_event_delivery_id(item) for item in delegate.events}) == 1


def test_retry_exhaustion_is_visible_and_reraises() -> None:
    delegate = RetryThenRecordPublisher(failures=5)
    publisher = ObservableEventPublisher(
        delegate,
        capability=EventDeliveryCapability.LOCAL_RECORDING,
        max_attempts=3,
    )

    with pytest.raises(RetryableEventPublicationError):
        publisher.publish(event())

    snapshot = publisher.snapshot()
    assert snapshot.attempts == 3
    assert snapshot.retries == 2
    assert snapshot.failures == 1
    assert snapshot.diagnostics[-1].status is EventDeliveryStatus.FAILED
    assert snapshot.diagnostics[-1].reason_code == "RETRY_EXHAUSTED"


def test_ambiguous_external_exception_is_outcome_unknown_and_not_retried() -> None:
    delegate = ExplodingPublisher()
    publisher = ObservableEventPublisher(
        delegate,
        capability=EventDeliveryCapability.EXTERNAL_DELIVERY,
        max_attempts=5,
    )

    with pytest.raises(RuntimeError):
        publisher.publish(event())

    snapshot = publisher.snapshot()
    assert delegate.calls == 1
    assert snapshot.attempts == 1
    assert snapshot.retries == 0
    assert snapshot.outcome_unknown == 1
    assert snapshot.failures == 0
    assert snapshot.diagnostics[-1].status is EventDeliveryStatus.OUTCOME_UNKNOWN


def test_ambiguous_local_exception_is_failed_and_not_retried() -> None:
    publisher = ObservableEventPublisher(
        ExplodingPublisher(),
        capability=EventDeliveryCapability.LOCAL_RECORDING,
        max_attempts=5,
    )

    with pytest.raises(RuntimeError):
        publisher.publish(event())

    snapshot = publisher.snapshot()
    assert snapshot.attempts == 1
    assert snapshot.retries == 0
    assert snapshot.failures == 1
    assert snapshot.outcome_unknown == 0


def test_diagnostic_history_is_bounded() -> None:
    publisher = ObservableEventPublisher(
        NullEventPublisher(),
        capability=EventDeliveryCapability.NULL,
        history_limit=2,
    )

    for index in range(3):
        publisher.publish(
            TradeRejected(
                correlation_id=f"correlation-{index}",
                timestamp=FIXED_TIME,
                operation="test",
                symbol="AAPL",
                policy="TestPolicy",
                explanation="Controlled event delivery test.",
            )
        )

    snapshot = publisher.snapshot()
    assert snapshot.attempts == 3
    assert snapshot.local_accepted == 3
    assert len(snapshot.diagnostics) == 2
    assert tuple(item.correlation_id for item in snapshot.diagnostics) == (
        "correlation-1",
        "correlation-2",
    )


@pytest.mark.parametrize("max_attempts", [0, 6, -1])
def test_retry_attempt_bound_is_enforced(max_attempts: int) -> None:
    with pytest.raises(ValueError):
        ObservableEventPublisher(
            NullEventPublisher(),
            capability=EventDeliveryCapability.NULL,
            max_attempts=max_attempts,
        )


def test_null_capability_cannot_be_misrepresented() -> None:
    with pytest.raises(ValueError):
        ObservableEventPublisher(
            RecordingPublisher(),
            capability=EventDeliveryCapability.NULL,
        )
    with pytest.raises(ValueError):
        ObservableEventPublisher(
            NullEventPublisher(),
            capability=EventDeliveryCapability.EXTERNAL_DELIVERY,
        )
