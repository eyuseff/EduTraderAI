"""Pure sizing and risk planning for proposed trades."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from volcanoes.domain import TradeIntent, TradeRequest
from volcanoes.execution.order_builder import OrderBuilder
from volcanoes.risk import RiskManager, RiskPortfolioView
from volcanoes.risk.trade_policies import (
    PolicyDecision,
    TradePolicyContext,
    TradePolicySet,
)
from volcanoes.sizing import (
    PositionSizer,
    PositionSizingRequest,
    PositionSizingResult,
)


@dataclass(frozen=True, slots=True)
class TradePlan:
    """Immutable result of deterministic sizing and risk planning."""

    approved: bool
    reason: str
    sizing_result: PositionSizingResult
    trade_request: TradeRequest | None = None
    risk_code: str | None = None
    reasons: tuple[str, ...] = ()
    policy_decisions: tuple[PolicyDecision, ...] = ()


class TradePlanner:
    """Plan a trade without broker calls or portfolio mutation."""

    ZERO_QUANTITY_REASON = "Risk allowance is insufficient to trade one share."

    def __init__(
        self,
        position_sizer: PositionSizer | None = None,
        order_builder: OrderBuilder | None = None,
        risk_manager: RiskManager | None = None,
        policies: TradePolicySet | None = None,
    ) -> None:
        self._position_sizer = position_sizer or PositionSizer()
        self._order_builder = order_builder or OrderBuilder()
        self._risk_manager = risk_manager or RiskManager()
        self._policies = policies or TradePolicySet.execution_defaults(
            self._risk_manager.config
        )

    def plan(
        self,
        portfolio: RiskPortfolioView,
        trade_intent: TradeIntent,
        *,
        target_price: Decimal | None = None,
        open_order_symbols: frozenset[str] = frozenset(),
    ) -> TradePlan:
        """Return a deterministic plan without producing side effects."""

        if not isinstance(portfolio, RiskPortfolioView):
            raise TypeError("portfolio must satisfy RiskPortfolioView.")

        if not isinstance(trade_intent, TradeIntent):
            raise TypeError("trade_intent must be a TradeIntent instance.")

        sizing_request = PositionSizingRequest(
            portfolio_equity=portfolio.equity,
            trade_intent=trade_intent,
            maximum_risk=(self._risk_manager.config.max_risk_per_trade),
        )
        sizing_result = self._position_sizer.size_position(sizing_request)

        if (
            sizing_result.quantity == 0
            and not self._policies.evaluate_when_zero_quantity
        ):
            return TradePlan(
                approved=False,
                reason=self.ZERO_QUANTITY_REASON,
                sizing_result=sizing_result,
                reasons=(self.ZERO_QUANTITY_REASON,),
            )

        context = TradePolicyContext(
            portfolio=portfolio,
            trade_intent=trade_intent,
            quantity=sizing_result.quantity,
            target_price=target_price,
            open_order_symbols=open_order_symbols,
        )
        decisions: list[PolicyDecision] = []
        rejections: list[PolicyDecision] = []
        quantity_limits: list[int] = []

        for policy in self._policies.policies:
            decision = policy.evaluate(context)
            decisions.append(decision)
            if decision.maximum_quantity is not None:
                quantity_limits.append(decision.maximum_quantity)
            if not decision.approved:
                rejections.append(decision)
                if not self._policies.collect_all_rejections:
                    break

        planned_quantity = min((sizing_result.quantity, *quantity_limits))
        planned_sizing = self._resize(
            trade_intent,
            planned_quantity,
        )

        zero_quantity_reason: str | None = None
        if planned_quantity == 0:
            zero_quantity_reason = self._policies.zero_quantity_reason

        trade_request = (
            self._order_builder.build(
                trade_intent,
                planned_sizing,
            )
            if planned_quantity > 0
            else None
        )

        if rejections or zero_quantity_reason is not None:
            reasons = tuple(decision.explanation for decision in rejections)
            if zero_quantity_reason is not None:
                reasons = (*reasons, zero_quantity_reason)

            return TradePlan(
                approved=False,
                reason=reasons[0],
                risk_code=(rejections[0].code if rejections else None),
                reasons=reasons,
                sizing_result=planned_sizing,
                trade_request=trade_request,
                policy_decisions=tuple(decisions),
            )

        return TradePlan(
            approved=True,
            reason="All deterministic risk rules passed.",
            reasons=(),
            sizing_result=planned_sizing,
            trade_request=trade_request,
            policy_decisions=tuple(decisions),
        )

    @staticmethod
    def _resize(
        trade_intent: TradeIntent,
        quantity: int,
    ) -> PositionSizingResult:
        if quantity == 0:
            return PositionSizingResult(
                quantity=0,
                dollar_risk=Decimal("0"),
                position_value=Decimal("0"),
            )

        return PositionSizingResult(
            quantity=quantity,
            dollar_risk=(trade_intent.risk_per_share * quantity),
            position_value=(trade_intent.entry_price * quantity),
        )

    @property
    def risk_manager(self) -> RiskManager:
        """Return the risk manager used by this planner."""

        return self._risk_manager

    @property
    def policies(self) -> TradePolicySet:
        """Return the immutable policy set orchestrated by this planner."""

        return self._policies
