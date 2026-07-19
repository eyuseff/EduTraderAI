from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from .base import AccountSnapshot, BrokerOrder, BrokerPosition


class SimulatedPaperBroker:
    """Local, zero-network paper broker.

    Orders are recorded but not assumed to fill automatically. This makes the
    first automation stage safe and testable without API credentials.
    """

    def __init__(
        self,
        starting_cash: float = 100_000.0,
        state_path: str | Path = "state/simulated_broker.json",
    ) -> None:
        self._state_path = Path(state_path)
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._starting_cash = float(starting_cash)
        self._state = self._load_state()

    @property
    def name(self) -> str:
        return "Local Simulator"

    @property
    def is_paper(self) -> bool:
        return True

    def _default_state(self) -> dict:
        return {
            "cash": self._starting_cash,
            "daily_pnl": 0.0,
            "positions": [],
            "orders": [],
        }

    def _load_state(self) -> dict:
        if not self._state_path.exists():
            state = self._default_state()
            self._save_state(state)
            return state
        try:
            return json.loads(self._state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = self._default_state()
            self._save_state(state)
            return state

    def _save_state(self, state: dict | None = None) -> None:
        payload = state if state is not None else self._state
        self._state_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def get_account(self) -> AccountSnapshot:
        positions = self.get_positions()
        equity = float(self._state["cash"]) + sum(p.market_value for p in positions)
        return AccountSnapshot(
            equity=equity,
            cash=float(self._state["cash"]),
            buying_power=float(self._state["cash"]),
            daily_pnl=float(self._state.get("daily_pnl", 0.0)),
            paper=True,
        )

    def get_positions(self) -> list[BrokerPosition]:
        return [BrokerPosition(**item) for item in self._state.get("positions", [])]

    def get_open_orders(self) -> list[BrokerOrder]:
        return [
            BrokerOrder(**item)
            for item in self._state.get("orders", [])
            if item.get("status") in {"accepted", "new", "open"}
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
        order = BrokerOrder(
            order_id=str(uuid4()),
            symbol=symbol.upper(),
            quantity=int(quantity),
            side="buy",
            status="accepted",
            order_type="bracket-limit-simulation",
            submitted_price=float(entry_price),
            stop_price=float(stop_price),
            target_price=float(target_price),
            message="Recorded by the local simulator; no real order was sent.",
        )
        self._state.setdefault("orders", []).append(asdict(order))
        self._save_state()
        return order

    def cancel_all_orders(self) -> int:
        cancelled = 0
        for order in self._state.get("orders", []):
            if order.get("status") in {"accepted", "new", "open"}:
                order["status"] = "cancelled"
                cancelled += 1
        self._save_state()
        return cancelled

    def close_all_positions(self) -> int:
        count = len(self._state.get("positions", []))
        self._state["positions"] = []
        self._save_state()
        return count

    def reset(self, starting_cash: float | None = None) -> None:
        if starting_cash is not None:
            self._starting_cash = float(starting_cash)
        self._state = self._default_state()
        self._save_state()
