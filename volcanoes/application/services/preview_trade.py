"""Broker-free Preview Trade application service."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from time import monotonic_ns

from volcanoes.application.operations import (
    CounterMetric,
    LatencyMetric,
    OperationalMetrics,
    fail_open,
)

from volcanoes.application.services._event_support import (
    configuration_from_pairs,
    plan_rejections,
    publish_rejection,
)
from volcanoes.domain import TradeIntent, TradeSide
from volcanoes.events import (
    EventPublisher,
    NullEventPublisher,
    PolicyExplanation,
    TradePreviewed,
    new_correlation_id,
)
from volcanoes.execution.trade_planner import TradePlanner
from volcanoes.risk import RiskPortfolioView


@dataclass(frozen=True, slots=True)
class PreviewTradeRequest:
    """Immutable input contract for the Preview Trade use case."""

    symbol: str
    side: TradeSide
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    correlation_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        if not isinstance(self.correlation_id, str) or not self.correlation_id.strip():
            raise ValueError("correlation_id cannot be empty.")


@dataclass(frozen=True, slots=True)
class PreviewTradeResult:
    """Immutable, presentation-neutral trade preview."""

    approved: bool
    quantity: int
    dollar_risk: Decimal
    position_value: Decimal
    reward_risk: Decimal
    reasons: tuple[str, ...]
    risk_code: str | None = None
    correlation_id: str = field(default_factory=new_correlation_id)
    rejections: tuple[PolicyExplanation, ...] = ()


class PreviewTradeService:
    """Preview deterministic sizing and risk without side effects."""

    INVALID_REQUEST = "INVALID_REQUEST"

    def __init__(
        self,
        planner: TradePlanner | None = None,
        event_publisher: EventPublisher | None = None,
        operational_metrics: OperationalMetrics | None = None,
    ) -> None:
        self._planner = planner or TradePlanner()
        if event_publisher is not None and not isinstance(
            event_publisher,
            EventPublisher,
        ):
            raise TypeError("event_publisher must be an EventPublisher instance.")
        self._event_publisher = event_publisher or NullEventPublisher()
        self._operational_metrics = fail_open(operational_metrics)

    def preview(
        self,
        portfolio: RiskPortfolioView,
        request: PreviewTradeRequest,
        *,
        open_order_symbols: frozenset[str] = frozenset(),
    ) -> PreviewTradeResult:
        """Return a trade preview without broker or persistence access."""

        started = monotonic_ns()
        self._operational_metrics.increment(CounterMetric.PREVIEWS)
        try:
            result = self._preview(
                portfolio,
                request,
                open_order_symbols=open_order_symbols,
            )
            self._operational_metrics.increment(
                CounterMetric.APPROVED_PLANS
                if result.approved
                else CounterMetric.REJECTED_PLANS
            )
            return result
        finally:
            self._operational_metrics.observe_latency(
                LatencyMetric.PREVIEW,
                monotonic_ns() - started,
            )

    def _preview(
        self,
        portfolio: RiskPortfolioView,
        request: PreviewTradeRequest,
        *,
        open_order_symbols: frozenset[str],
    ) -> PreviewTradeResult:
        """Execute the unchanged deterministic preview operation."""

        correlation_id = self._correlation_id(request)
        try:
            intent = self._create_intent(request)
            reward_risk = self._calculate_reward_risk(request)
        except (TypeError, ValueError) as error:
            rejection = PolicyExplanation(
                policy="RequestValidation",
                explanation=str(error),
                configuration=configuration_from_pairs(
                    ("request_type", type(request).__name__),
                ),
            )
            publish_rejection(
                self._event_publisher,
                operation="preview",
                symbol=getattr(request, "symbol", ""),
                correlation_id=correlation_id,
                explanations=(rejection,),
            )
            return self._rejected_invalid(
                str(error),
                correlation_id=correlation_id,
                rejection=rejection,
            )

        try:
            plan = self._planner.plan(
                portfolio,
                intent,
                target_price=request.target_price,
                open_order_symbols=open_order_symbols,
            )
        except (TypeError, ValueError) as error:
            explanation = str(error)
            if explanation == "Portfolio equity must be greater than zero.":
                explanation = "Account equity is unavailable or zero."
            rejection = PolicyExplanation(
                policy="PortfolioValidation",
                explanation=explanation,
                configuration=configuration_from_pairs(
                    ("equity", getattr(portfolio, "equity", "unavailable")),
                ),
            )
            publish_rejection(
                self._event_publisher,
                operation="preview",
                symbol=intent.symbol,
                correlation_id=correlation_id,
                explanations=(rejection,),
            )
            return self._rejected_invalid(
                explanation,
                correlation_id=correlation_id,
                rejection=rejection,
                risk_code="INVALID_PORTFOLIO",
            )

        rejections = plan_rejections(plan, self._planner)
        self._event_publisher.publish(
            TradePreviewed(
                correlation_id=correlation_id,
                symbol=intent.symbol,
                side=intent.side.value,
                entry_price=request.entry_price,
                stop_price=request.stop_price,
                target_price=request.target_price,
                approved=plan.approved,
                quantity=plan.sizing_result.quantity,
                dollar_risk=plan.sizing_result.dollar_risk,
                position_value=plan.sizing_result.position_value,
            )
        )
        if rejections:
            publish_rejection(
                self._event_publisher,
                operation="preview",
                symbol=intent.symbol,
                correlation_id=correlation_id,
                explanations=rejections,
            )

        return PreviewTradeResult(
            approved=plan.approved,
            quantity=plan.sizing_result.quantity,
            dollar_risk=plan.sizing_result.dollar_risk,
            position_value=plan.sizing_result.position_value,
            reward_risk=reward_risk,
            reasons=plan.reasons,
            risk_code=plan.risk_code,
            correlation_id=correlation_id,
            rejections=rejections,
        )

    @staticmethod
    def _create_intent(
        request: PreviewTradeRequest,
    ) -> TradeIntent:
        if not isinstance(request, PreviewTradeRequest):
            raise TypeError("request must be a PreviewTradeRequest instance.")

        if not isinstance(request.side, TradeSide):
            raise ValueError(f"Unsupported trade side: {request.side!r}.")

        for name in ("entry_price", "stop_price", "target_price"):
            if not isinstance(getattr(request, name), Decimal):
                raise TypeError(f"{name} must be a Decimal.")

        return TradeIntent(
            symbol=request.symbol,
            side=request.side,
            entry_price=request.entry_price,
            stop_price=request.stop_price,
        )

    @staticmethod
    def _calculate_reward_risk(
        request: PreviewTradeRequest,
    ) -> Decimal:
        if request.target_price <= Decimal("0"):
            raise ValueError("Target price must be greater than zero.")

        if request.side is TradeSide.BUY:
            reward = request.target_price - request.entry_price
            if reward <= Decimal("0"):
                raise ValueError("Buy target price must be above entry price.")
        else:
            reward = request.entry_price - request.target_price
            if reward <= Decimal("0"):
                raise ValueError("Sell target price must be below entry price.")

        return reward / abs(request.entry_price - request.stop_price)

    @classmethod
    def _rejected_invalid(
        cls,
        reason: str,
        *,
        correlation_id: str,
        rejection: PolicyExplanation,
        risk_code: str | None = None,
    ) -> PreviewTradeResult:
        return PreviewTradeResult(
            approved=False,
            quantity=0,
            dollar_risk=Decimal("0"),
            position_value=Decimal("0"),
            reward_risk=Decimal("0"),
            reasons=(reason,),
            risk_code=risk_code or cls.INVALID_REQUEST,
            correlation_id=correlation_id,
            rejections=(rejection,),
        )

    @staticmethod
    def _correlation_id(request: object) -> str:
        correlation_id = getattr(request, "correlation_id", "")
        return (
            correlation_id
            if isinstance(correlation_id, str) and correlation_id.strip()
            else new_correlation_id()
        )

    @property
    def planner(self) -> TradePlanner:
        """Return the deterministic planner used by this service."""

        return self._planner
