"""Application lifecycle management for Volcanes."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from volcanoes.database.schema import initialize_database
from volcanoes.execution.paper_broker import PaperBroker
from volcanoes.portfolio import Portfolio, PortfolioRepository


class Application:
    """Own and coordinate the core Volcanes services."""

    def __init__(
        self,
        database_path: Path,
        starting_cash: Decimal = Decimal("100000.00"),
    ) -> None:
        if not isinstance(database_path, Path):
            raise TypeError(
                "database_path must be a Path instance."
            )

        if not isinstance(starting_cash, Decimal):
            raise TypeError(
                "starting_cash must be a Decimal."
            )

        if starting_cash <= Decimal("0"):
            raise ValueError(
                "starting_cash must be greater than zero."
            )

        self.database_path = database_path
        self.starting_cash = starting_cash

        self.portfolio_repository: PortfolioRepository | None = None
        self.portfolio: Portfolio | None = None
        self.broker: PaperBroker | None = None

        self._running = False

    @property
    def running(self) -> bool:
        """Return whether the application is running."""

        return self._running

    def start(self) -> None:
        """Initialize the database and restore application state."""

        if self._running:
            raise RuntimeError(
                "Application is already running."
            )

        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        initialize_database(self.database_path)

        self.portfolio_repository = PortfolioRepository(
            self.database_path
        )

        restored_portfolio = (
            self.portfolio_repository.load()
        )

        if restored_portfolio is None:
            self.portfolio = Portfolio(
                starting_cash=self.starting_cash
            )
        else:
            self.portfolio = restored_portfolio

        self.broker = PaperBroker(self.portfolio)
        self._running = True

    def stop(self) -> None:
        """Persist the current state and stop the application."""

        if not self._running:
            raise RuntimeError(
                "Application is not running."
            )

        if self.portfolio_repository is None:
            raise RuntimeError(
                "Portfolio repository is not initialized."
            )

        if self.portfolio is None:
            raise RuntimeError(
                "Portfolio is not initialized."
            )

        self.portfolio_repository.save(
            self.portfolio
        )

        self._running = False
