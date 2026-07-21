"""Read-only bridge from the active broker API to Volcanoes risk state."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from broker.base import AccountSnapshot, BrokerPosition, PaperBroker
from volcanoes.risk.portfolio_view import RiskPositionView


def _decimal(value: float) -> Decimal:
    """Convert broker floats without introducing binary float artifacts."""

    return Decimal(str(value))


@dataclass(frozen=True, slots=True)
class BrokerPositionView(RiskPositionView):
    """Immutable copy of one position returned by the active broker."""

    symbol: str
    quantity: int
    average_entry_price: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal

    @classmethod
    def from_position(
        cls,
        position: BrokerPosition,
    ) -> BrokerPositionView:
        """Copy all broker position values into immutable Decimal fields."""

        return cls(
            symbol=position.symbol.strip().upper(),
            quantity=position.quantity,
            average_entry_price=_decimal(position.average_entry_price),
            current_price=_decimal(position.current_price),
            market_value=_decimal(position.market_value),
            unrealized_pnl=_decimal(position.unrealized_pnl),
        )


@dataclass(frozen=True, slots=True)
class BrokerPortfolioView:
    """Immutable risk view copied from one active-broker snapshot."""

    equity: Decimal
    cash: Decimal
    buying_power: Decimal
    daily_pnl: Decimal
    paper: bool
    positions: tuple[BrokerPositionView, ...]

    @classmethod
    def from_broker(cls, broker: PaperBroker) -> BrokerPortfolioView:
        """Read account and positions without invoking broker mutations."""

        account = broker.get_account()
        positions = broker.get_positions()
        return cls.from_snapshot(account, positions)

    @classmethod
    def from_snapshot(
        cls,
        account: AccountSnapshot,
        positions: list[BrokerPosition],
    ) -> BrokerPortfolioView:
        """Copy an existing broker snapshot into a read-only risk view."""

        return cls(
            equity=_decimal(account.equity),
            cash=_decimal(account.cash),
            buying_power=_decimal(account.buying_power),
            daily_pnl=_decimal(account.daily_pnl),
            paper=account.paper,
            positions=tuple(
                BrokerPositionView.from_position(position) for position in positions
            ),
        )

    @property
    def starting_cash(self) -> Decimal:
        """Return implied start-of-period equity for daily-loss checks."""

        return self.equity - self.daily_pnl

    @property
    def realized_pnl(self) -> Decimal:
        """Expose broker daily P/L through the risk-view P/L contract."""

        return self.daily_pnl

    @property
    def invested_value(self) -> Decimal:
        """Return gross exposure using absolute position market values."""

        return sum(
            (abs(position.market_value) for position in self.positions),
            start=Decimal("0"),
        )

    @property
    def open_positions(self) -> int:
        """Return the number of broker positions in the snapshot."""

        return len(self.positions)

    def has_position(self, symbol: str) -> bool:
        """Return whether the snapshot contains a normalized symbol."""

        return self.get_position(symbol) is not None

    def get_position(self, symbol: str) -> RiskPositionView | None:
        """Return a copied position without consulting the broker again."""

        normalized_symbol = symbol.strip().upper()
        return next(
            (
                position
                for position in self.positions
                if position.symbol == normalized_symbol
            ),
            None,
        )
