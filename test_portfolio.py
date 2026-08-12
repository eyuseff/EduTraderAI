"""Regression test for the Portfolio engine."""

from decimal import Decimal

from volcanoes.domain import LedgerEntryType
from volcanoes.portfolio import Portfolio


def main() -> None:
    portfolio = Portfolio(
        starting_cash=Decimal("100000.00")
    )

    print("\n===== Portfolio Test =====\n")
    print("Initial cash:", portfolio.cash)

    portfolio.buy(
        symbol="MSFT",
        quantity=25,
        price=Decimal("393.82"),
    )

    position = portfolio.get_position("MSFT")

    print("\nAfter BUY")
    print("---------------------")
    print("Cash:", portfolio.cash)
    print("Equity:", portfolio.equity)
    print(
        "Quantity:",
        position.quantity if position else 0,
    )
    print(
        "Average Price:",
        position.average_price if position else 0,
    )

    portfolio.sell(
        symbol="MSFT",
        quantity=10,
        price=Decimal("410.00"),
    )

    position = portfolio.get_position("MSFT")

    print("\nAfter SELL 10")
    print("---------------------")
    print("Cash:", portfolio.cash)
    print("Realized P&L:", portfolio.realized_pnl)
    print(
        "Remaining:",
        position.quantity if position else 0,
    )

    portfolio.sell(
        symbol="MSFT",
        quantity=15,
        price=Decimal("420.00"),
    )

    print("\nAfter SELL ALL")
    print("---------------------")
    print("Cash:", portfolio.cash)
    print("Realized P&L:", portfolio.realized_pnl)
    print("Equity:", portfolio.equity)
    print("Has position:", portfolio.has_position("MSFT"))

    print("\nLedger")
    print("---------------------")
    print("Entries:", portfolio.ledger.count())

    for entry in portfolio.ledger.entries:
        print(
            entry.entry_type.value,
            entry.symbol,
            entry.quantity,
            entry.amount,
        )

    assert portfolio.ledger.count() == 3

    assert (
        portfolio.ledger.entries[0].entry_type
        == LedgerEntryType.BUY
    )

    assert (
        portfolio.ledger.entries[1].entry_type
        == LedgerEntryType.SELL
    )

    assert (
        portfolio.ledger.entries[2].entry_type
        == LedgerEntryType.SELL
    )


if __name__ == "__main__":
    main()
