from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from global_rotation.daily import DailyGlobalRotationService
from global_rotation.data import DailyHistoryBatch
from global_rotation.risk import PaperPortfolioContext
from global_rotation.universe import parse_universe


def _history(*, end: str = "2026-08-28", resistance_space: bool = True) -> pd.DataFrame:
    dates = pd.bdate_range(end=end, periods=240)
    price = 80.0
    closes: list[float] = []
    for index in range(240):
        price += (0.8, 0.8, -0.8)[index % 3]
        closes.append(price)
    frame = pd.DataFrame(
        {
            "Open": closes,
            "High": [value + 0.5 for value in closes],
            "Low": [value - 0.5 for value in closes],
            "Close": closes,
            "Volume": [2_000_000.0] * len(closes),
        },
        index=dates,
    )
    if resistance_space:
        frame.loc[frame.index[-30], "High"] = closes[-1] * 1.12
    return frame


class FakeProvider:
    def __init__(self, histories, *, requested=None):
        self.histories = histories
        self.requested = requested

    def load(self, symbols):
        selected = {
            symbol: self.histories[symbol]
            for symbol in symbols
            if symbol in self.histories
        }
        requested = len(symbols) if self.requested is None else self.requested
        return DailyHistoryBatch(selected, (), requested)


def _universe():
    return parse_universe(
        {
            "schema_version": 1,
            "universe_id": "test-global",
            "version": "1",
            "as_of": "2026-08-28",
            "source": "test fixture",
            "regions": [
                {"code": "US", "benchmark_symbol": "SPY", "currency": "USD"},
                {
                    "code": "JP",
                    "benchmark_symbol": "1306.T",
                    "currency": "JPY",
                    "fx_symbol": "JPYUSD=X",
                },
            ],
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
                },
                {
                    "symbol": "BBB.T",
                    "name": "Beta",
                    "region": "JP",
                    "exchange": "TSE",
                    "currency": "JPY",
                    "etoro_eligible": True,
                    "fractional_enabled": True,
                    "underlying_buy_x1": True,
                },
            ],
        }
    )


def _portfolio():
    return PaperPortfolioContext(
        equity_usd=Decimal("10000"),
        buying_power_usd=Decimal("10000"),
        current_exposure_usd=Decimal("0"),
        realized_loss_today_usd=Decimal("0"),
        open_symbols=(),
        qualification_phase=True,
    )


def test_daily_service_runs_regions_with_dynamic_fx_and_deterministic_identity():
    fx = _history()
    fx.loc[:, "Close"] = 0.0068
    histories = {
        "SPY": _history(),
        "1306.T": _history(),
        "JPYUSD=X": fx,
        "AAA": _history(),
        "BBB.T": _history(),
    }
    service = DailyGlobalRotationService(FakeProvider(histories))

    first = service.run(universe=_universe(), portfolio=_portfolio())
    second = service.run(universe=_universe(), portfolio=_portfolio())

    assert first.run_id == second.run_id
    assert first.universe_size == 2
    assert first.as_of_by_region == {
        "US": date(2026, 8, 28),
        "JP": date(2026, 8, 28),
    }
    assert first.fx_as_of_by_region == first.as_of_by_region
    assert {item.symbol for item in first.result.candidates} == {"AAA", "BBB.T"}
    japan = next(item for item in first.result.candidates if item.symbol == "BBB.T")
    assert japan.entry_usd < japan.entry_local

    payload_dates = dict(first.as_of_by_region)
    with pytest.raises(TypeError):
        first.as_of_by_region["US"] = date(1999, 1, 1)
    with pytest.raises(TypeError):
        first.result.regimes["US"] = first.result.regimes["JP"]
    assert dict(first.as_of_by_region) == payload_dates
    assert isinstance(first.result.regimes["US"].reasons, tuple)


def test_daily_identity_changes_with_portfolio_or_market_data_content():
    histories = {
        "SPY": _history(),
        "1306.T": _history(),
        "JPYUSD=X": _history(),
        "AAA": _history(),
        "BBB.T": _history(),
    }
    histories["JPYUSD=X"].loc[:, "Close"] = 0.0068
    baseline = DailyGlobalRotationService(FakeProvider(histories)).run(
        universe=_universe(), portfolio=_portfolio()
    )
    lower_buying_power = PaperPortfolioContext(
        equity_usd=Decimal("10000"),
        buying_power_usd=Decimal("50"),
        current_exposure_usd=Decimal("0"),
        realized_loss_today_usd=Decimal("0"),
        open_symbols=(),
        qualification_phase=True,
    )
    portfolio_changed = DailyGlobalRotationService(FakeProvider(histories)).run(
        universe=_universe(), portfolio=lower_buying_power
    )
    corrected_histories = {key: value.copy() for key, value in histories.items()}
    corrected_histories["AAA"].iloc[
        -1, corrected_histories["AAA"].columns.get_loc("Volume")
    ] += 1
    market_changed = DailyGlobalRotationService(FakeProvider(corrected_histories)).run(
        universe=_universe(), portfolio=_portfolio()
    )

    assert len(baseline.run_id) == 64
    assert baseline.run_id != portfolio_changed.run_id
    assert baseline.run_id != market_changed.run_id
    assert baseline.portfolio_sha256 != portfolio_changed.portfolio_sha256
    assert baseline.market_data_sha256 != market_changed.market_data_sha256


def test_daily_identity_includes_emitted_provider_request_count():
    histories = {
        "SPY": _history(),
        "1306.T": _history(),
        "JPYUSD=X": _history(),
        "AAA": _history(),
        "BBB.T": _history(),
    }
    baseline = DailyGlobalRotationService(FakeProvider(histories)).run(
        universe=_universe(), portfolio=_portfolio()
    )
    changed_metadata = DailyGlobalRotationService(
        FakeProvider(histories, requested=999)
    ).run(universe=_universe(), portfolio=_portfolio())

    assert baseline.histories_requested != changed_metadata.histories_requested
    assert baseline.run_id != changed_metadata.run_id


def test_daily_service_quarantines_symbol_not_aligned_to_regional_close():
    stale = _history(end="2026-08-27")
    histories = {
        "SPY": _history(),
        "1306.T": _history(),
        "JPYUSD=X": _history(),
        "AAA": stale,
        "BBB.T": _history(),
    }
    service = DailyGlobalRotationService(FakeProvider(histories))

    run = service.run(universe=_universe(), portfolio=_portfolio())

    assert {item.symbol for item in run.result.candidates} == {"BBB.T"}
    assert any(
        item.symbol == "AAA" and item.code == "STALE_SESSION"
        for item in run.data_issues
    )


def test_daily_service_uses_fx_from_exact_benchmark_session_not_future_bar():
    future_fx = _history(end="2026-08-31")
    future_fx.loc[:, "Close"] = 0.0068
    future_fx.loc[future_fx.index[-1], "Close"] = 0.02
    histories = {
        "SPY": _history(),
        "1306.T": _history(),
        "JPYUSD=X": future_fx,
        "AAA": _history(),
        "BBB.T": _history(),
    }

    run = DailyGlobalRotationService(FakeProvider(histories)).run(
        universe=_universe(), portfolio=_portfolio()
    )

    japan = next(item for item in run.result.candidates if item.symbol == "BBB.T")
    assert japan.entry_usd < Decimal("1.50")


def test_daily_service_skips_region_when_exact_session_fx_is_missing():
    histories = {
        "SPY": _history(),
        "1306.T": _history(),
        "JPYUSD=X": _history(end="2026-08-27"),
        "AAA": _history(),
        "BBB.T": _history(),
    }

    run = DailyGlobalRotationService(FakeProvider(histories)).run(
        universe=_universe(), portfolio=_portfolio()
    )

    assert {item.symbol for item in run.result.candidates} == {"AAA"}
    assert any(
        item.symbol == "JPYUSD=X" and item.code == "STALE_FX"
        for item in run.data_issues
    )
