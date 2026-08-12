"""Regression test for the Ledger."""

from decimal import Decimal

from volcanoes.domain import LedgerEntry, LedgerEntryType
from volcanoes.ledger import Ledger


def main() -> None:
    ledger = Ledger()

    ledger.record(
        LedgerEntry(
            entry_type=LedgerEntryType.BUY,
            amount=Decimal("-9845.50"),
            description="Bought 25 shares of MSFT",
            symbol="MSFT",
            quantity=25,
        )
    )

    ledger.record(
        LedgerEntry(
            entry_type=LedgerEntryType.SELL,
            amount=Decimal("4100.00"),
            description="Sold 10 shares of MSFT",
            symbol="MSFT",
            quantity=10,
        )
    )

    print("\n===== Ledger Test =====\n")
    print("Entries:", ledger.count())

    for entry in ledger.entries:
        print(
            f"{entry.entry_type.value:<6} "
            f"{entry.symbol or '-':<6} "
            f"{entry.quantity or 0:<4} "
            f"{entry.amount}"
        )


if __name__ == "__main__":
    main()
