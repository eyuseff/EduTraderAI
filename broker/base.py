from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class AccountSnapshot:
    equity: float
    cash: float
    buying_power: float
    daily_pnl: float = 0.0
    paper: bool = True


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str
    quantity: int
    average_entry_price: float
    current_price: float

    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price

    @property
    def unrealized_pnl(self) -> float:
        return self.quantity * (self.current_price - self.average_entry_price)


@dataclass(frozen=True)
class BrokerOrder:
    order_id: str
    symbol: str
    quantity: int
    side: str
    status: str
    order_type: str
    submitted_price: float
    stop_price: float | None = None
    target_price: float | None = None
    message: str = ""


@runtime_checkable
class PaperBroker(Protocol):
    """Minimum interface required by the paper execution engine."""

    @property
    def name(self) -> str: ...

    @property
    def is_paper(self) -> bool: ...

    def get_account(self) -> AccountSnapshot: ...

    def get_positions(self) -> list[BrokerPosition]: ...

    def get_open_orders(self) -> list[BrokerOrder]: ...

    def submit_bracket_order(
        self,
        *,
        symbol: str,
        quantity: int,
        entry_price: float,
        stop_price: float,
        target_price: float,
    ) -> BrokerOrder: ...

    def cancel_all_orders(self) -> int: ...

    def close_all_positions(self) -> int: ...
