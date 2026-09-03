import json

import pytest

from scripts.run_global_rotation_daily import _portfolio, _staged_output_directory


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


def test_cli_refuses_to_overwrite_an_existing_run_directory(tmp_path):
    with _staged_output_directory(tmp_path, "same-content-id") as staging:
        (staging / "summary.json").write_text("{}", encoding="utf-8")

    assert (tmp_path / "same-content-id" / "summary.json").is_file()
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        with _staged_output_directory(tmp_path, "same-content-id"):
            pass


def test_cli_does_not_publish_partial_run_after_write_failure(tmp_path):
    with pytest.raises(RuntimeError, match="simulated write failure"):
        with _staged_output_directory(tmp_path, "failed-content-id") as staging:
            (staging / "summary.json").write_text("{}", encoding="utf-8")
            raise RuntimeError("simulated write failure")

    assert not (tmp_path / "failed-content-id").exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("bad_symbol", [None, 7, ""])
def test_cli_rejects_invalid_open_symbol_values(tmp_path, bad_symbol):
    snapshot = tmp_path / "portfolio.json"
    snapshot.write_text(
        json.dumps(
            {
                "equity_usd": "10000",
                "buying_power_usd": "10000",
                "current_exposure_usd": "0",
                "realized_loss_today_usd": "0",
                "open_symbols": [bad_symbol],
                "qualification_phase": True,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="only non-empty strings"):
        _portfolio(snapshot)


@pytest.mark.parametrize(
    "field",
    [
        "equity_usd",
        "buying_power_usd",
        "current_exposure_usd",
        "realized_loss_today_usd",
    ],
)
def test_cli_rejects_non_finite_portfolio_values(tmp_path, field):
    payload = {
        "equity_usd": "10000",
        "buying_power_usd": "10000",
        "current_exposure_usd": "0",
        "realized_loss_today_usd": "0",
        "open_symbols": [],
        "qualification_phase": True,
    }
    payload[field] = "Infinity"
    snapshot = tmp_path / "portfolio.json"
    snapshot.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="finite"):
        _portfolio(snapshot)
