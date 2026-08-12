"""Integration tests for the complete trade execution pipeline."""

from decimal import Decimal

import pytest

from volcanoes.domain import (
    OrderStatus,
    TradeIntent,
    TradeSide,
)
from volcanoes.execution import (
    ExecutionPipeline,
    PaperBroker,
)
from volcanoes.portfolio import Portfolio
from volcanoes.risk import (
    RiskConfig,
    RiskManager,
    RiskViolation,
)


def test_pipeline_executes_first_end_to_end_trade():
    portfolio = Portfolio(
        starting_cash=Decimal("100000"),
    )

    broker = PaperBroker(portfolio)
    pipeline = ExecutionPipeline(broker)

    intent = TradeIntent(
        symbol="AAPL",
        side=TradeSide.BUY,
        entry_price=Decimal("100"),
        stop_price=Decimal("95"),
    )

    result = pipeline.execute(
        portfolio,
        intent,
    )

    assert result.submitted is True
    assert result.sizing_result.quantity == 200
    assert result.sizing_result.dollar_risk == Decimal(
        "1000"
    )
    assert result.sizing_result.position_value == Decimal(
        "20000"
    )

    assert result.trade_request is not None
    assert result.trade_request.symbol == "AAPL"
    assert result.trade_request.quantity == 200
    assert result.trade_request.price == Decimal("100")

    assert result.order is not None
    assert result.order.status == OrderStatus.FILLED
    assert result.order.side == TradeSide.BUY
    assert result.order.quantity == 200
    assert result.order.price == Decimal("100")
    assert result.order.filled_at is not None

    assert portfolio.cash == Decimal("80000")
    assert portfolio.open_positions == 1
    assert portfolio.invested_value == Decimal("20000")
    assert portfolio.equity == Decimal("100000")

    position = portfolio.get_position("AAPL")

    assert position is not None
    assert position.symbol == "AAPL"
    assert position.quantity == 200
    assert position.average_price == Decimal("100")

    assert portfolio.ledger.count() == 1

    ledger_entry = portfolio.ledger.entries[0]

    assert ledger_entry.symbol == "AAPL"
    assert ledger_entry.quantity == 200
    assert ledger_entry.amount == Decimal("-20000")

    assert broker.get_cash_balance() == Decimal("80000")
    assert broker.get_position_quantity("AAPL") == 200
    assert broker.get_orders() == [result.order]


def test_pipeline_returns_without_submitting_zero_quantity():
    portfolio = Portfolio(
        starting_cash=Decimal("100"),
    )

    broker = PaperBroker(portfolio)
    pipeline = ExecutionPipeline(broker)

    intent = TradeIntent(
        symbol="EXPENSIVE",
        side=TradeSide.BUY,
        entry_price=Decimal("1000"),
        stop_price=Decimal("500"),
    )

    result = pipeline.execute(
        portfolio,
        intent,
    )

    assert result.submitted is False
    assert result.sizing_result.quantity == 0
    assert result.trade_request is None
    assert result.order is None

    assert portfolio.cash == Decimal("100")
    assert portfolio.open_positions == 0
    assert portfolio.ledger.count() == 0
    assert broker.get_orders() == []


def test_pipeline_propagates_risk_violation_before_execution():
    portfolio = Portfolio(
        starting_cash=Decimal("100000"),
    )

    config = RiskConfig(
        max_risk_per_trade=Decimal("0.01"),
        max_daily_loss=Decimal("0.03"),
        max_portfolio_exposure=Decimal("0.80"),
        max_position_size=Decimal("0.10"),
        max_open_positions=10,
    )

    risk_manager = RiskManager(config)
    broker = PaperBroker(portfolio)

    pipeline = ExecutionPipeline(
        broker=broker,
        risk_manager=risk_manager,
    )

    intent = TradeIntent(
        symbol="MSFT",
        side=TradeSide.BUY,
        entry_price=Decimal("100"),
        stop_price=Decimal("95"),
    )

    with pytest.raises(RiskViolation) as exc_info:
        pipeline.execute(
            portfolio,
            intent,
        )

    assert exc_info.value.code == "MAX_POSITION_SIZE"

    assert portfolio.cash == Decimal("100000")
    assert portfolio.open_positions == 0
    assert portfolio.ledger.count() == 0
    assert broker.get_orders() == []
