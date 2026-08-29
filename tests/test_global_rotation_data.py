import pandas as pd

from global_rotation.data import (
    YFinanceDailyHistoryProvider,
    validate_daily_history,
)


def _history(rows: int = 220) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=rows, freq="B")
    close = pd.Series([100 + index * 0.1 for index in range(rows)], index=index)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 1,
            "Low": close - 1,
            "Close": close,
            "Volume": 2_000_000,
        },
        index=index,
    )


def test_yfinance_provider_extracts_multi_symbol_batches_without_network():
    downloaded = pd.concat({"AAA": _history(), "BBB": _history()}, axis=1)

    def downloader(**kwargs):
        assert kwargs["tickers"] == ["AAA", "BBB"]
        assert kwargs["auto_adjust"] is False
        return downloaded

    provider = YFinanceDailyHistoryProvider(downloader=downloader)
    batch = provider.load(["aaa", "BBB", "AAA"])

    assert batch.requested == 2
    assert batch.loaded == 2
    assert batch.issues == ()
    assert tuple(batch.histories["AAA"].columns) == (
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    )


def test_invalid_ohlc_is_quarantined():
    frame = _history()
    frame.loc[frame.index[-1], "High"] = frame["Low"].iloc[-1] - 1

    clean, issues = validate_daily_history("BAD", frame)

    assert clean is None
    assert [item.code for item in issues] == ["INVALID_OHLC"]


def test_yahoo_research_adapter_refuses_unreviewed_large_scale():
    provider = YFinanceDailyHistoryProvider(
        maximum_symbols=2, downloader=lambda **_: _history()
    )

    try:
        provider.load(["AAA", "BBB", "CCC"])
    except ValueError as exc:
        assert "production market-data provider" in str(exc)
    else:
        raise AssertionError("Provider limit should block an oversized request.")

    try:
        YFinanceDailyHistoryProvider(maximum_symbols=8_000)
    except ValueError as exc:
        assert "cannot be configured above 500" in str(exc)
    else:
        raise AssertionError("Yahoo hard safety cap should not be configurable away.")
