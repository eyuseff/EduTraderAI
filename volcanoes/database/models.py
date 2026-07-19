"""Core domain models for Volcanes — The Real Volcanoes."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(UTC)


class TradeStatus(StrEnum):
    """Valid stages in the Volcanes trade lifecycle."""

    DISCOVERED = "DISCOVERED"
    QUALIFIED = "QUALIFIED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ORDER_SENT = "ORDER_SENT"
    FILLED = "FILLED"
    OPEN = "OPEN"
    MONITORED = "MONITORED"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    CLOSED = "CLOSED"
    REVIEWED = "REVIEWED"
    CANCELLED = "CANCELLED"


class OrderStatus(StrEnum):
    """Supported order states."""

    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class Side(StrEnum):
    """Trading direction."""

    BUY = "BUY"
    SELL = "SELL"


class ExecutionMode(StrEnum):
    """Allowed execution environments."""

    PREVIEW = "PREVIEW"
    PAPER = "PAPER"
    LIVE = "LIVE"


class MarketRegime(StrEnum):
    """High-level market conditions."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    SIDEWAYS = "SIDEWAYS"
    VOLATILE = "VOLATILE"
    UNKNOWN = "UNKNOWN"


class RiskDecision(StrEnum):
    """Possible Guardian decisions."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REDUCED = "REDUCED"


@dataclass(slots=True)
class Candidate:
    """A trading opportunity identified by Explorer."""

    symbol: str
    strategy_name: str
    score: float
    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    explanation: str | None = None
    scanner_run_id: int | None = None
    status: TradeStatus = TradeStatus.DISCOVERED
    created_at: datetime = field(default_factory=utc_now)
    id: int | None = None

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()
        self.strategy_name = self.strategy_name.strip()

        if not self.symbol:
            raise ValueError("Candidate symbol cannot be empty.")

        if not self.strategy_name:
            raise ValueError("Candidate strategy name cannot be empty.")

        if not 0 <= self.score <= 100:
            raise ValueError("Candidate score must be between 0 and 100.")


@dataclass(slots=True)
class GuardianAssessment:
    """Guardian's deterministic risk evaluation."""

    decision: RiskDecision
    approved_quantity: float
    risk_amount: float
    portfolio_heat_after: float
    reasons: list[str] = field(default_factory=list)
    assessed_at: datetime = field(default_factory=utc_now)

    @property
    def approved(self) -> bool:
        """Return whether Guardian permits the trade."""
        return self.decision in {
            RiskDecision.APPROVED,
            RiskDecision.REDUCED,
        }


@dataclass(slots=True)
class Trade:
    """A trade moving through the Volcanes lifecycle."""

    symbol: str
    strategy_name: str
    side: Side
    quantity: float
    status: TradeStatus = TradeStatus.DISCOVERED
    candidate_id: int | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    realized_pnl: float | None = None
    explanation: str | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()
        self.strategy_name = self.strategy_name.strip()

        if not self.symbol:
            raise ValueError("Trade symbol cannot be empty.")

        if not self.strategy_name:
            raise ValueError("Trade strategy name cannot be empty.")

        if self.quantity <= 0:
            raise ValueError("Trade quantity must be greater than zero.")


@dataclass(slots=True)
class Order:
    """An execution instruction sent to a broker."""

    broker: str
    order_type: str
    side: Side
    quantity: float
    status: OrderStatus = OrderStatus.CREATED
    trade_id: int | None = None
    broker_order_id: str | None = None
    limit_price: float | None = None
    stop_price: float | None = None
    submitted_at: datetime | None = None
    filled_at: datetime | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        self.broker = self.broker.strip()
        self.order_type = self.order_type.strip().upper()

        if not self.broker:
            raise ValueError("Broker name cannot be empty.")

        if not self.order_type:
            raise ValueError("Order type cannot be empty.")

        if self.quantity <= 0:
            raise ValueError("Order quantity must be greater than zero.")


@dataclass(slots=True)
class SystemEvent:
    """An auditable event produced by a Volcanes component."""

    event_type: str
    component: str
    message: str
    severity: str = "INFO"
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    id: int | None = None

    def __post_init__(self) -> None:
        self.event_type = self.event_type.strip().upper()
        self.component = self.component.strip()
        self.message = self.message.strip()
        self.severity = self.severity.strip().upper()

        if not self.event_type:
            raise ValueError("Event type cannot be empty.")

        if not self.component:
            raise ValueError("Event component cannot be empty.")

        if not self.message:
            raise ValueError("Event message cannot be empty.")
