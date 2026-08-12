"""Paper broker implementation for Volcanes."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from volcanoes.domain import Order, OrderStatus, TradeSide
from volcanoes.execution.broker import Broker
from volcanoes.portfolio import Portfolio


class PaperBroker(Broker):
    """Simulate order execution through a Portfolio account."""

    def __init__(self, portfolio: Portfolio) -> None:
        if not isinstance(portfolio, Portfolio):
            raise TypeError(
                "PaperBroker requires a Portfolio instance."
            )

        self._portfolio = portfolio
        self._orders: list[Order] = []

    def submit_order(self, order: Order) -> Order:
        """Fill or reject an order using deterministic paper rules."""

        if not isinstance(order, Order):
            raise TypeError(
                "Submitted order must be an Order instance."
            )

        if order.side == TradeSide.BUY:
            self._process_buy(order)
        elif order.side == TradeSide.SELL:
            self._process_sell(order)
        else:
            self._reject(
                order,
                "Unsupported order side.",
            )

        self._orders.append(order)
        return order

    def get_cash_balance(self) -> Decimal:
        """Return available portfolio cash."""

        return self._portfolio.cash

    def get_position_quantity(self, symbol: str) -> int:
        """Return the quantity held for a symbol."""

        normalized_symbol = symbol.strip().upper()

        if not normalized_symbol:
            raise ValueError(
                "Symbol cannot be empty."
            )

        position = self._portfolio.get_position(
            normalized_symbol
        )

        if position is None:
            return 0

        return position.quantity

    def get_orders(self) -> list[Order]:
        """Return a copy of all submitted orders."""

        return list(self._orders)

    @property
    def portfolio(self) -> Portfolio:
        """Return the portfolio used by this broker."""

        return self._portfolio

    def _process_buy(self, order: Order) -> None:
        """Process a simulated buy order."""

        try:
            self._portfolio.buy(
                symbol=order.symbol,
                quantity=order.quantity,
                price=order.price,
            )
        except ValueError as exc:
            self._reject(
                order,
                str(exc),
            )
            return

        self._fill(order)

    def _process_sell(self, order: Order) -> None:
        """Process a simulated sell order."""

        try:
            self._portfolio.sell(
                symbol=order.symbol,
                quantity=order.quantity,
                price=order.price,
            )
        except ValueError as exc:
            self._reject(
                order,
                str(exc),
            )
            return

        self._fill(order)

    @staticmethod
    def _fill(order: Order) -> None:
        """Mark an order as filled."""

        order.status = OrderStatus.FILLED
        order.filled_at = datetime.now(UTC)
        order.rejection_reason = None

    @staticmethod
    def _reject(
        order: Order,
        reason: str,
    ) -> None:
        """Mark an order as rejected."""

        order.status = OrderStatus.REJECTED
        order.filled_at = None
        order.rejection_reason = reason
