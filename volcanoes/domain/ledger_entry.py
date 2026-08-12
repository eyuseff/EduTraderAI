"""Ledger entry domain model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from volcanoes.domain.enums import LedgerEntryType


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """Immutable financial ledger entry."""

    entry_type: LedgerEntryType
    amount: Decimal
    description: str
    symbol: str | None = None
    quantity: int | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )
    id: str = field(
        default_factory=lambda: str(uuid4())
    )

    def __post_init__(self) -> None:
        if not isinstance(self.entry_type, LedgerEntryType):
            raise TypeError(
                "entry_type must be a LedgerEntryType."
            )

        if not isinstance(self.amount, Decimal):
            raise TypeError(
                "amount must be a Decimal."
            )

        if not self.description.strip():
            raise ValueError(
                "description cannot be empty."
            )

        if self.symbol is not None:
            normalized_symbol = self.symbol.strip().upper()

            if not normalized_symbol:
                raise ValueError(
                    "symbol cannot be empty."
                )

            object.__setattr__(
                self,
                "symbol",
                normalized_symbol,
            )

        if self.quantity is not None and self.quantity <= 0:
            raise ValueError(
                "quantity must be greater than zero."
            )
