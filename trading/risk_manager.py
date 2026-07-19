from __future__ import annotations

from dataclasses import dataclass, field
from math import floor, isfinite

from broker.base import AccountSnapshot, BrokerPosition


@dataclass(frozen=True)
class RiskLimits:
    risk_per_trade_pct: float = 0.25
    max_daily_loss_pct: float = 1.0
    max_open_positions: int = 5
    max_total_exposure_pct: float = 50.0
    max_single_position_pct: float = 12.0
    minimum_reward_risk: float = 2.0
    minimum_price: float = 10.0
    long_only: bool = True


@dataclass(frozen=True)
class TradeProposal:
    symbol: str
    entry_price: float
    stop_price: float
    target_price: float
    side: str = "buy"


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    quantity: int
    maximum_loss: float
    capital_required: float
    reward_risk: float
    reasons: list[str] = field(default_factory=list)


class RiskManager:
    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()

    def evaluate(
        self,
        proposal: TradeProposal,
        account: AccountSnapshot,
        positions: list[BrokerPosition],
        open_order_symbols: set[str] | None = None,
    ) -> RiskDecision:
        reasons: list[str] = []
        symbol = proposal.symbol.strip().upper()
        open_order_symbols = {s.upper() for s in (open_order_symbols or set())}

        values = [proposal.entry_price, proposal.stop_price, proposal.target_price]
        if not symbol or any(not isfinite(v) for v in values):
            return self._rejected("Invalid symbol or price value.")

        if self.limits.long_only and proposal.side.lower() != "buy":
            reasons.append("The current safety policy allows long trades only.")
        if proposal.entry_price < self.limits.minimum_price:
            reasons.append(
                f"Price is below the ${self.limits.minimum_price:.2f} minimum."
            )
        if proposal.stop_price <= 0 or proposal.stop_price >= proposal.entry_price:
            reasons.append("Stop price must be above zero and below the entry price.")
        if proposal.target_price <= proposal.entry_price:
            reasons.append("Target price must be above the entry price.")
        if account.equity <= 0:
            reasons.append("Account equity is unavailable or zero.")

        risk_per_share = proposal.entry_price - proposal.stop_price
        reward_per_share = proposal.target_price - proposal.entry_price
        reward_risk = (
            reward_per_share / risk_per_share if risk_per_share > 0 else 0.0
        )
        if reward_risk < self.limits.minimum_reward_risk:
            reasons.append(
                f"Reward/risk {reward_risk:.2f} is below the required "
                f"{self.limits.minimum_reward_risk:.2f}."
            )

        if len(positions) >= self.limits.max_open_positions:
            reasons.append("Maximum number of open positions has been reached.")
        if any(p.symbol.upper() == symbol for p in positions):
            reasons.append("A position in this symbol already exists.")
        if symbol in open_order_symbols:
            reasons.append("An open order for this symbol already exists.")

        daily_loss_limit = account.equity * self.limits.max_daily_loss_pct / 100
        if account.daily_pnl <= -daily_loss_limit:
            reasons.append("Daily loss lock is active.")

        current_exposure = sum(abs(p.market_value) for p in positions)
        max_total_exposure = account.equity * self.limits.max_total_exposure_pct / 100
        available_exposure = max(0.0, max_total_exposure - current_exposure)
        max_single_value = account.equity * self.limits.max_single_position_pct / 100
        max_risk_dollars = account.equity * self.limits.risk_per_trade_pct / 100

        if risk_per_share <= 0:
            quantity = 0
        else:
            quantity_by_risk = floor(max_risk_dollars / risk_per_share)
            quantity_by_cash = floor(account.buying_power / proposal.entry_price)
            quantity_by_total_exposure = floor(available_exposure / proposal.entry_price)
            quantity_by_single_position = floor(max_single_value / proposal.entry_price)
            quantity = max(
                0,
                min(
                    quantity_by_risk,
                    quantity_by_cash,
                    quantity_by_total_exposure,
                    quantity_by_single_position,
                ),
            )

        if quantity < 1:
            reasons.append("Risk and exposure limits produce a zero-share position.")

        return RiskDecision(
            approved=not reasons,
            quantity=quantity,
            maximum_loss=round(quantity * max(risk_per_share, 0), 2),
            capital_required=round(quantity * proposal.entry_price, 2),
            reward_risk=round(reward_risk, 2),
            reasons=reasons,
        )

    @staticmethod
    def _rejected(reason: str) -> RiskDecision:
        return RiskDecision(
            approved=False,
            quantity=0,
            maximum_loss=0.0,
            capital_required=0.0,
            reward_risk=0.0,
            reasons=[reason],
        )
