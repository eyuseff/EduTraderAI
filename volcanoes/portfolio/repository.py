"""SQLite persistence for Portfolio state."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from volcanoes.database.connection import database_session
from volcanoes.domain import Position
from volcanoes.portfolio.portfolio import Portfolio


class PortfolioRepository:
    """Persist and restore the current portfolio state."""

    def __init__(
        self,
        database_path: Path | None = None,
    ) -> None:
        self.database_path = database_path

    def save(self, portfolio: Portfolio) -> int:
        """Save a portfolio snapshot and replace open positions."""

        if not isinstance(portfolio, Portfolio):
            raise TypeError(
                "portfolio must be a Portfolio instance."
            )

        with database_session(
            self.database_path
        ) as connection:
            connection.execute(
                "DELETE FROM positions"
            )

            for position in portfolio.positions.values():
                connection.execute(
                    """
                    INSERT INTO positions (
                        symbol,
                        quantity,
                        average_price
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        position.symbol,
                        position.quantity,
                        str(position.average_price),
                    ),
                )

            cursor = connection.execute(
                """
                INSERT INTO portfolio_snapshots (
                    starting_cash,
                    cash,
                    equity,
                    buying_power,
                    realized_pnl
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(portfolio.starting_cash),
                    str(portfolio.cash),
                    str(portfolio.equity),
                    str(portfolio.buying_power),
                    str(portfolio.realized_pnl),
                ),
            )

            snapshot_id = cursor.lastrowid

        if snapshot_id is None:
            raise RuntimeError(
                "Portfolio snapshot was not saved."
            )

        return snapshot_id

    def load(self) -> Portfolio | None:
        """Restore the latest saved portfolio state."""

        with database_session(
            self.database_path
        ) as connection:
            snapshot = connection.execute(
                """
                SELECT
                    starting_cash,
                    cash,
                    realized_pnl
                FROM portfolio_snapshots
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

            if snapshot is None:
                return None

            position_rows = connection.execute(
                """
                SELECT
                    id,
                    symbol,
                    quantity,
                    average_price
                FROM positions
                ORDER BY symbol
                """
            ).fetchall()

        portfolio = Portfolio(
            starting_cash=Decimal(
                snapshot["starting_cash"]
            )
        )

        portfolio.cash = Decimal(
            snapshot["cash"]
        )

        portfolio.realized_pnl = Decimal(
            snapshot["realized_pnl"]
        )

        portfolio.positions = {
            row["symbol"]: Position(
                id=row["id"],
                symbol=row["symbol"],
                quantity=int(row["quantity"]),
                average_price=Decimal(
                    row["average_price"]
                ),
            )
            for row in position_rows
        }

        return portfolio
