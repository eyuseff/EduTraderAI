"""
EduTrader AI
Position Sizing Engine

Calculates a position size based on account balance,
maximum portfolio risk, entry price, and stop-loss price.
"""

from dataclasses import dataclass
from math import floor


@dataclass(frozen=True)
class PositionSizeResult:
    """Structured position-sizing calculation."""

    account_balance: float
    risk_percentage: float
    maximum_loss: float
    risk_per_share: float
    shares: int
    capital_required: float
    estimated_profit: float
    actual_loss: float
    actual_risk_percentage: float


class PositionSizingEngine:
    """Calculates risk-controlled equity position sizes."""

    def __init__(
        self,
        account_balance: float = 10_000.0,
        risk_percentage: float = 1.0,
    ) -> None:
        if account_balance <= 0:
            raise ValueError("Account balance must be greater than zero.")

        if not 0 < risk_percentage <= 100:
            raise ValueError(
                "Risk percentage must be greater than 0 and no more than 100."
            )

        self.account_balance = float(account_balance)
        self.risk_percentage = float(risk_percentage)

    def calculate(
        self,
        entry_price: float,
        stop_loss: float,
        target_price: float,
    ) -> PositionSizeResult:
        """
        Calculate the maximum whole-share position.

        The position is limited by:

        1. Maximum permitted monetary loss.
        2. Available account capital.
        """

        entry_price = float(entry_price)
        stop_loss = float(stop_loss)
        target_price = float(target_price)

        self._validate_prices(
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_price=target_price,
        )

        maximum_loss = (
            self.account_balance * self.risk_percentage / 100
        )

        risk_per_share = entry_price - stop_loss
        reward_per_share = target_price - entry_price

        shares_by_risk = floor(maximum_loss / risk_per_share)
        shares_by_capital = floor(self.account_balance / entry_price)

        shares = max(
            0,
            min(shares_by_risk, shares_by_capital),
        )

        capital_required = shares * entry_price
        actual_loss = shares * risk_per_share
        estimated_profit = shares * reward_per_share

        actual_risk_percentage = (
            actual_loss / self.account_balance * 100
            if self.account_balance > 0
            else 0.0
        )

        return PositionSizeResult(
            account_balance=round(self.account_balance, 2),
            risk_percentage=round(self.risk_percentage, 2),
            maximum_loss=round(maximum_loss, 2),
            risk_per_share=round(risk_per_share, 2),
            shares=shares,
            capital_required=round(capital_required, 2),
            estimated_profit=round(estimated_profit, 2),
            actual_loss=round(actual_loss, 2),
            actual_risk_percentage=round(
                actual_risk_percentage,
                2,
            ),
        )

    @staticmethod
    def _validate_prices(
        entry_price: float,
        stop_loss: float,
        target_price: float,
    ) -> None:
        """Validate a long-position trade plan."""

        if entry_price <= 0:
            raise ValueError(
                "Entry price must be greater than zero."
            )

        if stop_loss < 0:
            raise ValueError(
                "Stop-loss price cannot be negative."
            )

        if stop_loss >= entry_price:
            raise ValueError(
                "For a long position, stop loss must be below entry."
            )

        if target_price <= entry_price:
            raise ValueError(
                "For a long position, target must be above entry."
            )