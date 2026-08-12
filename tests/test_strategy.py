"""Tests for the Strategy framework."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from volcanoes.market import Bar
from volcanoes.strategy import NoOpStrategy, Strategy


def create_bar() -> Bar:
    price = Decimal("100")

    return Bar(
        symbol="AAPL",
        timestamp=datetime(2026, 7, 20, tzinfo=UTC),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=100,
    )


def test_strategy_is_abstract() -> None:
    with pytest.raises(TypeError):
        Strategy()


def test_noop_strategy_is_strategy() -> None:
    strategy = NoOpStrategy()

    assert isinstance(strategy, Strategy)


def test_noop_strategy_returns_none() -> None:
    strategy = NoOpStrategy()

    assert strategy.on_bar(create_bar()) is None


def test_noop_strategy_is_deterministic() -> None:
    strategy = NoOpStrategy()
    bar = create_bar()

    assert strategy.on_bar(bar) is None
    assert strategy.on_bar(bar) is None
    assert strategy.on_bar(bar) is None


def test_noop_strategy_does_not_modify_bar() -> None:
    strategy = NoOpStrategy()

    bar = create_bar()

    original = (
        bar.symbol,
        bar.timestamp,
        bar.open,
        bar.high,
        bar.low,
        bar.close,
        bar.volume,
    )

    strategy.on_bar(bar)

    assert (
        bar.symbol,
        bar.timestamp,
        bar.open,
        bar.high,
        bar.low,
        bar.close,
        bar.volume,
    ) == original
