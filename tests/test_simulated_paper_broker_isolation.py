"""Isolation tests for the real local simulator paper broker."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from uuid import UUID

import pytest

from broker.simulated import SimulatedPaperBroker


def _state_path(tmp_path: Path, name: str = "simulator-state.json") -> Path:
    path = tmp_path / "isolated-simulator" / name
    resolved_tmp = tmp_path.resolve()
    resolved_parent = path.parent.resolve()

    assert resolved_parent == resolved_tmp / "isolated-simulator"
    assert path.name == name
    assert "state/simulated_broker.json" not in path.as_posix()
    assert path.is_absolute()
    assert path.resolve().is_relative_to(resolved_tmp)
    return path


def _read_state(path: Path) -> dict[str, object]:
    assert path.resolve().is_relative_to(path.parent.parent.resolve())
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*args: object, **kwargs: object) -> object:
        raise AssertionError("SimulatedPaperBroker isolation test attempted network use.")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)


def test_simulated_broker_uses_explicit_temp_state_for_order_lifecycle(
    tmp_path: Path,
) -> None:
    path = _state_path(tmp_path)

    broker = SimulatedPaperBroker(starting_cash=12_345.0, state_path=path)

    assert path.exists()
    assert broker.name == "Local Simulator"
    assert broker.is_paper is True
    assert broker.get_positions() == []
    assert broker.get_open_orders() == []
    account = broker.get_account()
    assert account.paper is True
    assert account.cash == 12_345.0
    assert account.buying_power == 12_345.0
    assert account.equity == 12_345.0
    assert _read_state(path) == {
        "cash": 12_345.0,
        "daily_pnl": 0.0,
        "orders": [],
        "positions": [],
    }

    order = broker.submit_bracket_order(
        symbol="aapl",
        quantity=3,
        entry_price=100.25,
        stop_price=97.5,
        target_price=106.75,
    )

    assert UUID(order.order_id).version == 4
    assert order.symbol == "AAPL"
    assert order.quantity == 3
    assert order.side == "buy"
    assert order.status == "accepted"
    assert order.order_type == "bracket-limit-simulation"
    assert order.submitted_price == 100.25
    assert order.stop_price == 97.5
    assert order.target_price == 106.75
    assert order.message == "Recorded by the local simulator; no real order was sent."

    reloaded = SimulatedPaperBroker(starting_cash=99_999.0, state_path=path)
    open_orders = reloaded.get_open_orders()
    assert len(open_orders) == 1
    assert open_orders[0].order_id == order.order_id
    assert open_orders[0].symbol == "AAPL"
    assert reloaded.get_account().cash == 12_345.0

    assert reloaded.cancel_all_orders() == 1
    assert reloaded.get_open_orders() == []
    persisted = _read_state(path)
    assert isinstance(persisted["orders"], list)
    assert persisted["orders"][0]["status"] == "cancelled"

    second_reload = SimulatedPaperBroker(state_path=path)
    assert second_reload.get_open_orders() == []
    assert second_reload.reset(starting_cash=7_000.0) is None
    assert _read_state(path) == {
        "cash": 7_000.0,
        "daily_pnl": 0.0,
        "orders": [],
        "positions": [],
    }
