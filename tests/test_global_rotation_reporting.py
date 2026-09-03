from datetime import date
from decimal import Decimal

import pandas as pd

from global_rotation.daily import DailyGlobalRotationRun
from global_rotation.data import DataQualityIssue
from global_rotation.engine import GlobalRotationEngine
from global_rotation.reporting import candidate_rows, run_payload
from global_rotation.risk import PaperPortfolioContext
from global_rotation.universe import parse_universe


def _history() -> pd.DataFrame:
    dates = pd.bdate_range(end="2026-08-28", periods=240)
    price = 80.0
    closes = []
    for index in range(240):
        price += (0.8, 0.8, -0.8)[index % 3]
        closes.append(price)
    frame = pd.DataFrame(
        {
            "Open": closes,
            "High": [value + 0.5 for value in closes],
            "Low": [value - 0.5 for value in closes],
            "Close": closes,
            "Volume": 2_000_000,
        },
        index=dates,
    )
    frame.loc[frame.index[-30], "High"] = closes[-1] * 1.12
    return frame


def test_reporting_payload_is_auditable_and_explicitly_non_executing():
    universe = parse_universe(
        {
            "schema_version": 1,
            "universe_id": "report-test",
            "version": "1",
            "as_of": "2026-08-28",
            "source": "test fixture",
            "regions": [{"code": "US", "benchmark_symbol": "SPY", "currency": "USD"}],
            "securities": [
                {
                    "symbol": "AAA",
                    "name": "Alpha",
                    "region": "US",
                    "exchange": "NYSE",
                    "currency": "USD",
                    "etoro_eligible": True,
                    "fractional_enabled": True,
                    "underlying_buy_x1": True,
                }
            ],
        }
    )
    result = GlobalRotationEngine(
        regions=[item.to_region_config() for item in universe.regions]
    ).scan(
        instruments=[universe.securities[0].to_instrument(fx_to_usd=Decimal("1"))],
        histories={"SPY": _history(), "AAA": _history()},
        portfolio=PaperPortfolioContext(
            equity_usd=Decimal("10000"),
            buying_power_usd=Decimal("10000"),
            current_exposure_usd=Decimal("0"),
            realized_loss_today_usd=Decimal("0"),
            open_symbols=(),
            qualification_phase=True,
        ),
    )
    run = DailyGlobalRotationRun(
        run_id="abc123",
        operator_schema="global-rotation-daily-output-v2",
        universe_sha256="a" * 64,
        portfolio_sha256="b" * 64,
        market_data_sha256="c" * 64,
        data_quality_sha256="d" * 64,
        result_sha256="e" * 64,
        risk_policy_sha256="f" * 64,
        rotation_policy_sha256="0" * 64,
        universe_id=universe.universe_id,
        universe_version=universe.version,
        universe_size=1,
        histories_requested=2,
        histories_loaded=2,
        as_of_by_region={"US": date(2026, 8, 28)},
        fx_as_of_by_region={"US": date(2026, 8, 28)},
        result=result,
        data_issues=(DataQualityIssue("ZZZ", "NO_DATA", "Missing."),),
    )

    rows = candidate_rows(run)
    payload = run_payload(run)

    assert rows[0]["first_invalidation"].startswith("Close below stop")
    assert payload["execution"] == {
        "mode": "RESEARCH_PAPER_PREVIEW_ONLY",
        "orders_submitted": 0,
        "manual_confirmation_required": True,
    }
    assert payload["market_data"]["as_of_by_region"]["US"] == "2026-08-28"
    assert payload["market_data"]["fx_as_of_by_region"]["US"] == "2026-08-28"
    assert payload["evidence_fingerprints"] == {
        "operator_schema": "global-rotation-daily-output-v2",
        "universe_sha256": "a" * 64,
        "portfolio_sha256": "b" * 64,
        "market_data_sha256": "c" * 64,
        "data_quality_sha256": "d" * 64,
        "result_sha256": "e" * 64,
        "risk_policy_sha256": "f" * 64,
        "rotation_policy_sha256": "0" * 64,
    }
