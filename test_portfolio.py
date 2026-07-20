"""Basic regression test for the Portfolio."""

from decimal import Decimal

from volcanoes.portfolio import Portfolio


def main() -> None:
    portfolio = Portfolio(
        starting_cash=Decimal("100000.00")
    )

    print("\n===== Portfolio Test =====\n")

    print(f"Initial cash: {portfolio.cash}")

    portfolio.buy(
        symbol="MSFT",
        quantity=25,
        price=Decimal("393.82"),
    )

    print("\nAfter BUY")
    print("---------------------")
    print(f"Cash: {portfolio.cash}")
    print(f"Equity: {portfolio.equity}")

    position = portfolio.get_position("MSFT")

    print(f"Quantity: {position.quantity}")
    print(f"Average Price: {position.average_price}")

    portfolio.sell(
        symbol="MSFT",
        quantity=10,
        price=Decimal("410.00"),
    )

    print("\nAfter SELL 10")
    print("---------------------")
    print(f"Cash: {portfolio.cash}")
    print(f"Realized P&L: {portfolio.realized_pnl}")

    position = portfolio.get_position("MSFT")

    print(f"Remaining: {position.quantity}")

    portfolio.sell(
        symbol="MSFT",
        quantity=15,
        price=Decimal("420.00"),
    )

    print("\nAfter SELL ALL")
    print("---------------------")
    print(f"Cash: {portfolio.cash}")
    print(f"Realized P&L: {portfolio.realized_pnl}")
    print(f"Equity: {portfolio.equity}")
    print(f"Has position: {portfolio.has_position('MSFT')}")


if __name__ == "__main__":
    main()
