from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from market.regime import MarketRegime, classify_market
from strategies.trend_momentum import StrategySignal, score_candidate


@dataclass(frozen=True)
class ScanResult:
    regime: MarketRegime
    qualified: list[StrategySignal]
    rejected: list[dict]
    scanned: int


def _rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gains = delta.clip(lower=0).rolling(period).mean()
    losses = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gains / losses.replace(0, np.nan)
    value = 100 - (100 / (1 + rs))
    return float(value.iloc[-1]) if pd.notna(value.iloc[-1]) else 50.0


def _atr(frame: pd.DataFrame, period: int = 14) -> float:
    prev_close = frame["Close"].shift(1)
    tr = pd.concat([
        frame["High"] - frame["Low"],
        (frame["High"] - prev_close).abs(),
        (frame["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    value = tr.rolling(period).mean().iloc[-1]
    return float(value) if pd.notna(value) else float(frame["Close"].iloc[-1] * 0.02)


def download_history(symbols: Iterable[str], period: str = "1y") -> dict[str, pd.DataFrame]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance is required for live scans. Install requirements.txt.") from exc

    output: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        try:
            frame = yf.download(symbol, period=period, interval="1d", auto_adjust=False, progress=False)
            if isinstance(frame.columns, pd.MultiIndex):
                frame.columns = frame.columns.get_level_values(0)
            frame = frame.dropna()
            if len(frame) >= 210:
                output[symbol] = frame
        except Exception:
            continue
    return output


def scan_market(symbols: list[str], min_score: int = 80, max_candidates: int = 10) -> ScanResult:
    history = download_history(list(dict.fromkeys(["SPY", *symbols])))
    spy = history.get("SPY")
    if spy is None:
        raise RuntimeError("SPY history was unavailable; market-regime check cannot run.")

    spy_close = float(spy["Close"].iloc[-1])
    spy_sma50 = float(spy["Close"].rolling(50).mean().iloc[-1])
    spy_sma200 = float(spy["Close"].rolling(200).mean().iloc[-1])
    volatility_pct = float(spy["Close"].pct_change().tail(20).std() * np.sqrt(252) * 100)
    regime = classify_market(spy_close, spy_sma50, spy_sma200, volatility_pct)

    qualified: list[StrategySignal] = []
    rejected: list[dict] = []
    for symbol in symbols:
        frame = history.get(symbol)
        if frame is None:
            rejected.append({"symbol": symbol, "reason": "Insufficient or unavailable market data."})
            continue
        close = float(frame["Close"].iloc[-1])
        previous = float(frame["Close"].iloc[-2])
        signal = score_candidate(
            symbol=symbol,
            close=close,
            sma20=float(frame["Close"].rolling(20).mean().iloc[-1]),
            sma50=float(frame["Close"].rolling(50).mean().iloc[-1]),
            rsi14=_rsi(frame["Close"]),
            atr14=_atr(frame),
            average_volume=float(frame["Volume"].tail(20).mean()),
            daily_change_pct=((close / previous) - 1) * 100,
        )
        if not regime.tradeable:
            rejected.append({"symbol": symbol, "score": signal.score, "reason": f"Market regime is {regime.label}."})
        elif signal.score < min_score:
            rejected.append({"symbol": symbol, "score": signal.score, "reason": f"Score below {min_score}."})
        elif signal.entry_price < 10:
            rejected.append({"symbol": symbol, "score": signal.score, "reason": "Price below $10."})
        elif signal.average_volume < 1_000_000:
            rejected.append({"symbol": symbol, "score": signal.score, "reason": "Average volume below 1,000,000."})
        else:
            qualified.append(signal)

    qualified.sort(key=lambda item: item.score, reverse=True)
    return ScanResult(regime, qualified[:max_candidates], rejected, len(symbols))
