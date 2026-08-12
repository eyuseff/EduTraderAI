"""Presentation-neutral deterministic trade submission service."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from threading import Lock
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
from volcanoes.domain import OrderStatus, TradeIntent, TradeSide
from volcanoes.events import (
    EventPublisher,
    NullEventPublisher,
    PlanDriftDetected,
    PolicyExplanation,
    TradeCancelled,
    TradeFailed,
    TradeFilled,
    TradeSubmitted,
    new_correlation_id,
)
from volcanoes.execution import ExecutionPipeline, TradePlan, TradePlanner
from volcanoes.risk import RiskPortfolioView


@dataclass(frozen=True, slots=True)
class ExpectedTradePlan:
    """Material plan values displayed by a preview operation."""

    approved: bool
    quantity: int
    dollar_risk: Decimal
    position_value: Decimal
    reasons: tuple[str, ...]
    risk_code: str | None = None
    correlation_id: str = field(default_factory=new_correlation_id)

    def __post_init__(self) -> None:
        if not isinstance(self.correlation_id, str) or not self.correlation_id.strip():
            raise ValueError("correlation_id cannot be empty.")

    @classmethod
    def from_plan(
        cls,
        plan: TradePlan,
        *,
        correlation_id: str | None = None,
    ) -> ExpectedTradePlan:
        """Capture the immutable values relevant to safe submission."""

        return cls(
            approved=plan.approved,
            quantity=plan.sizing_result.quantity,
            dollar_risk=plan.sizing_result.dollar_risk,
            position_value=plan.sizing_result.position_value,
            reasons=plan.reasons,
            risk_code=plan.risk_code,
            correlation_id=correlation_id or new_correlation_id(),
        )


@dataclass(frozen=True, slots=True)
class SubmitTradeRequest:
    """Immutable command containing canonical prices and preview assumptions."""

    symbol: str
    side: TradeSide
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    expected_plan: ExpectedTradePlan

    @property
    def correlation_id(self) -> str:
        """Return the preview lifecycle identifier carried into submission."""

        return self.expected_plan.correlation_id


@dataclass(frozen=True, slots=True)
class SubmitTradeResult:
    """Explainable result of planning and optional broker submission."""

    submitted: bool
    code: str
    explanation: str
    correlation_id: str
    plan: TradePlan | None = None
    order_id: str | None = None
    symbol: str | None = None
    side: TradeSide | None = None
    quantity: int = 0
    price: Decimal | None = None
    stop_price: Decimal | None = None
    target_price: Decimal | None = None
    broker_status: str | None = None
    message: str = ""
    rejections: tuple[PolicyExplanation, ...] = ()


class SubmitTradeService:
    """Replan against fresh state and execute only an unchanged approved plan."""

    INVALID_REQUEST = "INVALID_REQUEST"
    PLAN_REJECTED = "PLAN_REJECTED"
    PLAN_DRIFT = "PLAN_DRIFT"
    DUPLICATE_SUBMISSION = "DUPLICATE_SUBMISSION"
    EXECUTION_REJECTED = "EXECUTION_REJECTED"
    BROKER_REJECTED = "BROKER_REJECTED"
    BROKER_ERROR = "BROKER_ERROR"
    SUBMITTED = "SUBMITTED"

    def __init__(
        self,
        planner: TradePlanner,
        execution_pipeline: ExecutionPipeline,
        event_publisher: EventPublisher | None = None,
        operational_metrics: OperationalMetrics | None = None,
    ) -> None:
        if not isinstance(planner, TradePlanner):
            raise TypeError("planner must be a TradePlanner instance.")

        if not isinstance(execution_pipeline, ExecutionPipeline):
            raise TypeError("execution_pipeline must be an ExecutionPipeline instance.")

        if execution_pipeline.planner is not planner:
            raise ValueError(
                "Preview and submission must share the exact TradePlanner instance."
            )

        if event_publisher is not None and not isinstance(
            event_publisher,
            EventPublisher,
        ):
            raise TypeError("event_publisher must be an EventPublisher instance.")

        self._planner = planner
        self._execution_pipeline = execution_pipeline
        self._event_publisher = event_publisher or NullEventPublisher()
        self._operational_metrics = fail_open(operational_metrics)
        self._submission_lock = Lock()
        self._submitted_requests: set[SubmitTradeRequest] = set()
        self._in_flight_requests: set[SubmitTradeRequest] = set()

    def submit(
        self,
        portfolio: RiskPortfolioView,
        request: SubmitTradeRequest,
        *,
        open_order_symbols: frozenset[str] = frozenset(),
    ) -> SubmitTradeResult:
        """Recompute from fresh immutable state and submit exactly once."""

        started = monotonic_ns()
        try:
            result = self._submit(
                portfolio,
                request,
                open_order_symbols=open_order_symbols,
            )
            if result.submitted:
                self._operational_metrics.increment(CounterMetric.SUBMISSIONS)
            if result.code in {self.BROKER_REJECTED, self.BROKER_ERROR}:
                self._operational_metrics.increment(CounterMetric.BROKER_FAILURES)
            if result.code == self.PLAN_DRIFT:
                self._operational_metrics.increment(CounterMetric.PLAN_DRIFT)
            return result
        finally:
            self._operational_metrics.observe_latency(
                LatencyMetric.SUBMISSION,
                monotonic_ns() - started,
            )

    def _submit(
        self,
        portfolio: RiskPortfolioView,
        request: SubmitTradeRequest,
        *,
        open_order_symbols: frozenset[str],
    ) -> SubmitTradeResult:
        """Execute the unchanged deterministic submission operation."""

        try:
            intent = self._create_intent(request)
        except (TypeError, ValueError) as error:
            correlation_id = self._correlation_id(request)
            rejection = PolicyExplanation(
                policy="RequestValidation",
                explanation=str(error),
                configuration=configuration_from_pairs(
                    ("request_type", type(request).__name__),
                ),
            )
            return self._rejected(
                request=request,
                correlation_id=correlation_id,
                code=self.INVALID_REQUEST,
                explanation=str(error),
                rejections=(rejection,),
            )

        try:
            plan = self._planner.plan(
                portfolio,
                intent,
                target_price=request.target_price,
                open_order_symbols=open_order_symbols,
            )
        except (TypeError, ValueError) as error:
            rejection = PolicyExplanation(
                policy="PortfolioValidation",
                explanation=str(error),
                configuration=configuration_from_pairs(
                    ("portfolio_type", type(portfolio).__name__),
                ),
            )
            return self._rejected(
                request=request,
                correlation_id=request.correlation_id,
                code=self.INVALID_REQUEST,
                explanation=str(error),
                rejections=(rejection,),
            )

        actual_plan = ExpectedTradePlan.from_plan(
            plan,
            correlation_id=request.correlation_id,
        )
        differences = self._plan_differences(request.expected_plan, actual_plan)
        if differences:
            expected_configuration = self._plan_configuration(request.expected_plan)
            actual_configuration = self._plan_configuration(actual_plan)
            self._event_publisher.publish(
                PlanDriftDetected(
                    correlation_id=request.correlation_id,
                    symbol=intent.symbol,
                    differences=differences,
                    expected=expected_configuration,
                    actual=actual_configuration,
                )
            )
            rejection = PolicyExplanation(
                policy="PlanConsistency",
                explanation=(
                    "Trade was not submitted because the fresh account snapshot "
                    "changed the previewed plan: " + ", ".join(differences) + "."
                ),
                configuration=configuration_from_pairs(
                    ("differences", ",".join(differences)),
                ),
            )
            return self._rejected(
                request=request,
                correlation_id=request.correlation_id,
                code=self.PLAN_DRIFT,
                explanation=rejection.explanation,
                plan=plan,
                rejections=(rejection,),
            )

        if not plan.approved:
            rejections = plan_rejections(plan, self._planner)
            return self._rejected(
                request=request,
                correlation_id=request.correlation_id,
                code=plan.risk_code or self.PLAN_REJECTED,
                explanation=plan.reason,
                plan=plan,
                rejections=rejections,
            )

        duplicate = self._reserve_submission(request)
        if duplicate is not None:
            return duplicate

        submitted = False
        try:
            execution_result = self._execution_pipeline.submit_plan(
                intent,
                plan,
                target_price=request.target_price,
            )

            if not execution_result.submitted or execution_result.order is None:
                return self._rejected(
                    request=request,
                    correlation_id=request.correlation_id,
                    code=self.EXECUTION_REJECTED,
                    explanation=execution_result.reason,
                    plan=plan,
                    rejections=(
                        PolicyExplanation(
                            policy="ExecutionPipeline",
                            explanation=execution_result.reason,
                        ),
                    ),
                )

            order = execution_result.order
            if order.status is OrderStatus.REJECTED:
                explanation = (
                    order.rejection_reason
                    or order.broker_message
                    or execution_result.reason
                )
                rejection = PolicyExplanation(
                    policy="BrokerAcceptance",
                    explanation=explanation,
                    configuration=configuration_from_pairs(
                        ("broker_status", order.broker_status),
                    ),
                )
                if (order.broker_status or "").strip().lower() in {
                    "cancelled",
                    "canceled",
                }:
                    self._event_publisher.publish(
                        TradeCancelled(
                            correlation_id=request.correlation_id,
                            order_id=order.broker_order_id,
                            symbol=order.symbol,
                            explanation=explanation,
                        )
                    )
                return self._rejected(
                    request=request,
                    correlation_id=request.correlation_id,
                    code=self.BROKER_REJECTED,
                    explanation=explanation,
                    plan=plan,
                    broker_status=order.broker_status,
                    message=order.broker_message,
                    rejections=(rejection,),
                )

            self._event_publisher.publish(
                TradeSubmitted(
                    correlation_id=request.correlation_id,
                    order_id=order.broker_order_id,
                    symbol=order.symbol,
                    side=order.side.value,
                    quantity=order.quantity,
                    price=order.price,
                    stop_price=order.stop_price,
                    target_price=order.target_price,
                    broker_status=order.broker_status,
                )
            )
            if order.status is OrderStatus.FILLED:
                self._event_publisher.publish(
                    TradeFilled(
                        correlation_id=request.correlation_id,
                        order_id=order.broker_order_id,
                        symbol=order.symbol,
                        side=order.side.value,
                        quantity=order.quantity,
                        price=order.price,
                    )
                )

            submitted = True
            return SubmitTradeResult(
                submitted=True,
                code=self.SUBMITTED,
                explanation=execution_result.reason,
                correlation_id=request.correlation_id,
                plan=plan,
                order_id=order.broker_order_id,
                symbol=order.symbol,
                side=order.side,
                quantity=order.quantity,
                price=order.price,
                stop_price=order.stop_price,
                target_price=order.target_price,
                broker_status=order.broker_status,
                message=order.broker_message,
            )
        except Exception as error:
            rejection = PolicyExplanation(
                policy="BrokerExecution",
                explanation=str(error),
                configuration=configuration_from_pairs(
                    ("error_type", type(error).__name__),
                ),
            )
            self._event_publisher.publish(
                TradeFailed(
                    correlation_id=request.correlation_id,
                    operation="submission",
                    symbol=intent.symbol,
                    policy=rejection.policy,
                    explanation=rejection.explanation,
                    configuration=rejection.configuration,
                )
            )
            return self._rejected_result(
                correlation_id=request.correlation_id,
                code=self.BROKER_ERROR,
                explanation=str(error),
                plan=plan,
                rejections=(rejection,),
            )
        finally:
            self._release_submission(request, submitted=submitted)

    def _reserve_submission(
        self,
        request: SubmitTradeRequest,
    ) -> SubmitTradeResult | None:
        with self._submission_lock:
            if (
                request in self._submitted_requests
                or request in self._in_flight_requests
            ):
                return self._rejected(
                    request=request,
                    correlation_id=request.correlation_id,
                    code=self.DUPLICATE_SUBMISSION,
                    explanation=(
                        "This immutable trade request has already been submitted."
                    ),
                    rejections=(
                        PolicyExplanation(
                            policy="DuplicateSubmission",
                            explanation=(
                                "This immutable trade request has already been "
                                "submitted."
                            ),
                            configuration=(("scope", "service_instance"),),
                        ),
                    ),
                )

            self._in_flight_requests.add(request)

        return None

    def _release_submission(
        self,
        request: SubmitTradeRequest,
        *,
        submitted: bool,
    ) -> None:
        with self._submission_lock:
            self._in_flight_requests.discard(request)
            if submitted:
                self._submitted_requests.add(request)

    @staticmethod
    def _create_intent(request: SubmitTradeRequest) -> TradeIntent:
        if not isinstance(request, SubmitTradeRequest):
            raise TypeError("request must be a SubmitTradeRequest instance.")

        if not isinstance(request.side, TradeSide):
            raise TypeError("side must be a TradeSide value.")

        if not isinstance(request.expected_plan, ExpectedTradePlan):
            raise TypeError("expected_plan must be an ExpectedTradePlan instance.")

        for name in ("entry_price", "stop_price", "target_price"):
            if not isinstance(getattr(request, name), Decimal):
                raise TypeError(f"{name} must be a Decimal.")

        if request.target_price <= Decimal("0"):
            raise ValueError("Target price must be greater than zero.")

        if request.side is TradeSide.BUY and (
            request.target_price <= request.entry_price
        ):
            raise ValueError("Buy target price must be above entry price.")

        if request.side is TradeSide.SELL and (
            request.target_price >= request.entry_price
        ):
            raise ValueError("Sell target price must be below entry price.")

        return TradeIntent(
            symbol=request.symbol,
            side=request.side,
            entry_price=request.entry_price,
            stop_price=request.stop_price,
        )

    @staticmethod
    def _plan_differences(
        expected: ExpectedTradePlan,
        actual: ExpectedTradePlan,
    ) -> tuple[str, ...]:
        fields = (
            "approved",
            "quantity",
            "dollar_risk",
            "position_value",
            "reasons",
            "risk_code",
        )
        return tuple(
            field
            for field in fields
            if getattr(expected, field) != getattr(actual, field)
        )

    def _rejected(
        self,
        *,
        request: object,
        correlation_id: str,
        code: str,
        explanation: str,
        plan: TradePlan | None = None,
        broker_status: str | None = None,
        message: str = "",
        rejections: tuple[PolicyExplanation, ...],
    ) -> SubmitTradeResult:
        publish_rejection(
            self._event_publisher,
            operation="submission",
            symbol=str(getattr(request, "symbol", "")),
            correlation_id=correlation_id,
            explanations=rejections,
        )
        return self._rejected_result(
            correlation_id=correlation_id,
            code=code,
            explanation=explanation,
            plan=plan,
            broker_status=broker_status,
            message=message,
            rejections=rejections,
        )

    @staticmethod
    def _rejected_result(
        *,
        correlation_id: str,
        code: str,
        explanation: str,
        plan: TradePlan | None = None,
        broker_status: str | None = None,
        message: str = "",
        rejections: tuple[PolicyExplanation, ...],
    ) -> SubmitTradeResult:
        return SubmitTradeResult(
            submitted=False,
            code=code,
            explanation=explanation,
            correlation_id=correlation_id,
            plan=plan,
            broker_status=broker_status,
            message=message,
            rejections=rejections,
        )

    @staticmethod
    def _correlation_id(request: object) -> str:
        correlation_id = getattr(request, "correlation_id", "")
        return (
            correlation_id
            if isinstance(correlation_id, str) and correlation_id.strip()
            else new_correlation_id()
        )

    @staticmethod
    def _plan_configuration(plan: ExpectedTradePlan) -> tuple[tuple[str, str], ...]:
        return configuration_from_pairs(
            ("approved", plan.approved),
            ("quantity", plan.quantity),
            ("dollar_risk", plan.dollar_risk),
            ("position_value", plan.position_value),
            ("reasons", "|".join(plan.reasons)),
            ("risk_code", plan.risk_code),
        )

    @property
    def planner(self) -> TradePlanner:
        """Return the exact planner shared with the execution pipeline."""

        return self._planner
