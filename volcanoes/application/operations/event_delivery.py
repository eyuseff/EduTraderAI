"""Bounded, transport-neutral observability for operational event delivery."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock

from volcanoes.events import DomainEvent, EventPublisher, NullEventPublisher
from volcanoes.events.serialization import serialize_event


class EventDeliveryCapability(StrEnum):
    """Declared delivery capability of one event publisher boundary."""

    NULL = "NULL"
    LOCAL_RECORDING = "LOCAL_RECORDING"
    EXTERNAL_DELIVERY = "EXTERNAL_DELIVERY"


class EventDeliveryStatus(StrEnum):
    """Safe observable result categories for one immutable event identity."""

    LOCAL_ACCEPTED = "LOCAL_ACCEPTED"
    EXTERNAL_DELIVERED = "EXTERNAL_DELIVERED"
    FAILED = "FAILED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


class RetryableEventPublicationError(RuntimeError):
    """Signal that an event was provably not sent and may be retried safely."""


@dataclass(frozen=True, slots=True)
class EventDeliveryDiagnostic:
    """One immutable safe delivery diagnostic."""

    event_id: str
    correlation_id: str
    capability: EventDeliveryCapability
    status: EventDeliveryStatus
    attempts: int
    retries: int
    reason_code: str


@dataclass(frozen=True, slots=True)
class EventDeliverySnapshot:
    """Bounded point-in-time process-local event delivery metrics."""

    attempts: int
    retries: int
    local_accepted: int
    external_delivered: int
    failures: int
    outcome_unknown: int
    diagnostics: tuple[EventDeliveryDiagnostic, ...]


class ObservableEventPublisher(EventPublisher):
    """Observe and safely retry event publication without replaying business work."""

    def __init__(
        self,
        delegate: EventPublisher,
        *,
        capability: EventDeliveryCapability,
        max_attempts: int = 1,
        history_limit: int = 100,
    ) -> None:
        if not isinstance(delegate, EventPublisher):
            raise TypeError("delegate must be an EventPublisher instance.")
        if not isinstance(capability, EventDeliveryCapability):
            raise TypeError("capability must be an EventDeliveryCapability value.")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int):
            raise TypeError("max_attempts must be an integer.")
        if not 1 <= max_attempts <= 5:
            raise ValueError("max_attempts must be between 1 and 5.")
        if isinstance(history_limit, bool) or not isinstance(history_limit, int):
            raise TypeError("history_limit must be an integer.")
        if not 1 <= history_limit <= 1_000:
            raise ValueError("history_limit must be between 1 and 1000.")
        if capability is EventDeliveryCapability.NULL and not isinstance(
            delegate, NullEventPublisher
        ):
            raise ValueError("NULL capability requires NullEventPublisher.")
        if capability is not EventDeliveryCapability.NULL and isinstance(
            delegate, NullEventPublisher
        ):
            raise ValueError("NullEventPublisher must declare NULL capability.")

        self._delegate = delegate
        self._capability = capability
        self._max_attempts = max_attempts
        self._history_limit = history_limit
        self._lock = Lock()
        self._attempts = 0
        self._retries = 0
        self._local_accepted = 0
        self._external_delivered = 0
        self._failures = 0
        self._outcome_unknown = 0
        self._diagnostics: list[EventDeliveryDiagnostic] = []

    @property
    def delegate(self) -> EventPublisher:
        return self._delegate

    @property
    def capability(self) -> EventDeliveryCapability:
        return self._capability

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    def publish(self, event: DomainEvent) -> None:
        """Publish one immutable event; retries apply only to known-not-sent failures."""

        if not isinstance(event, DomainEvent):
            raise TypeError("event must be a DomainEvent instance.")
        event_id = derive_event_delivery_id(event)
        attempts = 0
        retries = 0

        while attempts < self._max_attempts:
            attempts += 1
            self._record_attempt()
            try:
                self._delegate.publish(event)
            except RetryableEventPublicationError:
                if attempts < self._max_attempts:
                    retries += 1
                    self._record_retry()
                    continue
                diagnostic = EventDeliveryDiagnostic(
                    event_id=event_id,
                    correlation_id=event.correlation_id,
                    capability=self._capability,
                    status=EventDeliveryStatus.FAILED,
                    attempts=attempts,
                    retries=retries,
                    reason_code="RETRY_EXHAUSTED",
                )
                self._record_terminal(diagnostic)
                raise
            except Exception:
                status = (
                    EventDeliveryStatus.OUTCOME_UNKNOWN
                    if self._capability is EventDeliveryCapability.EXTERNAL_DELIVERY
                    else EventDeliveryStatus.FAILED
                )
                diagnostic = EventDeliveryDiagnostic(
                    event_id=event_id,
                    correlation_id=event.correlation_id,
                    capability=self._capability,
                    status=status,
                    attempts=attempts,
                    retries=retries,
                    reason_code=(
                        "EXTERNAL_DELIVERY_OUTCOME_UNKNOWN"
                        if status is EventDeliveryStatus.OUTCOME_UNKNOWN
                        else "DELIVERY_FAILED"
                    ),
                )
                self._record_terminal(diagnostic)
                raise
            else:
                status = (
                    EventDeliveryStatus.EXTERNAL_DELIVERED
                    if self._capability is EventDeliveryCapability.EXTERNAL_DELIVERY
                    else EventDeliveryStatus.LOCAL_ACCEPTED
                )
                diagnostic = EventDeliveryDiagnostic(
                    event_id=event_id,
                    correlation_id=event.correlation_id,
                    capability=self._capability,
                    status=status,
                    attempts=attempts,
                    retries=retries,
                    reason_code=(
                        "EXTERNAL_DELIVERY_ACKNOWLEDGED"
                        if status is EventDeliveryStatus.EXTERNAL_DELIVERED
                        else (
                            "NULL_NO_EXTERNAL_DELIVERY"
                            if self._capability is EventDeliveryCapability.NULL
                            else "LOCAL_DELIVERY_ACCEPTED"
                        )
                    ),
                )
                self._record_terminal(diagnostic)
                return

    def snapshot(self) -> EventDeliverySnapshot:
        """Return immutable bounded process-local delivery metrics and diagnostics."""

        with self._lock:
            return EventDeliverySnapshot(
                attempts=self._attempts,
                retries=self._retries,
                local_accepted=self._local_accepted,
                external_delivered=self._external_delivered,
                failures=self._failures,
                outcome_unknown=self._outcome_unknown,
                diagnostics=tuple(self._diagnostics),
            )

    def _record_attempt(self) -> None:
        with self._lock:
            self._attempts += 1

    def _record_retry(self) -> None:
        with self._lock:
            self._retries += 1

    def _record_terminal(self, diagnostic: EventDeliveryDiagnostic) -> None:
        with self._lock:
            if diagnostic.status is EventDeliveryStatus.LOCAL_ACCEPTED:
                self._local_accepted += 1
            elif diagnostic.status is EventDeliveryStatus.EXTERNAL_DELIVERED:
                self._external_delivered += 1
            elif diagnostic.status is EventDeliveryStatus.FAILED:
                self._failures += 1
            else:
                self._outcome_unknown += 1
            self._diagnostics.append(diagnostic)
            overflow = len(self._diagnostics) - self._history_limit
            if overflow > 0:
                del self._diagnostics[:overflow]


def derive_event_delivery_id(event: DomainEvent) -> str:
    """Derive a stable identity from the canonical immutable event payload."""

    if not isinstance(event, DomainEvent):
        raise TypeError("event must be a DomainEvent instance.")
    digest = hashlib.sha256(serialize_event(event).encode("utf-8")).hexdigest()
    return f"evt-{digest}"
