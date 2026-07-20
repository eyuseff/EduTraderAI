"""Domain model representing a strategy's trading intention."""

from dataclasses import dataclass
from decimal import Decimal

from volcanoes.domain.enums import TradeSide


@dataclass(frozen=True)
class TradeIntent:
    """
    Represent a trading idea before position sizing.

    A trade intent describes what a strategy wants to trade and the
    prices that define the setup. It intentionally does not contain a
    quantity because position sizing is handled by a separate component.
    """

    symbol: str
    side: TradeSide
    entry_price: Decimal
    stop_price: Decimal

    def __post_init__(self) -> None:
        """Validate and normalize the trade intent."""

        normalized_symbol = self.symbol.strip().upper()

        if not normalized_symbol:
            raise ValueError(
                "Trade intent symbol cannot be empty."
            )

        if self.entry_price <= Decimal("0"):
            raise ValueError(
                "Entry price must be greater than zero."
            )

        if self.stop_price <= Decimal("0"):
            raise ValueError(
                "Stop price must be greater than zero."
            )

        if self.side is TradeSide.BUY:
            if self.stop_price >= self.entry_price:
                raise ValueError(
                    "Buy stop price must be below entry price."
                )

        if self.side is TradeSide.SELL:
            if self.stop_price <= self.entry_price:
                raise ValueError(
                    "Sell stop price must be above entry price."
                )

        object.__setattr__(
            self,
            "symbol",
            normalized_symbol,
        )

    @property
    def risk_per_share(self) -> Decimal:
        """Return the absolute price risk for one share."""

        return abs(
            self.entry_price - self.stop_price
        )
