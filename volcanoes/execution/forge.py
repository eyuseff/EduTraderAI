"""Execution coordinator for Volcanes — The Real Volcanoes."""

from __future__ import annotations

from dataclasses import dataclass

from volcanoes.domain import (
    Candidate,
    GuardianDecision,
    Order,
    TradeSide,
)
from volcanoes.execution.broker import Broker


@dataclass(frozen=True)
class ForgeResult:
    """Explainable result produced by Forge."""

    submitted: bool
    reason: str
    order: Order | None = None


class Forge:
    """Submit only Guardian-approved candidates to a broker."""

    def __init__(
        self,
        broker: Broker,
        allocation_fraction: float = 0.10,
    ) -> None:
        if not 0 < allocation_fraction <= 1:
            raise ValueError(
                "Allocation fraction must be greater than 0 and at most 1."
            )

        self.broker = broker
        self.allocation_fraction = allocation_fraction

    def execute(
        self,
        candidate: Candidate,
        decision: GuardianDecision,
    ) -> ForgeResult:
        """Create and submit a buy order for an approved candidate."""

        if not decision.approved:
            return ForgeResult(
                submitted=False,
                reason=f"Guardian rejected candidate: {decision.reason}",
            )

        if candidate.entry_price is None or candidate.entry_price <= 0:
            return ForgeResult(
                submitted=False,
                reason="Candidate has no valid entry price.",
            )

        available_cash = self.broker.get_cash_balance()
        allocated_cash = available_cash * self.allocation_fraction
        quantity = int(allocated_cash // candidate.entry_price)

        if quantity <= 0:
            return ForgeResult(
                submitted=False,
                reason="Allocated cash is insufficient to buy one share.",
            )

        order = Order(
            symbol=candidate.symbol,
            side=TradeSide.BUY,
            quantity=quantity,
            price=candidate.entry_price,
        )

        completed_order = self.broker.submit_order(order)

        return ForgeResult(
            submitted=True,
            reason=(
                "Order completed with status "
                f"{completed_order.status.value}."
            ),
            order=completed_order,
        )
