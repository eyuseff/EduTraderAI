import json
from pathlib import Path

import pytest

from global_rotation.universe import (
    UniverseRegion,
    UniverseSecurity,
    load_universe,
    parse_universe,
)

ROOT = Path(__file__).resolve().parents[1]


def test_starter_universe_is_versioned_global_and_safely_unverified():
    universe = load_universe(ROOT / "data/global_rotation_universe_starter_v1.json")

    assert universe.schema_version == 1
    assert len(universe.regions) == 6
    assert len(universe.active_securities) == 64
    assert len(universe.history_symbols) == 75
    assert {item.code for item in universe.regions} == {
        "US",
        "CA",
        "EU",
        "JP",
        "AU",
        "HK",
    }
    assert all(item.asset_type == "stock" for item in universe.securities)
    assert all(item.etoro_eligible is None for item in universe.securities)
    assert all(item.underlying_buy_x1 is False for item in universe.securities)


def test_universe_rejects_duplicate_symbols():
    payload = json.loads(
        (ROOT / "data/global_rotation_universe_starter_v1.json").read_text()
    )
    payload["securities"].append(dict(payload["securities"][0]))

    with pytest.raises(ValueError, match="symbols must be present and unique"):
        parse_universe(payload)


def test_universe_rejects_non_stock_assets():
    payload = json.loads(
        (ROOT / "data/global_rotation_universe_starter_v1.json").read_text()
    )
    payload["securities"][0]["asset_type"] = "cfd"

    with pytest.raises(ValueError, match="Only listed stocks are allowed"):
        parse_universe(payload)


def test_programmatic_universe_models_reject_false_like_booleans():
    with pytest.raises(ValueError, match="FX inversion"):
        UniverseRegion("JP", "1306.T", "JPY", "JPYUSD=X", fx_invert="false")

    with pytest.raises(ValueError, match="Active status"):
        UniverseSecurity(
            symbol="AAA",
            name="Alpha",
            region="US",
            exchange="NYSE",
            currency="USD",
            active="false",
        )
