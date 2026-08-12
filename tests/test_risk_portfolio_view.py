"""Tests for the read-only risk portfolio boundary."""

from dataclasses import dataclass
from decimal import Decimal

from volcanoes.domain import TradeRequest
from volcanoes.portfolio import Portfolio
from volcanoes.risk import (
    RiskManager,
    RiskPortfolioView,
    RiskPositionView,
)


@dataclass(frozen=True, slots=True)
class PositionView(RiskPositionView):
    symbol: str
    quantity: int


@dataclass(frozen=True, slots=True)
class PortfolioView:
    starting_cash: Decimal
    realized_pnl: Decimal
    equity: Decimal
    buying_power: Decimal
    invested_value: Decimal
    positions: tuple[PositionView, ...] = ()

    @property
    def open_positions(self) -> int:
        return len(self.positions)

    def has_position(self, symbol: str) -> bool:
        return self.get_position(symbol) is not None

    def get_position(self, symbol: str) -> RiskPositionView | None:
        normalized = symbol.strip().upper()
        return next(
            (position for position in self.positions if position.symbol == normalized),
            None,
        )


def test_native_portfolio_satisfies_risk_portfolio_view() -> None:
    portfolio = Portfolio(starting_cash=Decimal("10000"))

    assert isinstance(portfolio, RiskPortfolioView)


def test_structural_view_satisfies_risk_portfolio_view() -> None:
    view = PortfolioView(
        starting_cash=Decimal("10000"),
        realized_pnl=Decimal("0"),
        equity=Decimal("10000"),
        buying_power=Decimal("10000"),
        invested_value=Decimal("0"),
    )

    assert isinstance(view, RiskPortfolioView)


def test_risk_manager_accepts_equivalent_structural_view() -> None:
    portfolio = Portfolio(starting_cash=Decimal("10000"))
    view = PortfolioView(
        starting_cash=portfolio.starting_cash,
        realized_pnl=portfolio.realized_pnl,
        equity=portfolio.equity,
        buying_power=portfolio.buying_power,
        invested_value=portfolio.invested_value,
    )
    trade = TradeRequest(
        symbol="AAPL",
        quantity=10,
        price=Decimal("100"),
    )
    manager = RiskManager()

    assert manager.validate_trade(portfolio, trade) is True
    assert manager.validate_trade(view, trade) is True


def test_risk_validation_does_not_mutate_structural_view() -> None:
    view = PortfolioView(
        starting_cash=Decimal("10000"),
        realized_pnl=Decimal("0"),
        equity=Decimal("10000"),
        buying_power=Decimal("10000"),
        invested_value=Decimal("0"),
    )
    trade = TradeRequest(
        symbol="AAPL",
        quantity=10,
        price=Decimal("100"),
    )

    before = view
    RiskManager().validate_trade(view, trade)

    assert view == before
