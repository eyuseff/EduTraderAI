"""Paper broker implementation for Volcanes."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from volcanoes.domain import Order, OrderStatus, TradeSide
from volcanoes.execution.broker import Broker


class PaperBroker(Broker):
    """Simulate order execution using cash and in-memory positions."""

    def __init__(
        self,
        initial_cash: Decimal | int | float | str = Decimal("100000.00"),
    ) -> None:
        cash = self._to_decimal(initial_cash)

        if cash <= Decimal("0"):
            raise ValueError("Initial cash must be greater than zero.")

        self._cash_balance = cash
        self._positions: dict[str, int] = {}
        self._orders: list[Order] = []

    def submit_order(self, order: Order) -> Order:
        """Fill or reject an order using deterministic paper rules."""

        if not isinstance(order, Order):
            raise TypeError("Submitted order must be an Order instance.")

        if order.side == TradeSide.BUY:
            self._process_buy(order)
        elif order.side == TradeSide.SELL:
            self._process_sell(order)
        else:
            self._reject(order, "Unsupported order side.")

        self._orders.append(order)
        return order

    def get_cash_balance(self) -> Decimal:
        """Return available cash."""

        return self._cash_balance

    def get_position_quantity(self, symbol: str) -> int:
        """Return the quantity held for a symbol."""

        normalized_symbol = symbol.strip().upper()

        if not normalized_symbol:
            raise ValueError("Symbol cannot be empty.")

        return self._positions.get(normalized_symbol, 0)

    def get_orders(self) -> list[Order]:
        """Return a copy of all submitted orders."""

        return list(self._orders)

    def _process_buy(self, order: Order) -> None:
        """Process a simulated buy order."""

        if order.notional_value > self._cash_balance:
            self._reject(order, "Insufficient cash.")
            return

        self._cash_balance -= order.notional_value

        current_quantity = self.get_position_quantity(order.symbol)
        self._positions[order.symbol] = current_quantity + order.quantity

        self._fill(order)

    def _process_sell(self, order: Order) -> None:
        """Process a simulated sell order."""

        current_quantity = self.get_position_quantity(order.symbol)

        if order.quantity > current_quantity:
            self._reject(order, "Insufficient position quantity.")
            return

        self._cash_balance += order.notional_value

        remaining_quantity = current_quantity - order.quantity

        if remaining_quantity == 0:
            self._positions.pop(order.symbol, None)
        else:
            self._positions[order.symbol] = remaining_quantity

        self._fill(order)

    @staticmethod
    def _fill(order: Order) -> None:
        """Mark an order as filled."""

        order.status = OrderStatus.FILLED
        order.filled_at = datetime.now(UTC)
        order.rejection_reason = None

    @staticmethod
    def _reject(order: Order, reason: str) -> None:
        """Mark an order as rejected."""

        order.status = OrderStatus.REJECTED
        order.filled_at = None
        order.rejection_reason = reason

    @staticmethod
    def _to_decimal(value: Decimal | int | float | str) -> Decimal:
        """Convert a supported numeric value to Decimal safely."""

        if isinstance(value, Decimal):
            return value

        if isinstance(value, bool):
            raise TypeError("Boolean values cannot be used as cash amounts.")

        if isinstance(value, (int, float, str)):
            try:
                return Decimal(str(value))
            except Exception as exc:
                raise ValueError(
                    "Initial cash must be a valid numeric value."
                ) from exc

        raise TypeError(
            "Initial cash must be a Decimal, int, float, or numeric string."
        )
