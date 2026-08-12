"""Shared operational-event helpers for trade application services."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from decimal import Decimal
from enum import Enum

from volcanoes.events import (
    EventPublisher,
    PolicyConfiguration,
    PolicyExplanation,
    PolicyViolation,
    TradeRejected,
)
from volcanoes.execution import TradePlan, TradePlanner


def plan_rejections(
    plan: TradePlan,
    planner: TradePlanner,
) -> tuple[PolicyExplanation, ...]:
    """Return ordered, configured explanations for a rejected trade plan."""

    policies = {type(policy).__name__: policy for policy in planner.policies.policies}
    explanations = tuple(
        PolicyExplanation(
            policy=decision.policy,
            explanation=decision.explanation,
            configuration=_configuration(policies.get(decision.policy)),
        )
        for decision in plan.policy_decisions
        if not decision.approved
    )
    if explanations:
        return _unique(explanations)

    if not plan.approved:
        return (
            PolicyExplanation(
                policy="PositionSizing",
                explanation=plan.reason,
                configuration=(
                    (
                        "maximum_risk",
                        _configuration_value(
                            planner.risk_manager.config.max_risk_per_trade
                        ),
                    ),
                ),
            ),
        )

    return ()


def publish_rejection(
    publisher: EventPublisher,
    *,
    operation: str,
    symbol: str,
    correlation_id: str,
    explanations: tuple[PolicyExplanation, ...],
) -> None:
    """Publish configured violations followed by one terminal rejection."""

    configured = _unique(explanations)
    if not configured:
        raise ValueError("At least one rejection explanation is required.")

    for explanation in configured:
        publisher.publish(
            PolicyViolation(
                correlation_id=correlation_id,
                operation=operation,
                symbol=symbol,
                policy=explanation.policy,
                explanation=explanation.explanation,
                configuration=explanation.configuration,
            )
        )

    primary = configured[0]
    publisher.publish(
        TradeRejected(
            correlation_id=correlation_id,
            operation=operation,
            symbol=symbol,
            policy=primary.policy,
            explanation=primary.explanation,
            configuration=primary.configuration,
        )
    )


def configuration_from_pairs(
    *pairs: tuple[str, object],
) -> PolicyConfiguration:
    """Create sorted immutable configuration from named scalar values."""

    return tuple(sorted((name, _configuration_value(value)) for name, value in pairs))


def _configuration(policy: object | None) -> PolicyConfiguration:
    if policy is None or not is_dataclass(policy):
        return ()

    return configuration_from_pairs(
        *(
            (policy_field.name, getattr(policy, policy_field.name))
            for policy_field in fields(policy)
        )
    )


def _configuration_value(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, bool):
        return str(value).lower()
    if value is None:
        return "null"
    return str(value)


def _unique(
    explanations: tuple[PolicyExplanation, ...],
) -> tuple[PolicyExplanation, ...]:
    return tuple(dict.fromkeys(explanations))
