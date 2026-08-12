"""Tests for application-level local simulator state isolation."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from uuid import UUID

import pytest

from broker import app_runtime
from broker.simulated import SimulatedPaperBroker

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*args: object, **kwargs: object) -> object:
        raise AssertionError("application simulator state override attempted network use")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)
    monkeypatch.setattr(socket.socket, "connect_ex", fail_network)


def _override_path(tmp_path: Path, name: str = "app-simulator-state.json") -> Path:
    state_path = tmp_path / "app-runtime" / name
    assert state_path.is_absolute()
    assert state_path.resolve().is_relative_to(tmp_path.resolve())
    return state_path


def _read_json(path: Path) -> dict[str, object]:
    assert path.resolve().is_relative_to(path.parent.parent.resolve())
    return json.loads(path.read_text(encoding="utf-8"))


def test_valid_absolute_override_builds_real_simulator_and_persists_under_tmp_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    state_path = _override_path(tmp_path)
    monkeypatch.setenv(
        app_runtime.SIMULATED_BROKER_STATE_PATH_ENV,
        str(state_path),
    )

    broker = app_runtime.build_local_simulated_broker(starting_cash=25_000.0)

    assert isinstance(broker, SimulatedPaperBroker)
    assert state_path.exists()
    assert state_path.resolve().is_relative_to(tmp_path.resolve())
    assert _read_json(state_path) == {
        "cash": 25_000.0,
        "daily_pnl": 0.0,
        "orders": [],
        "positions": [],
    }
    account = broker.get_account()
    assert account.cash == 25_000.0
    assert account.equity == 25_000.0

    order = broker.submit_bracket_order(
        symbol="msft",
        quantity=2,
        entry_price=310.0,
        stop_price=300.0,
        target_price=330.0,
    )
    assert UUID(order.order_id).version == 4
    assert order.symbol == "MSFT"

    reloaded = app_runtime.build_local_simulated_broker(starting_cash=1_000.0)
    open_orders = reloaded.get_open_orders()
    assert len(open_orders) == 1
    assert open_orders[0].order_id == order.order_id
    assert reloaded.get_account().cash == 25_000.0


@pytest.mark.parametrize("raw_value", ("", "   "))
def test_blank_override_fails_before_simulator_construction(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
) -> None:
    calls: list[object] = []
    monkeypatch.setenv(app_runtime.SIMULATED_BROKER_STATE_PATH_ENV, raw_value)
    monkeypatch.setattr(
        app_runtime,
        "SimulatedPaperBroker",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    with pytest.raises(ValueError, match="non-empty absolute path"):
        app_runtime.build_local_simulated_broker(starting_cash=10_000.0)

    assert calls == []


def test_relative_override_fails_before_simulator_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    monkeypatch.setenv(
        app_runtime.SIMULATED_BROKER_STATE_PATH_ENV,
        "relative/simulator.json",
    )
    monkeypatch.setattr(
        app_runtime,
        "SimulatedPaperBroker",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    with pytest.raises(ValueError, match="must be absolute"):
        app_runtime.build_local_simulated_broker(starting_cash=10_000.0)

    assert calls == []


def test_repository_path_override_fails_before_simulator_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    repository_path = PROJECT_ROOT / "tmp-simulator.json"
    monkeypatch.setenv(
        app_runtime.SIMULATED_BROKER_STATE_PATH_ENV,
        str(repository_path),
    )
    monkeypatch.setattr(
        app_runtime,
        "SimulatedPaperBroker",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    with pytest.raises(ValueError, match="outside the repository"):
        app_runtime.build_local_simulated_broker(starting_cash=10_000.0)

    assert calls == []


def test_symlinked_parent_into_repository_fails_before_simulator_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[object] = []
    link = tmp_path / "repo-link"
    link.symlink_to(PROJECT_ROOT, target_is_directory=True)
    monkeypatch.setenv(
        app_runtime.SIMULATED_BROKER_STATE_PATH_ENV,
        str(link / "simulator.json"),
    )
    monkeypatch.setattr(
        app_runtime,
        "SimulatedPaperBroker",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    with pytest.raises(ValueError, match="outside the repository"):
        app_runtime.build_local_simulated_broker(starting_cash=10_000.0)

    assert calls == []


def test_absent_override_preserves_legacy_constructor_without_real_default_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class SentinelBroker:
        pass

    def constructor(*args: object, **kwargs: object) -> SentinelBroker:
        calls.append((args, kwargs))
        return SentinelBroker()

    monkeypatch.delenv(app_runtime.SIMULATED_BROKER_STATE_PATH_ENV, raising=False)
    monkeypatch.setattr(app_runtime, "SimulatedPaperBroker", constructor)

    broker = app_runtime.build_local_simulated_broker(starting_cash=12_000.0)

    assert isinstance(broker, SentinelBroker)
    assert calls == [((), {"starting_cash": 12_000.0})]


def test_app_static_wiring_uses_runtime_builder_without_direct_simulator_construction() -> (
    None
):
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")

    assert "from broker.app_runtime import build_local_simulated_broker" in source
    assert "return build_local_simulated_broker(starting_cash=starting_cash)" in source
    assert "from broker.simulated import SimulatedPaperBroker" not in source
    assert "SimulatedPaperBroker(" not in source
