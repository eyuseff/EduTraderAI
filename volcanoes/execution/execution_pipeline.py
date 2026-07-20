"""End-to-end trade execution pipeline for Volcanes."""

from __future__ import annotations

from dataclasses import dataclass

from volcanoes.domain import (
    Order,
    TradeIntent,
    TradeRequest,
)
from volcanoes.execution.broker import Broker
from volcanoes.execution.order_builder import OrderBuilder
from volcanoes.portfolio import Portfolio
from volcanoes.risk import RiskManager
from volcanoes.sizing import (
    PositionSizer,
    PositionSizingRequest,
    PositionSizingResult,
)


@dataclass(frozen=True)
class ExecutionPipelineResult:
    """Explainable result produced by the execution pipeline."""

    submitted: bool
    reason: str
    sizing_result: PositionSizingResult
    trade_request: TradeRequest | None = None
    order: Order | None = None


class ExecutionPipeline:
    """
    Coordinate sizing, risk validation, and broker execution.

    The pipeline contains no trading calculations or risk rules of its
    own. It delegates those responsibilities to specialized components.
    """

    def __init__(
        self,
        broker: Broker,
        position_sizer: PositionSizer | None = None,
        order_builder: OrderBuilder | None = None,
        risk_manager: RiskManager | None = None,
    ) -> None:
        if not isinstance(broker, Broker):
            raise TypeError(
                "ExecutionPipeline requires a Broker instance."
            )

        self._broker = broker
        self._position_sizer = (
            position_sizer or PositionSizer()
        )
        self._order_builder = (
            order_builder or OrderBuilder()
        )
        self._risk_manager = (
            risk_manager or RiskManager()
        )

    def execute(
        self,
        portfolio: Portfolio,
        trade_intent: TradeIntent,
    ) -> ExecutionPipelineResult:
        """
        Size, validate, build, and submit a trade.

        RiskViolation exceptions are intentionally allowed to propagate
        so callers receive the exact risk code and explanation.
        """

        if not isinstance(portfolio, Portfolio):
            raise TypeError(
                "portfolio must be a Portfolio instance."
            )

        if not isinstance(trade_intent, TradeIntent):
            raise TypeError(
                "trade_intent must be a TradeIntent instance."
            )

        sizing_request = PositionSizingRequest(
            portfolio_equity=portfolio.equity,
            trade_intent=trade_intent,
            maximum_risk=(
                self._risk_manager.config.max_risk_per_trade
            ),
        )

        sizing_result = (
            self._position_sizer.size_position(
                sizing_request
            )
        )

        if sizing_result.quantity == 0:
            return ExecutionPipelineResult(
                submitted=False,
                reason=(
                    "Risk allowance is insufficient "
                    "to trade one share."
                ),
                sizing_result=sizing_result,
            )

        trade_request = self._order_builder.build(
            trade_intent,
            sizing_result,
        )

        self._risk_manager.validate_trade(
            portfolio,
            trade_request,
        )

        order = Order(
            symbol=trade_request.symbol,
            side=trade_intent.side,
            quantity=trade_request.quantity,
            price=trade_request.price,
        )

        completed_order = self._broker.submit_order(
            order
        )

        return ExecutionPipelineResult(
            submitted=True,
            reason=(
                "Order completed with status "
                f"{completed_order.status.value}."
            ),
            sizing_result=sizing_result,
            trade_request=trade_request,
            order=completed_order,
        )

    @property
    def broker(self) -> Broker:
        """Return the broker used by the pipeline."""

        return self._broker

    @property
    def risk_manager(self) -> RiskManager:
        """Return the pipeline risk manager."""

        return self._risk_manager
