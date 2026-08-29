import json

import pytest

from scripts.run_global_rotation_daily import _portfolio


def test_cli_requires_complete_portfolio_truth(tmp_path):
    snapshot = tmp_path / "portfolio.json"
    snapshot.write_text(json.dumps({"equity_usd": "10000"}), encoding="utf-8")

    with pytest.raises(ValueError, match="Portfolio snapshot is missing"):
        _portfolio(snapshot)


def test_cli_rejects_string_boolean_in_portfolio_snapshot(tmp_path):
    snapshot = tmp_path / "portfolio.json"
    snapshot.write_text(
        json.dumps(
            {
                "equity_usd": "10000",
                "buying_power_usd": "10000",
                "current_exposure_usd": "0",
                "realized_loss_today_usd": "0",
                "open_symbols": [],
                "qualification_phase": "false",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="qualification_phase must be true or false"):
        _portfolio(snapshot)
