"""Read-only daily market-data adapters and quality checks."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

import pandas as pd

REQUIRED_COLUMNS = ("Open", "High", "Low", "Close", "Volume")


@dataclass(frozen=True)
class DataQualityIssue:
    symbol: str
    code: str
    message: str


@dataclass(frozen=True)
class DailyHistoryBatch:
    histories: dict[str, pd.DataFrame]
    issues: tuple[DataQualityIssue, ...]
    requested: int

    @property
    def loaded(self) -> int:
        return len(self.histories)


class DailyHistoryProvider(Protocol):
    def load(self, symbols: Sequence[str]) -> DailyHistoryBatch: ...


def validate_daily_history(
    symbol: str,
    frame: pd.DataFrame,
    *,
    minimum_bars: int = 210,
) -> tuple[pd.DataFrame | None, tuple[DataQualityIssue, ...]]:
    """Normalize and quarantine incomplete or internally inconsistent OHLCV."""

    issues: list[DataQualityIssue] = []
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        return None, (
            DataQualityIssue(
                symbol,
                "MISSING_COLUMNS",
                f"Missing OHLCV columns: {', '.join(missing)}.",
            ),
        )
    clean = frame.loc[:, list(REQUIRED_COLUMNS)].copy()
    clean = clean.apply(pd.to_numeric, errors="coerce").dropna()
    clean = clean.loc[~clean.index.duplicated(keep="last")].sort_index()
    if len(clean) < minimum_bars:
        issues.append(
            DataQualityIssue(
                symbol,
                "INSUFFICIENT_BARS",
                f"Only {len(clean)} complete bars; {minimum_bars} required.",
            )
        )
    prices = clean.loc[:, ["Open", "High", "Low", "Close"]]
    if (prices <= 0).any().any():
        issues.append(
            DataQualityIssue(symbol, "NON_POSITIVE_PRICE", "Price is not positive.")
        )
    if (clean["Volume"] < 0).any():
        issues.append(
            DataQualityIssue(symbol, "NEGATIVE_VOLUME", "Volume is negative.")
        )
    invalid_high = clean["High"] < prices.loc[:, ["Open", "Low", "Close"]].max(axis=1)
    invalid_low = clean["Low"] > prices.loc[:, ["Open", "High", "Close"]].min(axis=1)
    if invalid_high.any() or invalid_low.any():
        issues.append(
            DataQualityIssue(
                symbol, "INVALID_OHLC", "OHLC high/low relationships are invalid."
            )
        )
    return (None if issues else clean), tuple(issues)


class YFinanceDailyHistoryProvider:
    """Research-only batched Yahoo Finance reader; never accesses a broker."""

    HARD_SYMBOL_LIMIT = 500

    def __init__(
        self,
        *,
        maximum_symbols: int = 500,
        chunk_size: int = 100,
        period: str = "1y",
        downloader: Callable[..., pd.DataFrame] | None = None,
    ) -> None:
        if maximum_symbols < 1 or chunk_size < 1:
            raise ValueError("Provider limits must be positive.")
        if maximum_symbols > self.HARD_SYMBOL_LIMIT:
            raise ValueError(
                f"Yahoo research adapter cannot be configured above "
                f"{self.HARD_SYMBOL_LIMIT} symbols."
            )
        self.maximum_symbols = maximum_symbols
        self.chunk_size = min(chunk_size, maximum_symbols)
        self.period = period
        self._downloader = downloader

    def load(self, symbols: Sequence[str]) -> DailyHistoryBatch:
        normalized = tuple(
            dict.fromkeys(item.strip().upper() for item in symbols if item.strip())
        )
        if len(normalized) > self.maximum_symbols:
            raise ValueError(
                f"Yahoo research adapter is capped at {self.maximum_symbols} symbols; "
                "use a production market-data provider for larger universes."
            )
        downloader = self._downloader
        if downloader is None:
            try:
                import yfinance as yf
            except ImportError as exc:
                raise RuntimeError(
                    "yfinance is required for the daily research runner."
                ) from exc
            downloader = yf.download

        histories: dict[str, pd.DataFrame] = {}
        issues: list[DataQualityIssue] = []
        for start in range(0, len(normalized), self.chunk_size):
            chunk = normalized[start : start + self.chunk_size]
            try:
                downloaded = downloader(
                    tickers=list(chunk),
                    period=self.period,
                    interval="1d",
                    auto_adjust=False,
                    actions=False,
                    group_by="ticker",
                    threads=True,
                    progress=False,
                )
            except Exception as exc:
                for symbol in chunk:
                    issues.append(
                        DataQualityIssue(
                            symbol, "DOWNLOAD_ERROR", f"Download failed: {exc}"
                        )
                    )
                continue
            for symbol in chunk:
                frame = self._extract_symbol(downloaded, symbol, len(chunk))
                if frame is None or frame.empty:
                    issues.append(
                        DataQualityIssue(
                            symbol, "NO_DATA", "No daily history was returned."
                        )
                    )
                    continue
                clean, symbol_issues = validate_daily_history(symbol, frame)
                issues.extend(symbol_issues)
                if clean is not None:
                    histories[symbol] = clean
        return DailyHistoryBatch(histories, tuple(issues), len(normalized))

    @staticmethod
    def _extract_symbol(
        downloaded: pd.DataFrame,
        symbol: str,
        chunk_length: int,
    ) -> pd.DataFrame | None:
        if not isinstance(downloaded.columns, pd.MultiIndex):
            return downloaded if chunk_length == 1 else None
        first = set(downloaded.columns.get_level_values(0))
        second = set(downloaded.columns.get_level_values(1))
        if symbol in first:
            return downloaded.xs(symbol, axis=1, level=0, drop_level=True)
        if symbol in second:
            return downloaded.xs(symbol, axis=1, level=1, drop_level=True)
        return None
