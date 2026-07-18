"""
EduTrader AI
Market Scanner

Downloads market data from Yahoo Finance and computes all
technical indicators required by the application.
"""

from __future__ import annotations

import yfinance as yf

from config import (
    WATCHLIST,
    HISTORY_PERIOD,
    INTERVAL,
    DECIMALS,
)

from logger import setup_logger
from indicators import calculate_indicators

logger = setup_logger()


class MarketScanner:
    """Downloads and prepares market data."""

    REQUIRED_COLUMNS = [
        "Close",
        "RSI",
        "EMA20",
        "EMA50",
        "SMA200",
        "MACD",
        "MACD_SIGNAL",
        "ATR",
    ]

    def scan(self) -> list[dict]:
        """
        Scan every symbol in the watchlist.

        Returns
        -------
        list[dict]
            One dictionary per stock.
        """

        logger.info("Starting market scan...")

        market = []

        for symbol in WATCHLIST:

            logger.info("Scanning %s", symbol)

            try:

                ticker = yf.Ticker(symbol)

                df = ticker.history(
                    period=HISTORY_PERIOD,
                    interval=INTERVAL,
                    auto_adjust=True,
                )

                if df.empty:
                    logger.warning("%s returned no data.", symbol)
                    continue

                df = calculate_indicators(df)

                missing = [
                    col for col in self.REQUIRED_COLUMNS
                    if col not in df.columns
                ]

                if missing:
                    logger.error(
                        "%s is missing indicators: %s",
                        symbol,
                        ", ".join(missing),
                    )
                    continue

                latest = df.iloc[-1]

                if latest[self.REQUIRED_COLUMNS].isnull().any():

                    logger.warning(
                        "%s contains NaN values in indicators.",
                        symbol,
                    )
                    continue

                stock = {

                    "Symbol": symbol,

                    "Price": round(
                        float(latest["Close"]),
                        DECIMALS,
                    ),

                    "RSI": round(
                        float(latest["RSI"]),
                        DECIMALS,
                    ),

                    "EMA20": round(
                        float(latest["EMA20"]),
                        DECIMALS,
                    ),

                    "EMA50": round(
                        float(latest["EMA50"]),
                        DECIMALS,
                    ),

                    "SMA200": round(
                        float(latest["SMA200"]),
                        DECIMALS,
                    ),

                    "MACD": round(
                        float(latest["MACD"]),
                        DECIMALS,
                    ),

                    "Signal": round(
                        float(latest["MACD_SIGNAL"]),
                        DECIMALS,
                    ),

                    "ATR": round(
                        float(latest["ATR"]),
                        DECIMALS,
                    ),
                }

                market.append(stock)

            except Exception:

                logger.exception("Failed scanning %s", symbol)

        logger.info(
            "Market scan completed. %d stocks processed.",
            len(market),
        )

        return market