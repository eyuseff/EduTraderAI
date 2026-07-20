"""Immutable result of a completed backtest."""

from __future__ import annotations

from dataclasses import dataclass

from volcanoes.portfolio import Portfolio


@dataclass(frozen=True)
class BacktestResult:
    """Summary produced by a completed backtest."""

    total_bars: int
    signals: int
    executed_trades: int
    rejected_trades: int
    portfolio: Portfolio
