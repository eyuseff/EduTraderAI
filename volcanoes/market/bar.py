"""Historical market bar domain model for Volcanes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True)
class Bar:
    """Immutable OHLCV market bar for one symbol and timestamp."""

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()

        if not symbol:
            raise ValueError("Bar symbol cannot be empty.")

        timestamp = self._normalize_timestamp(self.timestamp)
        open_price = self._normalize_price(self.open, "open")
        high_price = self._normalize_price(self.high, "high")
        low_price = self._normalize_price(self.low, "low")
        close_price = self._normalize_price(self.close, "close")
        volume = self._normalize_volume(self.volume)

        if high_price < low_price:
            raise ValueError(
                "Bar high price cannot be lower than the low price."
            )

        if high_price < open_price:
            raise ValueError(
                "Bar high price cannot be lower than the open price."
            )

        if high_price < close_price:
            raise ValueError(
                "Bar high price cannot be lower than the close price."
            )

        if low_price > open_price:
            raise ValueError(
                "Bar low price cannot be higher than the open price."
            )

        if low_price > close_price:
            raise ValueError(
                "Bar low price cannot be higher than the close price."
            )

        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "timestamp", timestamp)
        object.__setattr__(self, "open", open_price)
        object.__setattr__(self, "high", high_price)
        object.__setattr__(self, "low", low_price)
        object.__setattr__(self, "close", close_price)
        object.__setattr__(self, "volume", volume)

    @staticmethod
    def _normalize_timestamp(value: datetime) -> datetime:
        """Validate a timezone-aware timestamp and normalize it to UTC."""

        if not isinstance(value, datetime):
            raise TypeError("Bar timestamp must be a datetime instance.")

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Bar timestamp must be timezone-aware.")

        return value.astimezone(UTC)

    @staticmethod
    def _normalize_price(
        value: Decimal | int | float | str,
        field_name: str,
    ) -> Decimal:
        """Convert and validate a strictly positive market price."""

        if isinstance(value, bool):
            raise TypeError(
                f"Bar {field_name} price cannot be a boolean value."
            )

        if not isinstance(value, (Decimal, int, float, str)):
            raise TypeError(
                f"Bar {field_name} price must be numeric."
            )

        try:
            price = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(
                f"Bar {field_name} price must be numeric."
            ) from exc

        if not price.is_finite():
            raise ValueError(
                f"Bar {field_name} price must be finite."
            )

        if price <= Decimal("0"):
            raise ValueError(
                f"Bar {field_name} price must be greater than zero."
            )

        return price

    @staticmethod
    def _normalize_volume(value: int) -> int:
        """Validate a non-negative integer volume."""

        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("Bar volume must be an integer.")

        if value < 0:
            raise ValueError("Bar volume cannot be negative.")

        return value
