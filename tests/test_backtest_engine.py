"""Tests for the deterministic BacktestEngine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from volcanoes.backtest import BacktestEngine
from volcanoes.domain import TradeIntent, TradeSide
from volcanoes.execution import ExecutionPipeline, PaperBroker
from volcanoes.market import Bar, HistoricalFeed
from volcanoes.portfolio import Portfolio
from volcanoes.risk import RiskConfig, RiskManager
from volcanoes.strategy import NoOpStrategy, Strategy


def create_bar(
    *,
    symbol: str = "AAPL",
    day_offset: int = 0,
    price: str = "100",
) -> Bar:
    """Create a valid market bar for backtest tests."""

    market_price = Decimal(price)

    return Bar(
        symbol=symbol,
        timestamp=(
            datetime(2026, 7, 20, 14, 30, tzinfo=UTC)
            + timedelta(days=day_offset)
        ),
        open=market_price,
        high=market_price,
        low=market_price,
        close=market_price,
        volume=1000,
    )


class BuyFirstBarStrategy(Strategy):
    """Generate one buy intent from the first received bar."""

    def __init__(self) -> None:
        self._signal_generated = False

    def on_bar(self, bar: Bar) -> TradeIntent | None:
        if self._signal_generated:
            return None

        self._signal_generated = True

        return TradeIntent(
            symbol=bar.symbol,
            side=TradeSide.BUY,
            entry_price=bar.close,
            stop_price=bar.close - Decimal("5"),
        )


class BuyEveryBarStrategy(Strategy):
    """Generate a buy intent for every received bar."""

    def on_bar(self, bar: Bar) -> TradeIntent | None:
        return TradeIntent(
            symbol=bar.symbol,
            side=TradeSide.BUY,
            entry_price=bar.close,
            stop_price=bar.close - Decimal("5"),
        )


def create_engine(
    *,
    bars: list[Bar],
    strategy: Strategy,
    starting_cash: str = "100000",
    risk_manager: RiskManager | None = None,
) -> BacktestEngine:
    """Create a complete in-memory backtest stack."""

    portfolio = Portfolio(
        starting_cash=Decimal(starting_cash),
    )
    broker = PaperBroker(portfolio)
    pipeline = ExecutionPipeline(
        broker=broker,
        risk_manager=risk_manager,
    )

    return BacktestEngine(
        feed=HistoricalFeed(bars),
        strategy=strategy,
        pipeline=pipeline,
        portfolio=portfolio,
    )


def test_backtest_engine_returns_zero_counts_for_empty_feed() -> None:
    engine = create_engine(
        bars=[],
        strategy=NoOpStrategy(),
    )

    result = engine.run()

    assert result.total_bars == 0
    assert result.signals == 0
    assert result.executed_trades == 0
    assert result.rejected_trades == 0
    assert result.portfolio is engine.portfolio


def test_backtest_engine_processes_every_bar() -> None:
    bars = [
        create_bar(day_offset=0),
        create_bar(day_offset=1),
        create_bar(day_offset=2),
    ]

    engine = create_engine(
        bars=bars,
        strategy=NoOpStrategy(),
    )

    result = engine.run()

    assert result.total_bars == 3
    assert engine.feed.has_next() is False


def test_noop_strategy_generates_no_trades() -> None:
    engine = create_engine(
        bars=[create_bar()],
        strategy=NoOpStrategy(),
    )

    result = engine.run()

    assert result.signals == 0
    assert result.executed_trades == 0
    assert result.rejected_trades == 0
    assert result.portfolio.open_positions == 0
    assert result.portfolio.ledger.count() == 0


def test_backtest_engine_executes_strategy_signal() -> None:
    engine = create_engine(
        bars=[create_bar()],
        strategy=BuyFirstBarStrategy(),
    )

    result = engine.run()

    assert result.total_bars == 1
    assert result.signals == 1
    assert result.executed_trades == 1
    assert result.rejected_trades == 0

    assert result.portfolio.open_positions == 1
    assert result.portfolio.ledger.count() == 1

    position = result.portfolio.get_position("AAPL")

    assert position is not None
    assert position.quantity == 200
    assert position.average_price == Decimal("100")


def test_backtest_engine_counts_only_actual_signals() -> None:
    bars = [
        create_bar(day_offset=0),
        create_bar(day_offset=1),
        create_bar(day_offset=2),
    ]

    engine = create_engine(
        bars=bars,
        strategy=BuyFirstBarStrategy(),
    )

    result = engine.run()

    assert result.total_bars == 3
    assert result.signals == 1
    assert result.executed_trades == 1


def test_zero_quantity_result_is_counted_as_rejected() -> None:
    engine = create_engine(
        bars=[
            create_bar(
                symbol="EXPENSIVE",
                price="1000",
            )
        ],
        strategy=BuyFirstBarStrategy(),
        starting_cash="100",
    )

    result = engine.run()

    assert result.signals == 1
    assert result.executed_trades == 0
    assert result.rejected_trades == 1
    assert result.portfolio.open_positions == 0
    assert result.portfolio.ledger.count() == 0


def test_risk_violation_is_counted_without_stopping_run() -> None:
    risk_manager = RiskManager(
        RiskConfig(
            max_risk_per_trade=Decimal("0.01"),
            max_daily_loss=Decimal("0.03"),
            max_portfolio_exposure=Decimal("0.80"),
            max_position_size=Decimal("0.10"),
            max_open_positions=10,
        )
    )

    bars = [
        create_bar(symbol="AAPL", day_offset=0),
        create_bar(symbol="MSFT", day_offset=1),
    ]

    engine = create_engine(
        bars=bars,
        strategy=BuyEveryBarStrategy(),
        risk_manager=risk_manager,
    )

    result = engine.run()

    assert result.total_bars == 2
    assert result.signals == 2
    assert result.executed_trades == 0
    assert result.rejected_trades == 2
    assert result.portfolio.open_positions == 0
    assert result.portfolio.ledger.count() == 0


def test_backtest_result_contains_engine_portfolio() -> None:
    engine = create_engine(
        bars=[create_bar()],
        strategy=BuyFirstBarStrategy(),
    )

    result = engine.run()

    assert result.portfolio is engine.portfolio


def test_second_run_on_consumed_feed_processes_no_bars() -> None:
    engine = create_engine(
        bars=[create_bar()],
        strategy=NoOpStrategy(),
    )

    first_result = engine.run()
    second_result = engine.run()

    assert first_result.total_bars == 1
    assert second_result.total_bars == 0


@pytest.mark.parametrize(
    ("argument_name", "invalid_value"),
    [
        ("feed", object()),
        ("strategy", object()),
        ("pipeline", object()),
        ("portfolio", object()),
    ],
)
def test_backtest_engine_rejects_invalid_components(
    argument_name: str,
    invalid_value: object,
) -> None:
    portfolio = Portfolio(
        starting_cash=Decimal("100000"),
    )
    broker = PaperBroker(portfolio)

    arguments: dict[str, object] = {
        "feed": HistoricalFeed([]),
        "strategy": NoOpStrategy(),
        "pipeline": ExecutionPipeline(broker),
        "portfolio": portfolio,
    }
    arguments[argument_name] = invalid_value

    with pytest.raises(TypeError):
        BacktestEngine(**arguments)  # type: ignore[arg-type]
