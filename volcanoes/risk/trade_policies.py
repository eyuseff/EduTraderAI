"""Immutable, deterministic policies used during trade planning."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from enum import StrEnum
from typing import Protocol

from volcanoes.domain import TradeIntent, TradeSide
from volcanoes.risk.portfolio_view import RiskPortfolioView
from volcanoes.risk.risk_config import RiskConfig


class QuantityLimitMode(StrEnum):
    """Choose whether a capital limit rejects or caps a proposed quantity."""

    REJECT = "REJECT"
    CAP = "CAP"


class DailyLossBasis(StrEnum):
    """Choose the equity base used to calculate the daily loss limit."""

    STARTING_EQUITY = "STARTING_EQUITY"
    CURRENT_EQUITY = "CURRENT_EQUITY"


@dataclass(frozen=True, slots=True)
class PolicyParityConfig:
    """Infrastructure-neutral values for the buy-preview parity profile."""

    minimum_price: Decimal
    minimum_reward_risk: Decimal
    maximum_daily_loss: Decimal
    maximum_position_size: Decimal
    maximum_portfolio_exposure: Decimal
    maximum_open_positions: int

    def __post_init__(self) -> None:
        if self.minimum_price < Decimal("0"):
            raise ValueError("minimum_price cannot be negative.")
        if self.minimum_reward_risk < Decimal("0"):
            raise ValueError("minimum_reward_risk cannot be negative.")
        _validate_fraction(
            self.maximum_daily_loss,
            "maximum_daily_loss",
        )
        _validate_fraction(
            self.maximum_position_size,
            "maximum_position_size",
        )
        _validate_fraction(
            self.maximum_portfolio_exposure,
            "maximum_portfolio_exposure",
        )
        if self.maximum_open_positions < 0:
            raise ValueError("maximum_open_positions cannot be negative.")


@dataclass(frozen=True, slots=True)
class TradePolicyContext:
    """Immutable input shared by every planning policy."""

    portfolio: RiskPortfolioView
    trade_intent: TradeIntent
    quantity: int
    target_price: Decimal | None = None
    open_order_symbols: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise TypeError("quantity must be a whole number.")
        if self.quantity < 0:
            raise ValueError("quantity cannot be negative.")
        if self.target_price is not None and not isinstance(
            self.target_price,
            Decimal,
        ):
            raise TypeError("target_price must be a Decimal or None.")

        object.__setattr__(
            self,
            "open_order_symbols",
            frozenset(
                symbol.strip().upper()
                for symbol in self.open_order_symbols
                if symbol.strip()
            ),
        )

    @property
    def position_value(self) -> Decimal:
        """Return the notional value of the proposed quantity."""

        return Decimal(self.quantity) * self.trade_intent.entry_price


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Explain one deterministic policy outcome."""

    policy: str
    approved: bool
    code: str
    explanation: str
    maximum_quantity: int | None = None

    def __post_init__(self) -> None:
        if self.maximum_quantity is not None and self.maximum_quantity < 0:
            raise ValueError("maximum_quantity cannot be negative.")


class TradePolicy(Protocol):
    """Structural contract implemented by independently testable policies."""

    def evaluate(self, context: TradePolicyContext) -> PolicyDecision:
        """Evaluate one immutable trade-planning context."""
        ...


@dataclass(frozen=True, slots=True)
class TradePolicySet:
    """Ordered immutable policy configuration orchestrated by TradePlanner."""

    policies: tuple[TradePolicy, ...]
    collect_all_rejections: bool = False
    evaluate_when_zero_quantity: bool = False
    zero_quantity_reason: str = "Risk allowance is insufficient to trade one share."

    @classmethod
    def execution_defaults(cls, config: RiskConfig) -> TradePolicySet:
        """Build policies matching the existing deterministic execution rules."""

        return cls(
            policies=(
                DailyLossPolicy(
                    maximum_loss_fraction=config.max_daily_loss,
                    basis=DailyLossBasis.STARTING_EQUITY,
                    rejection_reason="Maximum daily loss limit has been reached.",
                ),
                BuyingPowerPolicy(
                    mode=QuantityLimitMode.REJECT,
                    rejection_reason="Trade exceeds available buying power.",
                ),
                MaximumPositionSizePolicy(
                    maximum_position_fraction=config.max_position_size,
                    mode=QuantityLimitMode.REJECT,
                    include_existing_position=True,
                    rejection_reason="Trade exceeds maximum position size.",
                ),
                OpenPositionLimitPolicy(
                    maximum_open_positions=config.max_open_positions,
                    allow_existing_position=True,
                    rejection_reason="Maximum number of open positions exceeded.",
                ),
                PortfolioExposurePolicy(
                    maximum_exposure_fraction=config.max_portfolio_exposure,
                    mode=QuantityLimitMode.REJECT,
                    rejection_reason="Trade exceeds maximum portfolio exposure.",
                ),
            )
        )

    @classmethod
    def preview_parity(cls, config: PolicyParityConfig) -> TradePolicySet:
        """Build the ordered profile matching the legacy buy preview."""

        return cls(
            policies=(
                MinimumPricePolicy(config.minimum_price),
                RewardRiskPolicy(config.minimum_reward_risk),
                OpenPositionLimitPolicy(
                    maximum_open_positions=config.maximum_open_positions,
                    allow_existing_position=False,
                    rejection_reason=(
                        "Maximum number of open positions has been reached."
                    ),
                ),
                DuplicatePositionPolicy(),
                DuplicateOrderPolicy(),
                DailyLossPolicy(
                    maximum_loss_fraction=config.maximum_daily_loss,
                    basis=DailyLossBasis.CURRENT_EQUITY,
                    rejection_reason="Daily loss lock is active.",
                ),
                BuyingPowerPolicy(mode=QuantityLimitMode.CAP),
                MaximumPositionSizePolicy(
                    maximum_position_fraction=(config.maximum_position_size),
                    mode=QuantityLimitMode.CAP,
                    include_existing_position=False,
                ),
                PortfolioExposurePolicy(
                    maximum_exposure_fraction=(config.maximum_portfolio_exposure),
                    mode=QuantityLimitMode.CAP,
                ),
            ),
            collect_all_rejections=True,
            evaluate_when_zero_quantity=True,
            zero_quantity_reason=(
                "Risk and exposure limits produce a zero-share position."
            ),
        )


@dataclass(frozen=True, slots=True)
class MinimumPricePolicy:
    """Reject instruments priced below an explicit minimum."""

    minimum_price: Decimal

    def __post_init__(self) -> None:
        if self.minimum_price < Decimal("0"):
            raise ValueError("minimum_price cannot be negative.")

    def evaluate(self, context: TradePolicyContext) -> PolicyDecision:
        approved = context.trade_intent.entry_price >= self.minimum_price
        explanation = (
            f"Entry price satisfies the ${self.minimum_price:.2f} minimum."
            if approved
            else f"Price is below the ${self.minimum_price:.2f} minimum."
        )
        return PolicyDecision(
            policy=type(self).__name__,
            approved=approved,
            code="MINIMUM_PRICE",
            explanation=explanation,
        )


@dataclass(frozen=True, slots=True)
class RewardRiskPolicy:
    """Require a minimum planned reward relative to per-share risk."""

    minimum_reward_risk: Decimal

    def __post_init__(self) -> None:
        if self.minimum_reward_risk < Decimal("0"):
            raise ValueError("minimum_reward_risk cannot be negative.")

    def evaluate(self, context: TradePolicyContext) -> PolicyDecision:
        target_price = context.target_price
        if target_price is None:
            return PolicyDecision(
                policy=type(self).__name__,
                approved=False,
                code="TARGET_PRICE_REQUIRED",
                explanation="Target price is required by reward/risk policy.",
            )

        if context.trade_intent.side is TradeSide.BUY:
            reward = target_price - context.trade_intent.entry_price
        else:
            reward = context.trade_intent.entry_price - target_price

        reward_risk = reward / context.trade_intent.risk_per_share
        approved = reward_risk >= self.minimum_reward_risk
        explanation = (
            (
                f"Reward/risk {reward_risk:.2f} meets the required "
                f"{self.minimum_reward_risk:.2f}."
            )
            if approved
            else (
                f"Reward/risk {reward_risk:.2f} is below the required "
                f"{self.minimum_reward_risk:.2f}."
            )
        )
        return PolicyDecision(
            policy=type(self).__name__,
            approved=approved,
            code="MINIMUM_REWARD_RISK",
            explanation=explanation,
        )


@dataclass(frozen=True, slots=True)
class DuplicatePositionPolicy:
    """Reject a symbol already held by the portfolio."""

    rejection_reason: str = "A position in this symbol already exists."

    def evaluate(self, context: TradePolicyContext) -> PolicyDecision:
        duplicate = context.portfolio.has_position(context.trade_intent.symbol)
        return PolicyDecision(
            policy=type(self).__name__,
            approved=not duplicate,
            code="DUPLICATE_POSITION",
            explanation=(
                self.rejection_reason
                if duplicate
                else "No position exists for the proposed symbol."
            ),
        )


@dataclass(frozen=True, slots=True)
class DuplicateOrderPolicy:
    """Reject a symbol already represented by an open order snapshot."""

    rejection_reason: str = "An open order for this symbol already exists."

    def evaluate(self, context: TradePolicyContext) -> PolicyDecision:
        duplicate = context.trade_intent.symbol in context.open_order_symbols
        return PolicyDecision(
            policy=type(self).__name__,
            approved=not duplicate,
            code="DUPLICATE_ORDER",
            explanation=(
                self.rejection_reason
                if duplicate
                else "No open order exists for the proposed symbol."
            ),
        )


@dataclass(frozen=True, slots=True)
class BuyingPowerPolicy:
    """Reject or cap quantity according to available buying power."""

    mode: QuantityLimitMode = QuantityLimitMode.REJECT
    rejection_reason: str = "Trade exceeds available buying power."

    def evaluate(self, context: TradePolicyContext) -> PolicyDecision:
        maximum_quantity = _whole_units(
            context.portfolio.buying_power,
            context.trade_intent.entry_price,
        )
        exceeds_limit = context.quantity > maximum_quantity

        if exceeds_limit and self.mode is QuantityLimitMode.REJECT:
            return PolicyDecision(
                policy=type(self).__name__,
                approved=False,
                code="INSUFFICIENT_BUYING_POWER",
                explanation=self.rejection_reason,
            )

        return PolicyDecision(
            policy=type(self).__name__,
            approved=True,
            code="BUYING_POWER_LIMIT",
            explanation=(f"Buying power permits at most {maximum_quantity} shares."),
            maximum_quantity=(
                maximum_quantity if self.mode is QuantityLimitMode.CAP else None
            ),
        )


@dataclass(frozen=True, slots=True)
class DailyLossPolicy:
    """Reject trades after a configured daily loss threshold is reached."""

    maximum_loss_fraction: Decimal
    basis: DailyLossBasis = DailyLossBasis.STARTING_EQUITY
    rejection_reason: str = "Maximum daily loss limit has been reached."

    def __post_init__(self) -> None:
        _validate_fraction(
            self.maximum_loss_fraction,
            "maximum_loss_fraction",
        )

    def evaluate(self, context: TradePolicyContext) -> PolicyDecision:
        equity_base = (
            context.portfolio.equity
            if self.basis is DailyLossBasis.CURRENT_EQUITY
            else context.portfolio.starting_cash
        )
        maximum_loss = equity_base * self.maximum_loss_fraction
        locked = context.portfolio.realized_pnl <= -maximum_loss
        return PolicyDecision(
            policy=type(self).__name__,
            approved=not locked,
            code="MAX_DAILY_LOSS",
            explanation=(
                self.rejection_reason
                if locked
                else f"Daily loss remains within {maximum_loss}."
            ),
        )


@dataclass(frozen=True, slots=True)
class MaximumPositionSizePolicy:
    """Reject or cap quantity according to maximum single-position value."""

    maximum_position_fraction: Decimal
    mode: QuantityLimitMode = QuantityLimitMode.REJECT
    include_existing_position: bool = True
    rejection_reason: str = "Trade exceeds maximum position size."

    def __post_init__(self) -> None:
        _validate_fraction(
            self.maximum_position_fraction,
            "maximum_position_fraction",
        )

    def evaluate(self, context: TradePolicyContext) -> PolicyDecision:
        maximum_value = context.portfolio.equity * self.maximum_position_fraction
        existing_value = Decimal("0")
        if self.include_existing_position:
            position = context.portfolio.get_position(context.trade_intent.symbol)
            if position is not None:
                existing_value = (
                    Decimal(position.quantity) * context.trade_intent.entry_price
                )

        maximum_quantity = _whole_units(
            max(Decimal("0"), maximum_value - existing_value),
            context.trade_intent.entry_price,
        )
        exceeds_limit = context.quantity > maximum_quantity

        if exceeds_limit and self.mode is QuantityLimitMode.REJECT:
            return PolicyDecision(
                policy=type(self).__name__,
                approved=False,
                code="MAX_POSITION_SIZE",
                explanation=self.rejection_reason,
            )

        return PolicyDecision(
            policy=type(self).__name__,
            approved=True,
            code="MAX_POSITION_SIZE_LIMIT",
            explanation=(
                f"Position-size policy permits at most {maximum_quantity} shares."
            ),
            maximum_quantity=(
                maximum_quantity if self.mode is QuantityLimitMode.CAP else None
            ),
        )


@dataclass(frozen=True, slots=True)
class OpenPositionLimitPolicy:
    """Reject trades that exceed the configured open-position count."""

    maximum_open_positions: int
    allow_existing_position: bool = True
    rejection_reason: str = "Maximum number of open positions exceeded."

    def __post_init__(self) -> None:
        if self.maximum_open_positions < 0:
            raise ValueError("maximum_open_positions cannot be negative.")

    def evaluate(self, context: TradePolicyContext) -> PolicyDecision:
        existing = context.portfolio.has_position(context.trade_intent.symbol)
        approved = (
            self.allow_existing_position and existing
        ) or context.portfolio.open_positions < self.maximum_open_positions
        return PolicyDecision(
            policy=type(self).__name__,
            approved=approved,
            code="MAX_OPEN_POSITIONS",
            explanation=(
                "Open-position capacity is available."
                if approved
                else self.rejection_reason
            ),
        )


@dataclass(frozen=True, slots=True)
class PortfolioExposurePolicy:
    """Reject or cap quantity according to maximum gross exposure."""

    maximum_exposure_fraction: Decimal
    mode: QuantityLimitMode = QuantityLimitMode.REJECT
    rejection_reason: str = "Trade exceeds maximum portfolio exposure."

    def __post_init__(self) -> None:
        _validate_fraction(
            self.maximum_exposure_fraction,
            "maximum_exposure_fraction",
        )

    def evaluate(self, context: TradePolicyContext) -> PolicyDecision:
        maximum_value = context.portfolio.equity * self.maximum_exposure_fraction
        available_value = max(
            Decimal("0"),
            maximum_value - context.portfolio.invested_value,
        )
        maximum_quantity = _whole_units(
            available_value,
            context.trade_intent.entry_price,
        )
        exceeds_limit = context.quantity > maximum_quantity

        if exceeds_limit and self.mode is QuantityLimitMode.REJECT:
            return PolicyDecision(
                policy=type(self).__name__,
                approved=False,
                code="MAX_PORTFOLIO_EXPOSURE",
                explanation=self.rejection_reason,
            )

        return PolicyDecision(
            policy=type(self).__name__,
            approved=True,
            code="MAX_PORTFOLIO_EXPOSURE_LIMIT",
            explanation=(f"Exposure policy permits at most {maximum_quantity} shares."),
            maximum_quantity=(
                maximum_quantity if self.mode is QuantityLimitMode.CAP else None
            ),
        )


def _whole_units(capital: Decimal, price: Decimal) -> int:
    if capital <= Decimal("0"):
        return 0
    return int((capital / price).to_integral_value(rounding=ROUND_FLOOR))


def _validate_fraction(value: Decimal, name: str) -> None:
    if value < Decimal("0") or value > Decimal("1"):
        raise ValueError(f"{name} must be between zero and one.")
