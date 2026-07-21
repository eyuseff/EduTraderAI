"""Publishing port for operational domain events."""

from __future__ import annotations

from abc import ABC, abstractmethod

from volcanoes.events.models import DomainEvent


class EventPublisher(ABC):
    """Port implemented by operational event destinations."""

    @abstractmethod
    def publish(self, event: DomainEvent) -> None:
        """Publish exactly one immutable domain event."""
        raise NotImplementedError


class NullEventPublisher(EventPublisher):
    """Default publisher used until a persistence adapter is introduced."""

    def publish(self, event: DomainEvent) -> None:
        """Accept an event without producing a side effect."""

        if not isinstance(event, DomainEvent):
            raise TypeError("event must be a DomainEvent instance.")
