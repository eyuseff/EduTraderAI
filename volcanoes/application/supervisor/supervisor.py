"""Supervisory coordination for deterministic preview and submission."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from threading import Lock
from time import monotonic_ns

from volcanoes.application.operations import (
    CounterMetric,
    LatencyMetric,
    OperationalMetrics,
    fail_open,
)
from volcanoes.application.services.preview_trade import (
    PreviewTradeRequest,
    PreviewTradeService,
)
from volcanoes.application.services.submit_trade import (
    ExpectedTradePlan,
    SubmitTradeRequest,
    SubmitTradeService,
)
from volcanoes.application.supervisor.contracts import (
    ExecutionDecision,
    ExecutionMode,
    ExecutionRequest,
    ExecutionResult,
)
from volcanoes.application.supervisor.events import (
    ExecutionAborted,
    ExecutionCompleted,
    ExecutionSkipped,
    ExecutionStarted,
)
from volcanoes.application.supervisor.policies import (
    ConcurrentSymbolPolicy,
    CooldownPolicy,
    DuplicateExecutionPolicy,
    MarketStatePolicy,
    SupervisorPolicyDecision,
)
from volcanoes.events import EventPublisher, NullEventPublisher, PolicyExplanation
from volcanoes.risk import RiskPortfolioView


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ExecutionSupervisor:
    """Serialize and supervise deterministic execution application services."""

    def __init__(
        self,
        preview_service: PreviewTradeService,
        submit_service: SubmitTradeService,
        *,
        cooldown_policy: CooldownPolicy | None = None,
        duplicate_policy: DuplicateExecutionPolicy | None = None,
        concurrent_symbol_policy: ConcurrentSymbolPolicy | None = None,
        market_state_policy: MarketStatePolicy | None = None,
        event_publisher: EventPublisher | None = None,
        operational_metrics: OperationalMetrics | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not isinstance(preview_service, PreviewTradeService):
            raise TypeError("preview_service must be a PreviewTradeService instance.")
        if not isinstance(submit_service, SubmitTradeService):
            raise TypeError("submit_service must be a SubmitTradeService instance.")
        if preview_service.planner is not submit_service.planner:
            raise ValueError(
                "Preview and submission services must share one TradePlanner instance."
            )
        if event_publisher is not None and not isinstance(
            event_publisher,
            EventPublisher,
        ):
            raise TypeError("event_publisher must be an EventPublisher instance.")

        self._preview_service = preview_service
        self._submit_service = submit_service
        self._cooldown_policy = cooldown_policy or CooldownPolicy()
        self._duplicate_policy = duplicate_policy or DuplicateExecutionPolicy()
        self._concurrent_symbol_policy = (
            concurrent_symbol_policy or ConcurrentSymbolPolicy()
        )
        self._market_state_policy = market_state_policy or MarketStatePolicy()
        self._event_publisher = event_publisher or NullEventPublisher()
        self._operational_metrics = fail_open(operational_metrics)
        self._clock = clock

        self._state_lock = Lock()
        self._active_symbols: set[str] = set()
        self._in_flight_keys: dict[str, tuple[str, ...]] = {}
        self._in_flight_fingerprints: set[tuple[str, ...]] = set()
        self._successful_fingerprints: set[tuple[str, ...]] = set()
        self._completed_by_key: dict[str, ExecutionResult] = {}
        self._last_success_by_symbol: dict[str, datetime] = {}

    def execute(
        self,
        portfolio: RiskPortfolioView,
        request: ExecutionRequest,
        *,
        open_order_symbols: frozenset[str] = frozenset(),
    ) -> ExecutionResult:
        """Preview and conditionally submit one supervised execution request."""

        started = monotonic_ns()
        try:
            result = self._execute(
                portfolio,
                request,
                open_order_symbols=open_order_symbols,
            )
            self._record_decision(result)
            return result
        finally:
            self._operational_metrics.observe_latency(
                LatencyMetric.SUPERVISOR,
                monotonic_ns() - started,
            )

    def _execute(
        self,
        portfolio: RiskPortfolioView,
        request: ExecutionRequest,
        *,
        open_order_symbols: frozenset[str],
    ) -> ExecutionResult:
        """Execute the unchanged supervisory workflow."""

        if not isinstance(request, ExecutionRequest):
            raise TypeError("request must be an ExecutionRequest instance.")
        if not isinstance(portfolio, RiskPortfolioView):
            raise TypeError("portfolio must satisfy RiskPortfolioView.")

        admitted, immediate = self._admit(request)
        if not admitted:
            if immediate is None:
                raise RuntimeError("Rejected supervisor admission has no result.")
            self._publish_skipped(immediate)
            return immediate

        result: ExecutionResult | None = None
        try:
            self._event_publisher.publish(
                ExecutionStarted(
                    correlation_id=request.correlation_id,
                    idempotency_key=request.idempotency_key,
                    symbol=request.symbol,
                    source=request.source.value,
                )
            )
            result = self._execute_services(
                portfolio,
                request,
                open_order_symbols=open_order_symbols,
            )
            return result
        except Exception as error:
            decision = ExecutionDecision(
                approved=False,
                code="SUPERVISOR_ABORTED",
                policy=type(self).__name__,
                explanation=str(error),
                correlation_id=request.correlation_id,
                configuration=(("error_type", type(error).__name__),),
            )
            result = ExecutionResult(
                request=request,
                decision=decision,
            )
            self._publish_aborted(result)
            return result
        finally:
            self._finish(request, result)

    def _record_decision(self, result: ExecutionResult) -> None:
        metric_by_code = {
            "IDEMPOTENT_REPLAY": CounterMetric.IDEMPOTENT_REPLAYS,
            "IDEMPOTENCY_CONFLICT": CounterMetric.IDEMPOTENCY_CONFLICTS,
            "IDEMPOTENCY_IN_FLIGHT": CounterMetric.IDEMPOTENCY_CONFLICTS,
            "DUPLICATE_EXECUTION": CounterMetric.DUPLICATE_EXECUTIONS,
            "SYMBOL_BUSY": CounterMetric.SYMBOL_BUSY_REJECTIONS,
            "COOLDOWN_ACTIVE": CounterMetric.COOLDOWN_REJECTIONS,
        }
        metric = metric_by_code.get(result.decision.code)
        if metric is not None:
            self._operational_metrics.increment(metric)

    def _execute_services(
        self,
        portfolio: RiskPortfolioView,
        request: ExecutionRequest,
        *,
        open_order_symbols: frozenset[str],
    ) -> ExecutionResult:
        preview = self._preview_service.preview(
            portfolio,
            PreviewTradeRequest(
                symbol=request.symbol,
                side=request.side,
                entry_price=request.entry_price,
                stop_price=request.stop_price,
                target_price=request.target_price,
                correlation_id=request.correlation_id,
            ),
            open_order_symbols=open_order_symbols,
        )
        if not preview.approved:
            decision = self._service_rejection_decision(
                correlation_id=request.correlation_id,
                code=preview.risk_code or "PREVIEW_REJECTED",
                rejections=preview.rejections,
                fallback="Deterministic preview rejected the execution request.",
            )
            result = ExecutionResult(
                request=request,
                decision=decision,
                preview=preview,
            )
            self._publish_aborted(result)
            return result

        if request.mode is ExecutionMode.PREVIEW_ONLY:
            decision = ExecutionDecision(
                approved=True,
                code="PREVIEW_COMPLETED",
                policy=type(self).__name__,
                explanation="Deterministic supervised preview completed successfully.",
                correlation_id=request.correlation_id,
            )
            result = ExecutionResult(
                request=request,
                decision=decision,
                preview=preview,
            )
            self._event_publisher.publish(
                ExecutionCompleted(
                    correlation_id=request.correlation_id,
                    idempotency_key=request.idempotency_key,
                    symbol=request.symbol,
                    source=request.source.value,
                    order_id=None,
                    quantity=preview.quantity,
                )
            )
            return result

        submission = self._submit_service.submit(
            portfolio,
            SubmitTradeRequest(
                symbol=request.symbol,
                side=request.side,
                entry_price=request.entry_price,
                stop_price=request.stop_price,
                target_price=request.target_price,
                expected_plan=ExpectedTradePlan(
                    approved=preview.approved,
                    quantity=preview.quantity,
                    dollar_risk=preview.dollar_risk,
                    position_value=preview.position_value,
                    reasons=preview.reasons,
                    risk_code=preview.risk_code,
                    correlation_id=request.correlation_id,
                ),
            ),
            open_order_symbols=open_order_symbols,
        )
        if not submission.submitted:
            decision = self._service_rejection_decision(
                correlation_id=request.correlation_id,
                code=submission.code,
                rejections=submission.rejections,
                fallback=submission.explanation,
            )
            result = ExecutionResult(
                request=request,
                decision=decision,
                preview=preview,
                submission=submission,
            )
            self._publish_aborted(result)
            return result

        decision = ExecutionDecision(
            approved=True,
            code="EXECUTION_COMPLETED",
            policy=type(self).__name__,
            explanation="Deterministic execution completed successfully.",
            correlation_id=request.correlation_id,
        )
        result = ExecutionResult(
            request=request,
            decision=decision,
            preview=preview,
            submission=submission,
        )
        self._event_publisher.publish(
            ExecutionCompleted(
                correlation_id=request.correlation_id,
                idempotency_key=request.idempotency_key,
                symbol=request.symbol,
                source=request.source.value,
                order_id=submission.order_id,
                quantity=submission.quantity,
            )
        )
        return result

    def _admit(
        self,
        request: ExecutionRequest,
    ) -> tuple[bool, ExecutionResult | None]:
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("Supervisor clock must return a timezone-aware datetime.")

        with self._state_lock:
            previous = self._completed_by_key.get(request.idempotency_key)
            if previous is not None:
                if previous.request.fingerprint != request.fingerprint:
                    return False, self._skipped_result(
                        request,
                        code="IDEMPOTENCY_CONFLICT",
                        policy="IdempotencyGuard",
                        explanation=(
                            "The idempotency key was already used for a different "
                            "execution request."
                        ),
                        configuration=(
                            ("original_correlation_id", previous.correlation_id),
                        ),
                    )

                decision = ExecutionDecision(
                    approved=False,
                    code="IDEMPOTENT_REPLAY",
                    policy="IdempotencyGuard",
                    explanation=(
                        "The completed result for this idempotency key was replayed."
                    ),
                    correlation_id=previous.correlation_id,
                    configuration=(
                        ("attempted_correlation_id", request.correlation_id),
                    ),
                )
                return False, replace(
                    previous,
                    decision=decision,
                    replayed=True,
                )

            in_flight = self._in_flight_keys.get(request.idempotency_key)
            if in_flight is not None:
                return False, self._skipped_result(
                    request,
                    code="IDEMPOTENCY_IN_FLIGHT",
                    policy="IdempotencyGuard",
                    explanation=(
                        "The idempotency key already has an active execution."
                    ),
                )

            policy_decisions = (
                self._duplicate_policy.evaluate(
                    request,
                    fingerprints=frozenset(
                        self._successful_fingerprints | self._in_flight_fingerprints
                    ),
                ),
                self._concurrent_symbol_policy.evaluate(
                    request,
                    active_symbols=frozenset(self._active_symbols),
                ),
                self._cooldown_policy.evaluate(
                    request,
                    last_execution_at=self._last_success_by_symbol.get(request.symbol),
                    now=now,
                ),
                self._market_state_policy.evaluate(request),
            )
            rejected = next(
                (decision for decision in policy_decisions if not decision.approved),
                None,
            )
            if rejected is not None:
                return False, self._from_policy_decision(request, rejected)

            self._active_symbols.add(request.symbol)
            self._in_flight_keys[request.idempotency_key] = request.fingerprint
            self._in_flight_fingerprints.add(request.fingerprint)
            return True, None

    def _finish(
        self,
        request: ExecutionRequest,
        result: ExecutionResult | None,
    ) -> None:
        now = self._clock()
        with self._state_lock:
            self._active_symbols.discard(request.symbol)
            self._in_flight_keys.pop(request.idempotency_key, None)
            self._in_flight_fingerprints.discard(request.fingerprint)
            if result is None:
                return

            self._completed_by_key[request.idempotency_key] = result
            if result.submitted:
                self._successful_fingerprints.add(request.fingerprint)
                self._last_success_by_symbol[request.symbol] = now

    def _publish_skipped(self, result: ExecutionResult) -> None:
        self._event_publisher.publish(
            ExecutionSkipped(
                correlation_id=result.correlation_id,
                idempotency_key=result.request.idempotency_key,
                symbol=result.request.symbol,
                source=result.request.source.value,
                code=result.decision.code,
                policy=result.decision.policy,
                explanation=result.decision.explanation,
                configuration=result.decision.configuration,
            )
        )

    def _publish_aborted(self, result: ExecutionResult) -> None:
        self._event_publisher.publish(
            ExecutionAborted(
                correlation_id=result.correlation_id,
                idempotency_key=result.request.idempotency_key,
                symbol=result.request.symbol,
                source=result.request.source.value,
                code=result.decision.code,
                policy=result.decision.policy,
                explanation=result.decision.explanation,
                configuration=result.decision.configuration,
            )
        )

    @staticmethod
    def _service_rejection_decision(
        *,
        correlation_id: str,
        code: str,
        rejections: tuple[PolicyExplanation, ...],
        fallback: str,
    ) -> ExecutionDecision:
        primary = (
            rejections[0]
            if rejections
            else PolicyExplanation(
                policy="ApplicationService",
                explanation=fallback,
            )
        )
        return ExecutionDecision(
            approved=False,
            code=code,
            policy=primary.policy,
            explanation=primary.explanation,
            correlation_id=correlation_id,
            configuration=primary.configuration,
        )

    @staticmethod
    def _from_policy_decision(
        request: ExecutionRequest,
        decision: SupervisorPolicyDecision,
    ) -> ExecutionResult:
        return ExecutionSupervisor._skipped_result(
            request,
            code=decision.code,
            policy=decision.policy,
            explanation=decision.explanation,
            configuration=decision.configuration,
        )

    @staticmethod
    def _skipped_result(
        request: ExecutionRequest,
        *,
        code: str,
        policy: str,
        explanation: str,
        configuration: tuple[tuple[str, str], ...] = (),
    ) -> ExecutionResult:
        return ExecutionResult(
            request=request,
            decision=ExecutionDecision(
                approved=False,
                code=code,
                policy=policy,
                explanation=explanation,
                correlation_id=request.correlation_id,
                configuration=configuration,
            ),
        )
