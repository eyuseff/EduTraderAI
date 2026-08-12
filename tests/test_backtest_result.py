"""Tests for BacktestResult."""

from decimal import Decimal

from volcanoes.backtest import BacktestResult
from volcanoes.portfolio import Portfolio


def test_backtest_result_stores_values() -> None:
    portfolio = Portfolio(
        starting_cash=Decimal("100000"),
    )

    result = BacktestResult(
        total_bars=100,
        signals=12,
        executed_trades=10,
        rejected_trades=2,
        portfolio=portfolio,
    )

    assert result.total_bars == 100
    assert result.signals == 12
    assert result.executed_trades == 10
    assert result.rejected_trades == 2
    assert result.portfolio is portfolio
