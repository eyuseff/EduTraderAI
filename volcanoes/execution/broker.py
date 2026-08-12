"""Broker abstractions for Volcanes — The Real Volcanoes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from volcanoes.domain import Order


class Broker(ABC):
    """Interface implemented by every Volcanes broker."""

    @abstractmethod
    def submit_order(self, order: Order) -> Order:
        """Submit an order and return its resulting state."""
        raise NotImplementedError

    @abstractmethod
    def get_cash_balance(self) -> Decimal:
        """Return currently available cash."""
        raise NotImplementedError

    @abstractmethod
    def get_position_quantity(self, symbol: str) -> int:
        """Return the current quantity held for one symbol."""
        raise NotImplementedError
