"""Integration test for Forge trade persistence."""

from decimal import Decimal

from volcanoes.database.models import Trade
from volcanoes.database.repository import SQLiteRepository
from volcanoes.database.schema import initialize_database
from volcanoes.domain import TradeSide, TradeStatus
from volcanoes.execution.forge import Forge
from volcanoes.execution.paper_broker import PaperBroker
from volcanoes.guardian.guardian import Guardian
from volcanoes.portfolio import Portfolio
from volcanoes.scanner.explorer import Explorer


def main() -> None:
    initialize_database()

    explorer = Explorer()
    guardian = Guardian(minimum_score=80)

    portfolio = Portfolio(
        starting_cash=Decimal("100000.00")
    )

    broker = PaperBroker(portfolio=portfolio)

    forge = Forge(
        broker=broker,
        allocation_fraction=0.10,
    )

    repository = SQLiteRepository()

    candidate = explorer.evaluate_symbol("MSFT")
    decision = guardian.evaluate(candidate)
    result = forge.execute(candidate, decision)

    if not result.submitted or result.order is None:
        print("No trade saved:", result.reason)
        return

    if result.order.status.value != "FILLED":
        print(
            "Order was not filled:",
            result.order.status.value,
        )
        return

    trade = Trade(
        candidate_id=candidate.id,
        symbol=candidate.symbol,
        strategy_name=candidate.strategy_name,
        side=TradeSide.BUY,
        quantity=result.order.quantity,
        entry_price=result.order.price,
        status=TradeStatus.OPEN,
        opened_at=result.order.filled_at,
        explanation=candidate.explanation,
    )

    trade_id = repository.save_trade(trade)

    print("\n===== Persistent Trade =====\n")
    print("Trade ID:", trade_id)
    print("Symbol:", trade.symbol)
    print("Quantity:", trade.quantity)
    print("Entry price:", trade.entry_price)
    print("Status:", trade.status.value)
    print(
        "Trades in database:",
        repository.count_rows("trades"),
    )


if __name__ == "__main__":
    main()
