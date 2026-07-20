"""Integration tests for the Volcanes application lifecycle."""

from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from volcanoes.application import Application


def test_application_creates_and_persists_portfolio() -> None:
    with TemporaryDirectory() as temporary_directory:
        database_path = (
            Path(temporary_directory)
            / "volcanes_test.db"
        )

        application = Application(
            database_path=database_path,
            starting_cash=Decimal("100000.00"),
        )

        assert application.running is False
        assert application.portfolio is None
        assert application.broker is None

        application.start()

        assert application.running is True
        assert application.portfolio is not None
        assert application.broker is not None
        assert database_path.exists()

        application.portfolio.buy(
            symbol="AAPL",
            quantity=10,
            price=Decimal("200.00"),
        )

        expected_cash = Decimal("98000.00")

        assert application.portfolio.cash == expected_cash

        application.stop()

        assert application.running is False

        restored_application = Application(
            database_path=database_path,
            starting_cash=Decimal("50000.00"),
        )

        restored_application.start()

        assert restored_application.running is True
        assert restored_application.portfolio is not None
        assert restored_application.broker is not None

        assert (
            restored_application.portfolio.starting_cash
            == Decimal("100000.00")
        )

        assert (
            restored_application.portfolio.cash
            == expected_cash
        )

        position = (
            restored_application.portfolio.get_position(
                "AAPL"
            )
        )

        assert position is not None
        assert position.quantity == 10
        assert position.average_price == Decimal("200.00")

        assert (
            restored_application.broker.portfolio
            is restored_application.portfolio
        )

        restored_application.stop()


def test_application_rejects_duplicate_start() -> None:
    with TemporaryDirectory() as temporary_directory:
        database_path = (
            Path(temporary_directory)
            / "volcanes_test.db"
        )

        application = Application(
            database_path=database_path
        )

        application.start()

        with pytest.raises(
            RuntimeError,
            match="already running",
        ):
            application.start()

        application.stop()


def test_application_rejects_stop_before_start() -> None:
    with TemporaryDirectory() as temporary_directory:
        database_path = (
            Path(temporary_directory)
            / "volcanes_test.db"
        )

        application = Application(
            database_path=database_path
        )

        with pytest.raises(
            RuntimeError,
            match="not running",
        ):
            application.stop()
