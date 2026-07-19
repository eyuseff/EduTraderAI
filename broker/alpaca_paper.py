from __future__ import annotations

import os
from decimal import Decimal

from .base import AccountSnapshot, BrokerOrder, BrokerPosition


class AlpacaPaperBroker:
    """Alpaca adapter locked to paper trading.

    The class deliberately has no live-mode switch. Paper credentials are read
    from ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables.
    """

    def __init__(self) -> None:
        try:
            from alpaca.trading.client import TradingClient
        except ImportError as exc:
            raise RuntimeError(
                "alpaca-py is not installed. Run: python3 -m pip install alpaca-py"
            ) from exc

        api_key = os.getenv("ALPACA_API_KEY", "").strip()
        secret_key = os.getenv("ALPACA_SECRET_KEY", "").strip()
        if not api_key or not secret_key:
            raise RuntimeError(
                "Missing ALPACA_API_KEY or ALPACA_SECRET_KEY environment variable."
            )

        self._client = TradingClient(api_key, secret_key, paper=True)

    @property
    def name(self) -> str:
        return "Alpaca Paper"

    @property
    def is_paper(self) -> bool:
        return True

    def get_account(self) -> AccountSnapshot:
        account = self._client.get_account()
        equity = float(account.equity)
        last_equity = float(account.last_equity or account.equity)
        return AccountSnapshot(
            equity=equity,
            cash=float(account.cash),
            buying_power=float(account.buying_power),
            daily_pnl=equity - last_equity,
            paper=True,
        )

    def get_positions(self) -> list[BrokerPosition]:
        result: list[BrokerPosition] = []
        for position in self._client.get_all_positions():
            result.append(
                BrokerPosition(
                    symbol=position.symbol,
                    quantity=int(Decimal(str(position.qty))),
                    average_entry_price=float(position.avg_entry_price),
                    current_price=float(position.current_price),
                )
            )
        return result

    def get_open_orders(self) -> list[BrokerOrder]:
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        orders = self._client.get_orders(
            filter=GetOrdersRequest(status=QueryOrderStatus.OPEN)
        )
        return [
            BrokerOrder(
                order_id=str(order.id),
                symbol=order.symbol,
                quantity=int(Decimal(str(order.qty or 0))),
                side=str(order.side.value),
                status=str(order.status.value),
                order_type=str(order.type.value),
                submitted_price=float(order.limit_price or 0),
                message="Alpaca paper order",
            )
            for order in orders
        ]

    def submit_bracket_order(
        self,
        *,
        symbol: str,
        quantity: int,
        entry_price: float,
        stop_price: float,
        target_price: float,
    ) -> BrokerOrder:
        from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
        from alpaca.trading.requests import (
            LimitOrderRequest,
            StopLossRequest,
            TakeProfitRequest,
        )

        request = LimitOrderRequest(
            symbol=symbol.upper(),
            qty=quantity,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=round(entry_price, 2),
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=round(target_price, 2)),
            stop_loss=StopLossRequest(stop_price=round(stop_price, 2)),
            client_order_id=f"edutrader-{symbol.lower()}-{quantity}",
        )
        order = self._client.submit_order(order_data=request)
        return BrokerOrder(
            order_id=str(order.id),
            symbol=order.symbol,
            quantity=int(Decimal(str(order.qty or quantity))),
            side=str(order.side.value),
            status=str(order.status.value),
            order_type="bracket-limit",
            submitted_price=float(order.limit_price or entry_price),
            stop_price=stop_price,
            target_price=target_price,
            message="Submitted to Alpaca paper trading.",
        )

    def cancel_all_orders(self) -> int:
        return len(self._client.cancel_orders())

    def close_all_positions(self) -> int:
        positions = self._client.get_all_positions()
        if positions:
            self._client.close_all_positions(cancel_orders=True)
        return len(positions)
