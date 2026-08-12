"""Execution coordinator for Volcanes — The Real Volcanoes."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

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
        allocation_fraction: Decimal | int | float | str = Decimal("0.10"),
    ) -> None:
        fraction = self._to_decimal(allocation_fraction)

        if not Decimal("0") < fraction <= Decimal("1"):
            raise ValueError(
                "Allocation fraction must be greater than 0 and at most 1."
            )

        self.broker = broker
        self.allocation_fraction = fraction

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

        if candidate.entry_price is None:
            return ForgeResult(
                submitted=False,
                reason="Candidate has no valid entry price.",
            )

        entry_price = self._to_decimal(candidate.entry_price)

        if entry_price <= Decimal("0"):
            return ForgeResult(
                submitted=False,
                reason="Candidate has no valid entry price.",
            )

        available_cash = self.broker.get_cash_balance()
        allocated_cash = available_cash * self.allocation_fraction
        quantity = int(allocated_cash // entry_price)

        if quantity <= 0:
            return ForgeResult(
                submitted=False,
                reason="Allocated cash is insufficient to buy one share.",
            )

        order = Order(
            symbol=candidate.symbol,
            side=TradeSide.BUY,
            quantity=quantity,
            price=entry_price,
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

    @staticmethod
    def _to_decimal(value: Decimal | int | float | str) -> Decimal:
        """Convert a supported numeric value to Decimal safely."""

        if isinstance(value, Decimal):
            return value

        if isinstance(value, bool):
            raise TypeError(
                "Boolean values cannot be used as financial values."
            )

        if isinstance(value, (int, float, str)):
            try:
                return Decimal(str(value))
            except Exception as exc:
                raise ValueError(
                    "Financial value must be numeric."
                ) from exc

        raise TypeError(
            "Financial value must be a Decimal, int, float, or numeric string."
        )
