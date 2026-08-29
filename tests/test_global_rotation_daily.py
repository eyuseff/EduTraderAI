from datetime import date
from decimal import Decimal

import pandas as pd

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
    def __init__(self, histories):
        self.histories = histories

    def load(self, symbols):
        selected = {
            symbol: self.histories[symbol]
            for symbol in symbols
            if symbol in self.histories
        }
        return DailyHistoryBatch(selected, (), len(symbols))


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
    assert {item.symbol for item in first.result.candidates} == {"AAA", "BBB.T"}
    japan = next(item for item in first.result.candidates if item.symbol == "BBB.T")
    assert japan.entry_usd < japan.entry_local


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
