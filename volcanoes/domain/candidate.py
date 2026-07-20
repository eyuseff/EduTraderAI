"""Candidate domain model for Volcanes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from volcanoes.domain.enums import CandidateStatus


@dataclass
class Candidate:
    """A market opportunity produced by Explorer."""

    symbol: str
    strategy_name: str
    score: int

    entry_price: Decimal | None = None
    stop_price: Decimal | None = None
    target_price: Decimal | None = None
    explanation: str = ""

    status: CandidateStatus = CandidateStatus.NEW
    scanner_run_id: int | None = None
    id: int | None = None

    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()
        self.strategy_name = self.strategy_name.strip()

        if not self.symbol:
            raise ValueError("Candidate symbol cannot be empty.")

        if not self.strategy_name:
            raise ValueError("Strategy name cannot be empty.")

        if not 0 <= self.score <= 100:
            raise ValueError("Candidate score must be between 0 and 100.")

        self.entry_price = self._normalize_price(self.entry_price)
        self.stop_price = self._normalize_price(self.stop_price)
        self.target_price = self._normalize_price(self.target_price)

    @staticmethod
    def _normalize_price(
        value: Decimal | float | int | str | None,
    ) -> Decimal | None:
        """Convert incoming market prices to Decimal with cent precision."""

        if value is None:
            return None

        try:
            decimal_value = Decimal(str(value))
        except Exception as exc:
            raise ValueError(f"Invalid price value: {value}") from exc

        decimal_value = decimal_value.quantize(Decimal("0.01"))

        if decimal_value <= Decimal("0"):
            raise ValueError("Price values must be greater than zero.")

        return decimal_value
