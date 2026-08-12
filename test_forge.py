from volcanoes.execution.forge import Forge
from volcanoes.execution.paper_broker import PaperBroker
from volcanoes.guardian.guardian import Guardian
from volcanoes.scanner.explorer import Explorer


def main() -> None:
    explorer = Explorer()
    guardian = Guardian(minimum_score=80)
    broker = PaperBroker(initial_cash=100_000)
    forge = Forge(broker=broker, allocation_fraction=0.10)

    candidate = explorer.evaluate_symbol("MSFT")
    decision = guardian.evaluate(candidate)
    result = forge.execute(candidate, decision)

    print("\n===== Forge Result =====\n")
    print("Symbol:", candidate.symbol)
    print("Score:", candidate.score)
    print("Guardian approved:", decision.approved)
    print("Submitted:", result.submitted)
    print("Reason:", result.reason)

    if result.order is not None:
        print("Order status:", result.order.status.value)
        print("Quantity:", result.order.quantity)
        print("Price:", result.order.price)
        print("Notional:", result.order.notional_value)

    print("Cash remaining:", broker.get_cash_balance())
    print(
        "Position quantity:",
        broker.get_position_quantity(candidate.symbol),
    )


if __name__ == "__main__":
    main()
