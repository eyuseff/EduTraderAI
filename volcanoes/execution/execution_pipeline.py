"""End-to-end trade execution pipeline for Volcanes."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from volcanoes.domain import (
    Order,
    TradeIntent,
    TradeRequest,
)
from volcanoes.execution.broker import Broker
from volcanoes.execution.order_builder import OrderBuilder
from volcanoes.execution.trade_planner import TradePlan, TradePlanner
from volcanoes.portfolio import Portfolio
from volcanoes.risk import RiskManager, RiskViolation
from volcanoes.sizing import (
    PositionSizer,
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
        planner: TradePlanner | None = None,
    ) -> None:
        if not isinstance(broker, Broker):
            raise TypeError("ExecutionPipeline requires a Broker instance.")

        self._broker = broker
        if planner is not None and any(
            component is not None
            for component in (position_sizer, order_builder, risk_manager)
        ):
            raise ValueError(
                "planner cannot be combined with sizing, order, or risk components."
            )

        self._planner = planner or TradePlanner(
            position_sizer=position_sizer,
            order_builder=order_builder,
            risk_manager=risk_manager,
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
            raise TypeError("portfolio must be a Portfolio instance.")

        if not isinstance(trade_intent, TradeIntent):
            raise TypeError("trade_intent must be a TradeIntent instance.")

        plan = self._planner.plan(
            portfolio,
            trade_intent,
        )

        return self.submit_plan(trade_intent, plan)

    def submit_plan(
        self,
        trade_intent: TradeIntent,
        plan: TradePlan,
        *,
        target_price: Decimal | None = None,
    ) -> ExecutionPipelineResult:
        """Submit an immutable plan without repeating sizing or risk rules."""

        if not isinstance(trade_intent, TradeIntent):
            raise TypeError("trade_intent must be a TradeIntent instance.")

        if not isinstance(plan, TradePlan):
            raise TypeError("plan must be a TradePlan instance.")

        if not plan.approved:
            if plan.risk_code is not None:
                raise RiskViolation(
                    code=plan.risk_code,
                    message=plan.reason,
                )

            return ExecutionPipelineResult(
                submitted=False,
                reason=plan.reason,
                sizing_result=plan.sizing_result,
            )

        trade_request = plan.trade_request

        if trade_request is None:
            raise RuntimeError("Approved trade plan has no trade request.")

        if (
            trade_request.symbol != trade_intent.symbol
            or trade_request.price != trade_intent.entry_price
        ):
            raise ValueError("Trade plan does not match the supplied trade intent.")

        order = Order(
            symbol=trade_request.symbol,
            side=trade_intent.side,
            quantity=trade_request.quantity,
            price=trade_request.price,
            stop_price=(trade_intent.stop_price if target_price is not None else None),
            target_price=target_price,
        )

        completed_order = self._broker.submit_order(order)

        return ExecutionPipelineResult(
            submitted=True,
            reason=("Order completed with status " f"{completed_order.status.value}."),
            sizing_result=plan.sizing_result,
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

        return self._planner.risk_manager

    @property
    def planner(self) -> TradePlanner:
        """Return the pure planner shared with preview use cases."""

        return self._planner
