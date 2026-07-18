"""
EduTrader AI
Risk Management Engine

Creates volatility-adjusted trade plans using ATR.
"""

from dataclasses import dataclass

from config import DECIMALS


@dataclass
class RiskResult:
    """Structured trade-risk calculation."""

    entry: float
    stop_loss: float
    target: float
    risk_amount: float
    reward_amount: float
    risk_percent: float
    reward_percent: float
    risk_reward: float


class RiskEngine:
    """Calculates ATR-based stop-loss and target prices."""

    def __init__(
        self,
        stop_atr_multiplier: float = 1.5,
        target_atr_multiplier: float = 3.0,
    ) -> None:
        if stop_atr_multiplier <= 0:
            raise ValueError(
                "stop_atr_multiplier must be greater than zero."
            )

        if target_atr_multiplier <= 0:
            raise ValueError(
                "target_atr_multiplier must be greater than zero."
            )

        self.stop_atr_multiplier = stop_atr_multiplier
        self.target_atr_multiplier = target_atr_multiplier

    def calculate(self, stock: dict) -> RiskResult:
        """
        Calculate an ATR-adjusted trade plan.

        The stock dictionary must contain:
        - Price
        - ATR
        """

        price = float(stock["Price"])
        atr = float(stock["ATR"])

        if price <= 0:
            raise ValueError("Stock price must be greater than zero.")

        if atr <= 0:
            raise ValueError("ATR must be greater than zero.")

        risk_amount = atr * self.stop_atr_multiplier
        reward_amount = atr * self.target_atr_multiplier

        stop_loss = max(0.0, price - risk_amount)
        target = price + reward_amount

        risk_percent = risk_amount / price * 100
        reward_percent = reward_amount / price * 100
        risk_reward = reward_amount / risk_amount

        return RiskResult(
            entry=round(price, DECIMALS),
            stop_loss=round(stop_loss, DECIMALS),
            target=round(target, DECIMALS),
            risk_amount=round(risk_amount, DECIMALS),
            reward_amount=round(reward_amount, DECIMALS),
            risk_percent=round(risk_percent, DECIMALS),
            reward_percent=round(reward_percent, DECIMALS),
            risk_reward=round(risk_reward, DECIMALS),
        )