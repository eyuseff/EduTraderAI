"""Immutable operational events emitted by Volcanoes application services."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from uuid import uuid4

PolicyConfiguration = tuple[tuple[str, str], ...]


def utc_now() -> datetime:
    """Return an aware UTC timestamp for a newly created event."""

    return datetime.now(UTC)


def new_correlation_id() -> str:
    """Create an opaque correlation identifier for one trade lifecycle."""

    return str(uuid4())


@dataclass(frozen=True, slots=True)
class PolicyExplanation:
    """Immutable explanation of one rejected operational decision."""

    policy: str
    explanation: str
    configuration: PolicyConfiguration = ()

    def __post_init__(self) -> None:
        if not self.policy.strip():
            raise ValueError("policy cannot be empty.")
        if not self.explanation.strip():
            raise ValueError("explanation cannot be empty.")
        object.__setattr__(self, "configuration", tuple(sorted(self.configuration)))
        _validate_payload(self.configuration)


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent:
    """Common immutable identity shared by every operational event."""

    correlation_id: str
    timestamp: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not isinstance(self.correlation_id, str) or not self.correlation_id.strip():
            raise ValueError("correlation_id cannot be empty.")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware.")

        for event_field in fields(self):
            _validate_payload(getattr(self, event_field.name))


@dataclass(frozen=True, slots=True, kw_only=True)
class TradePreviewed(DomainEvent):
    symbol: str
    side: str
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    approved: bool
    quantity: int
    dollar_risk: Decimal
    position_value: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class TradeRejected(DomainEvent):
    operation: str
    symbol: str
    policy: str
    explanation: str
    configuration: PolicyConfiguration = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class TradeSubmitted(DomainEvent):
    order_id: str | None
    symbol: str
    side: str
    quantity: int
    price: Decimal
    stop_price: Decimal | None
    target_price: Decimal | None
    broker_status: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class TradeFilled(DomainEvent):
    order_id: str | None
    symbol: str
    side: str
    quantity: int
    price: Decimal


@dataclass(frozen=True, slots=True, kw_only=True)
class TradeCancelled(DomainEvent):
    order_id: str | None
    symbol: str
    explanation: str


@dataclass(frozen=True, slots=True, kw_only=True)
class TradeFailed(DomainEvent):
    operation: str
    symbol: str
    policy: str
    explanation: str
    configuration: PolicyConfiguration = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class PlanDriftDetected(DomainEvent):
    symbol: str
    differences: tuple[str, ...]
    expected: PolicyConfiguration
    actual: PolicyConfiguration


@dataclass(frozen=True, slots=True, kw_only=True)
class PolicyViolation(DomainEvent):
    operation: str
    symbol: str
    policy: str
    explanation: str
    configuration: PolicyConfiguration = ()


def _validate_payload(value: object) -> None:
    """Reject mutable or infrastructure-specific objects from event payloads."""

    if value is None or isinstance(
        value,
        (str, int, bool, Decimal, datetime, Enum),
    ):
        return

    if isinstance(value, tuple):
        for item in value:
            _validate_payload(item)
        return

    raise TypeError(
        "Event payloads may contain only immutable deterministic values; "
        f"received {type(value).__name__}."
    )
