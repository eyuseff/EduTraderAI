from __future__ import annotations

import builtins
import json
import os
import socket
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.paper_qualification_preflight import build_preflight_evidence, main


def test_preflight_builds_exactly_one_non_marketable_limit_share() -> None:
    evidence = build_preflight_evidence(
        symbol=" aapl ",
        reference_best_ask=Decimal("100.50"),
    )

    assert evidence["schema_version"] == "paper-qualification-preflight-v1"
    assert evidence["preflight_passed"] is True
    assert evidence["environment"] == "PAPER"
    assert evidence["order_intent"] == {
        "symbol": "AAPL",
        "side": "BUY",
        "quantity": 1,
        "order_type": "LIMIT",
        "time_in_force": "DAY",
        "limit_price": "100.49",
    }
    assert evidence["reference_best_ask"] == "100.50"
    assert evidence["tick_size"] == "0.01"
    assert evidence["non_marketable"] is True


@pytest.mark.parametrize(
    "flag",
    (
        "action_executed",
        "broker_accessed",
        "credentials_loaded",
        "network_used",
        "persistence_accessed",
        "runtime_changed",
    ),
)
def test_preflight_effect_flags_are_false(flag: str) -> None:
    evidence = build_preflight_evidence(
        symbol="AAPL",
        reference_best_ask=Decimal("100.50"),
    )

    assert evidence[flag] is False


def test_preflight_has_no_external_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("external effect attempted")

    monkeypatch.setattr(builtins, "open", fail)
    monkeypatch.setattr(Path, "read_text", fail)
    monkeypatch.setattr(Path, "write_text", fail)
    monkeypatch.setattr(Path, "write_bytes", fail)
    monkeypatch.setattr(socket, "socket", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(os, "getenv", fail)

    evidence = build_preflight_evidence(
        symbol="AAPL",
        reference_best_ask=Decimal("100.50"),
    )

    assert evidence["preflight_passed"] is True
    assert evidence["action_executed"] is False


def test_cli_emits_deterministic_json(capsys: pytest.CaptureFixture[str]) -> None:
    args = ["--symbol", "AAPL", "--reference-best-ask", "100.50"]

    assert main(args) == 0
    first = capsys.readouterr().out
    assert main(args) == 0
    second = capsys.readouterr().out

    assert first == second
    payload = json.loads(first)
    assert payload["preflight_passed"] is True
    assert payload["order_intent"]["side"] == "BUY"
    assert payload["action_executed"] is False
    assert payload["credentials_loaded"] is False
    assert payload["network_used"] is False


def test_cli_never_emits_secret_shaped_fields(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--symbol", "AAPL", "--reference-best-ask", "100.50"]) == 0

    rendered = capsys.readouterr().out.lower()
    assert "api_key" not in rendered
    assert "password" not in rendered
    assert "access_token" not in rendered
    assert "authorization" not in rendered
