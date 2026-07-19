"""Market-data gateway for Volcanes — The Real Volcanoes."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import yfinance as yf


@dataclass(frozen=True)
class MarketSnapshot:
    """Validated latest market information for one symbol."""

    symbol: str
    price: float
    previous_close: float
    volume: int
    change_percent: float


class Sentinel:
    """Collect, normalize, and validate market data."""

    REQUIRED_COLUMNS = {
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    }

    def download_history(
        self,
        symbol: str,
        period: str = "6mo",
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Download and validate historical market data."""

        normalized_symbol = symbol.strip().upper()

        if not normalized_symbol:
            raise ValueError("Symbol cannot be empty.")

        data = yf.download(
            normalized_symbol,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
        )

        if data.empty:
            raise LookupError(
                f"No market data was returned for {normalized_symbol}."
            )

        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        missing_columns = self.REQUIRED_COLUMNS.difference(data.columns)

        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(
                f"Market data for {normalized_symbol} is missing: {missing}"
            )

        clean_data = data.copy()
        clean_data = clean_data.dropna(subset=["Close"])
        clean_data.index = pd.to_datetime(clean_data.index)

        if clean_data.empty:
            raise ValueError(
                f"Market data for {normalized_symbol} contains no valid prices."
            )

        return clean_data

    def get_snapshot(self, symbol: str) -> MarketSnapshot:
        """Return a normalized snapshot using the latest two sessions."""

        normalized_symbol = symbol.strip().upper()
        history = self.download_history(
            normalized_symbol,
            period="5d",
            interval="1d",
        )

        if len(history) < 2:
            raise ValueError(
                f"At least two sessions are required for {normalized_symbol}."
            )

        latest = history.iloc[-1]
        previous = history.iloc[-2]

        price = float(latest["Close"])
        previous_close = float(previous["Close"])
        volume = int(latest["Volume"])

        change_percent = (
            ((price - previous_close) / previous_close) * 100
            if previous_close != 0
            else 0.0
        )

        return MarketSnapshot(
            symbol=normalized_symbol,
            price=price,
            previous_close=previous_close,
            volume=volume,
            change_percent=change_percent,
        )
