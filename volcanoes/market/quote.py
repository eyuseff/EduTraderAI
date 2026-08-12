"""Real-time market quote domain model for Volcanes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class Quote:
    """Immutable bid/ask/last market quote."""

    symbol: str
    timestamp: datetime
    bid: Decimal
    ask: Decimal
    last: Decimal

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()

        if not symbol:
            raise ValueError("Quote symbol cannot be empty.")

        timestamp = self._normalize_timestamp(self.timestamp)
        bid = self._normalize_price(self.bid)
        ask = self._normalize_price(self.ask)
        last = self._normalize_price(self.last)

        if bid > ask:
            raise ValueError(
                "Quote bid price cannot be greater than ask price."
            )

        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "bid", bid)
        object.__setattr__(self, "ask", ask)
        object.__setattr__(self, "last", last)

    @property
    def mid_price(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid

    @staticmethod
    def _normalize_timestamp(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "Quote timestamp must be timezone-aware."
            )

        return value.astimezone(UTC)

    @staticmethod
    def _normalize_price(
        value: Decimal | int | float | str,
    ) -> Decimal:
        try:
            price = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("Invalid quote price.") from exc

        if price <= Decimal("0"):
            raise ValueError(
                "Quote prices must be greater than zero."
            )

        return price
