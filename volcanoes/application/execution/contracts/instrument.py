"""Immutable Paper execution instrument."""

from __future__ import annotations

from dataclasses import dataclass

from volcanoes.application.execution.contracts._validation import (
    normalize_alias,
    normalize_symbol,
)


@dataclass(frozen=True, slots=True)
class PaperExecutionInstrument:
    """Broker-neutral instrument facts without tradability claims."""

    symbol: str
    asset_class: str = "equity"
    currency: str = "USD"
    venue: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", normalize_symbol(self.symbol))
        object.__setattr__(
            self,
            "asset_class",
            normalize_alias(self.asset_class, "asset_class").lower(),
        )
        object.__setattr__(
            self,
            "currency",
            normalize_alias(self.currency, "currency").upper(),
        )
        if self.venue is not None:
            object.__setattr__(
                self,
                "venue",
                normalize_alias(self.venue, "venue"),
            )

    def to_primitive(self) -> dict[str, object]:
        return {
            "asset_class": self.asset_class,
            "currency": self.currency,
            "symbol": self.symbol,
            "venue": self.venue,
        }
