"""Translate the active root paper broker into the Volcanes broker port."""

from __future__ import annotations

from decimal import Decimal

from broker.base import PaperBroker
from volcanoes.domain import Order, OrderStatus, TradeSide
from volcanoes.execution.broker import Broker


class PaperBrokerExecutionAdapter(Broker):
    """Narrow order-submission adapter with no trading calculations."""

    _REJECTED_STATUSES = frozenset({"cancelled", "canceled", "expired", "rejected"})
    _FILLED_STATUSES = frozenset({"filled"})

    def __init__(self, broker: PaperBroker) -> None:
        if not isinstance(broker, PaperBroker):
            raise TypeError("broker must satisfy the PaperBroker protocol.")

        if not broker.is_paper:
            raise ValueError("Deterministic submission requires a paper broker.")

        self._broker = broker

    def submit_order(self, order: Order) -> Order:
        """Submit the already-sized bracket order and copy broker metadata."""

        if order.side is not TradeSide.BUY:
            raise ValueError("The active paper broker supports buy brackets only.")

        if order.stop_price is None or order.target_price is None:
            raise ValueError("Bracket orders require stop and target prices.")

        broker_order = self._broker.submit_bracket_order(
            symbol=order.symbol,
            quantity=order.quantity,
            entry_price=float(order.price),
            stop_price=float(order.stop_price),
            target_price=float(order.target_price),
        )
        normalized_status = broker_order.status.strip().lower()

        order.broker_order_id = broker_order.order_id
        order.broker_status = broker_order.status
        order.broker_message = broker_order.message

        if normalized_status in self._REJECTED_STATUSES:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = broker_order.message or (
                f"Broker returned status {broker_order.status}."
            )
        elif normalized_status in self._FILLED_STATUSES:
            order.status = OrderStatus.FILLED
        else:
            order.status = OrderStatus.PENDING

        return order

    def get_cash_balance(self) -> Decimal:
        """Return root-broker cash without mutating broker state."""

        return Decimal(str(self._broker.get_account().cash))

    def get_position_quantity(self, symbol: str) -> int:
        """Return the current root-broker quantity for a normalized symbol."""

        normalized_symbol = symbol.strip().upper()
        return sum(
            position.quantity
            for position in self._broker.get_positions()
            if position.symbol.strip().upper() == normalized_symbol
        )

    @property
    def root_broker(self) -> PaperBroker:
        """Expose the wrapped broker to the outer composition layer only."""

        return self._broker
