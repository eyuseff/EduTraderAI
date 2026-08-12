"""Regression test for portfolio persistence."""

from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from volcanoes.database.schema import initialize_database
from volcanoes.portfolio import Portfolio, PortfolioRepository


def test_portfolio_persistence() -> None:
    with TemporaryDirectory() as temporary_directory:
        database_path = (
            Path(temporary_directory)
            / "portfolio_test.db"
        )

        initialize_database(database_path)

        portfolio = Portfolio(
            starting_cash=Decimal("100000.00")
        )

        portfolio.buy(
            "MSFT",
            25,
            Decimal("393.82"),
        )

        portfolio.buy(
            "AAPL",
            10,
            Decimal("210.50"),
        )

        portfolio.sell(
            "MSFT",
            10,
            Decimal("410.00"),
        )

        repository = PortfolioRepository(
            database_path
        )

        snapshot_id = repository.save(portfolio)

        restored = repository.load()

        assert snapshot_id == 1
        assert restored is not None

        assert (
            restored.starting_cash
            == portfolio.starting_cash
        )

        assert (
            restored.cash
            == portfolio.cash
        )

        assert (
            restored.realized_pnl
            == portfolio.realized_pnl
        )

        assert (
            restored.buying_power
            == portfolio.buying_power
        )

        assert (
            restored.equity
            == portfolio.equity
        )

        assert (
            len(restored.positions)
            == len(portfolio.positions)
        )

        assert (
            restored.get_position("MSFT").quantity
            == portfolio.get_position("MSFT").quantity
        )

        assert (
            restored.get_position("MSFT").average_price
            == portfolio.get_position("MSFT").average_price
        )

        assert (
            restored.get_position("AAPL").quantity
            == portfolio.get_position("AAPL").quantity
        )

        assert (
            restored.get_position("AAPL").average_price
            == portfolio.get_position("AAPL").average_price
        )
