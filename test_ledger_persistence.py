"""Regression test for SQLite ledger persistence."""

from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from volcanoes.database.repository import SQLiteRepository
from volcanoes.database.schema import initialize_database
from volcanoes.domain import LedgerEntry, LedgerEntryType


def main() -> None:
    with TemporaryDirectory() as temporary_directory:
        database_path = (
            Path(temporary_directory)
            / "ledger_test.db"
        )

        initialize_database(database_path)

        repository = SQLiteRepository(database_path)

        buy_entry = LedgerEntry(
            entry_type=LedgerEntryType.BUY,
            amount=Decimal("-9845.50"),
            description="Bought 25 shares of MSFT",
            symbol="MSFT",
            quantity=25,
        )

        sell_entry = LedgerEntry(
            entry_type=LedgerEntryType.SELL,
            amount=Decimal("4100.00"),
            description="Sold 10 shares of MSFT",
            symbol="MSFT",
            quantity=10,
        )

        buy_database_id = (
            repository.save_ledger_entry(buy_entry)
        )

        sell_database_id = (
            repository.save_ledger_entry(sell_entry)
        )

        entries = repository.get_ledger_entries()

        assert buy_database_id == 1
        assert sell_database_id == 2
        assert len(entries) == 2
        assert entries[0] == buy_entry
        assert entries[1] == sell_entry
        assert (
            repository.count_rows("ledger_entries")
            == 2
        )

        print(
            "\n===== Persistent Ledger =====\n"
        )
        print("Entries:", len(entries))

        for entry in entries:
            print(
                entry.entry_type.value,
                entry.symbol,
                entry.quantity,
                entry.amount,
            )


if __name__ == "__main__":
    main()
