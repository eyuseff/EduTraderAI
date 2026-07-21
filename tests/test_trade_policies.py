"""Exhaustive tests for immutable deterministic trade policies."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass
from decimal import Decimal
from typing import cast

import pytest

from volcanoes.domain import TradeIntent, TradeSide
from volcanoes.execution import TradePlanner
from volcanoes.risk import (
    BuyingPowerPolicy,
    DailyLossBasis,
    DailyLossPolicy,
    DuplicateOrderPolicy,
    DuplicatePositionPolicy,
    MaximumPositionSizePolicy,
    MinimumPricePolicy,
    OpenPositionLimitPolicy,
    PolicyParityConfig,
    PortfolioExposurePolicy,
    QuantityLimitMode,
    RewardRiskPolicy,
    RiskPositionView,
    TradePolicyContext,
    TradePolicySet,
)


@dataclass(frozen=True, slots=True)
class PositionView:
    symbol: str
    quantity: int


@dataclass(frozen=True, slots=True)
class PortfolioView:
    starting_cash: Decimal = Decimal("100000")
    equity: Decimal = Decimal("100000")
    buying_power: Decimal = Decimal("100000")
    realized_pnl: Decimal = Decimal("0")
    invested_value: Decimal = Decimal("0")
    positions: tuple[PositionView, ...] = ()

    @property
    def open_positions(self) -> int:
        return len(self.positions)

    def has_position(self, symbol: str) -> bool:
        return self.get_position(symbol) is not None

    def get_position(self, symbol: str) -> RiskPositionView | None:
        normalized = symbol.strip().upper()
        return cast(
            RiskPositionView | None,
            next(
                (
                    position
                    for position in self.positions
                    if position.symbol.strip().upper() == normalized
                ),
                None,
            ),
        )


def intent(
    *,
    symbol: str = "AAPL",
    entry: str = "100",
    stop: str = "95",
) -> TradeIntent:
    return TradeIntent(
        symbol=symbol,
        side=TradeSide.BUY,
        entry_price=Decimal(entry),
        stop_price=Decimal(stop),
    )


def context(
    *,
    portfolio: PortfolioView | None = None,
    trade_intent: TradeIntent | None = None,
    quantity: int = 100,
    target: str | None = "110",
    open_orders: frozenset[str] = frozenset(),
) -> TradePolicyContext:
    return TradePolicyContext(
        portfolio=portfolio or PortfolioView(),
        trade_intent=trade_intent or intent(),
        quantity=quantity,
        target_price=Decimal(target) if target is not None else None,
        open_order_symbols=open_orders,
    )


@pytest.mark.parametrize(
    ("policy", "policy_context", "expected_code", "expected_reason"),
    [
        (
            MinimumPricePolicy(Decimal("10")),
            context(trade_intent=intent(entry="5", stop="4"), target="7"),
            "MINIMUM_PRICE",
            "Price is below the $10.00 minimum.",
        ),
        (
            RewardRiskPolicy(Decimal("2")),
            context(target="101"),
            "MINIMUM_REWARD_RISK",
            "Reward/risk 0.20 is below the required 2.00.",
        ),
        (
            DuplicatePositionPolicy(),
            context(
                portfolio=PortfolioView(
                    positions=(PositionView("aapl", 10),),
                )
            ),
            "DUPLICATE_POSITION",
            "A position in this symbol already exists.",
        ),
        (
            DuplicateOrderPolicy(),
            context(open_orders=frozenset({" aapl "})),
            "DUPLICATE_ORDER",
            "An open order for this symbol already exists.",
        ),
        (
            BuyingPowerPolicy(),
            context(
                portfolio=PortfolioView(buying_power=Decimal("1000")),
            ),
            "INSUFFICIENT_BUYING_POWER",
            "Trade exceeds available buying power.",
        ),
        (
            DailyLossPolicy(Decimal("0.01")),
            context(
                portfolio=PortfolioView(realized_pnl=Decimal("-1000")),
            ),
            "MAX_DAILY_LOSS",
            "Maximum daily loss limit has been reached.",
        ),
    ],
)
def test_required_policies_are_deterministic_and_explain_rejections(
    policy: object,
    policy_context: TradePolicyContext,
    expected_code: str,
    expected_reason: str,
) -> None:
    first = policy.evaluate(policy_context)  # type: ignore[attr-defined]
    second = policy.evaluate(policy_context)  # type: ignore[attr-defined]

    assert first == second
    assert first.approved is False
    assert first.code == expected_code
    assert first.explanation == expected_reason
    assert first.policy == type(policy).__name__


@pytest.mark.parametrize(
    ("policy", "field"),
    [
        (MinimumPricePolicy(Decimal("10")), "minimum_price"),
        (RewardRiskPolicy(Decimal("2")), "minimum_reward_risk"),
        (DuplicatePositionPolicy(), "rejection_reason"),
        (DuplicateOrderPolicy(), "rejection_reason"),
        (BuyingPowerPolicy(), "mode"),
        (DailyLossPolicy(Decimal("0.01")), "maximum_loss_fraction"),
    ],
)
def test_required_policy_objects_are_immutable(
    policy: object,
    field: str,
) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(policy, field, None)


def test_minimum_price_policy_approves_boundary() -> None:
    decision = MinimumPricePolicy(Decimal("10")).evaluate(
        context(trade_intent=intent(entry="10", stop="9"), target="12")
    )

    assert decision.approved is True
    assert "$10.00 minimum" in decision.explanation


def test_reward_risk_policy_approves_boundary_and_requires_target() -> None:
    policy = RewardRiskPolicy(Decimal("2"))

    boundary = policy.evaluate(context(target="110"))
    missing_target = policy.evaluate(context(target=None))

    assert boundary.approved is True
    assert boundary.explanation == "Reward/risk 2.00 meets the required 2.00."
    assert missing_target.approved is False
    assert missing_target.code == "TARGET_PRICE_REQUIRED"


def test_duplicate_policies_normalize_symbols() -> None:
    duplicate_position = DuplicatePositionPolicy().evaluate(
        context(
            portfolio=PortfolioView(
                positions=(PositionView(" aApL ", 1),),
            )
        )
    )
    duplicate_order = DuplicateOrderPolicy().evaluate(
        context(open_orders=frozenset({" aapl "}))
    )

    assert duplicate_position.approved is False
    assert duplicate_order.approved is False


def test_buying_power_policy_can_cap_without_rejecting() -> None:
    decision = BuyingPowerPolicy(mode=QuantityLimitMode.CAP).evaluate(
        context(
            portfolio=PortfolioView(buying_power=Decimal("5050")),
        )
    )

    assert decision.approved is True
    assert decision.maximum_quantity == 50
    assert decision.explanation == "Buying power permits at most 50 shares."


def test_daily_loss_policy_supports_explicit_equity_bases() -> None:
    portfolio = PortfolioView(
        starting_cash=Decimal("100000"),
        equity=Decimal("99005"),
        realized_pnl=Decimal("-995"),
    )

    starting_basis = DailyLossPolicy(
        Decimal("0.01"),
        basis=DailyLossBasis.STARTING_EQUITY,
    ).evaluate(context(portfolio=portfolio))
    current_basis = DailyLossPolicy(
        Decimal("0.01"),
        basis=DailyLossBasis.CURRENT_EQUITY,
        rejection_reason="Daily loss lock is active.",
    ).evaluate(context(portfolio=portfolio))

    assert starting_basis.approved is True
    assert current_basis.approved is False
    assert current_basis.explanation == "Daily loss lock is active."


def test_zero_thresholds_remain_valid_configuration_values() -> None:
    policy_context = context()

    assert MinimumPricePolicy(Decimal("0")).evaluate(policy_context).approved
    assert RewardRiskPolicy(Decimal("0")).evaluate(policy_context).approved
    assert DailyLossPolicy(Decimal("0")).evaluate(policy_context).approved is False


def test_capital_limit_policies_produce_legacy_quantity_caps() -> None:
    portfolio = PortfolioView(
        equity=Decimal("100000"),
        buying_power=Decimal("50000"),
        invested_value=Decimal("49000"),
    )
    policy_context = context(portfolio=portfolio, quantity=1000)

    position = MaximumPositionSizePolicy(
        Decimal("0.12"),
        mode=QuantityLimitMode.CAP,
        include_existing_position=False,
    ).evaluate(policy_context)
    exposure = PortfolioExposurePolicy(
        Decimal("0.50"),
        mode=QuantityLimitMode.CAP,
    ).evaluate(policy_context)

    assert position.maximum_quantity == 120
    assert exposure.maximum_quantity == 10


def test_open_position_limit_can_match_legacy_or_execution_semantics() -> None:
    portfolio = PortfolioView(
        positions=(PositionView("AAPL", 10),),
    )
    policy_context = context(portfolio=portfolio)

    execution = OpenPositionLimitPolicy(
        maximum_open_positions=1,
        allow_existing_position=True,
    ).evaluate(policy_context)
    parity = OpenPositionLimitPolicy(
        maximum_open_positions=1,
        allow_existing_position=False,
        rejection_reason="Maximum number of open positions has been reached.",
    ).evaluate(policy_context)

    assert execution.approved is True
    assert parity.approved is False
    assert parity.explanation == "Maximum number of open positions has been reached."


def test_trade_planner_orchestrates_ordered_policies_and_aggregates_reasons() -> None:
    policies = TradePolicySet(
        policies=(
            MinimumPricePolicy(Decimal("110")),
            RewardRiskPolicy(Decimal("3")),
        ),
        collect_all_rejections=True,
    )
    planner = TradePlanner(policies=policies)

    plan = planner.plan(
        PortfolioView(),
        intent(),
        target_price=Decimal("110"),
    )

    assert plan.approved is False
    assert plan.risk_code == "MINIMUM_PRICE"
    assert plan.reasons == (
        "Price is below the $110.00 minimum.",
        "Reward/risk 2.00 is below the required 3.00.",
    )
    assert tuple(decision.policy for decision in plan.policy_decisions) == (
        "MinimumPricePolicy",
        "RewardRiskPolicy",
    )


def test_parity_configuration_is_immutable_and_owns_policy_order() -> None:
    config = PolicyParityConfig(
        minimum_price=Decimal("10"),
        minimum_reward_risk=Decimal("2"),
        maximum_daily_loss=Decimal("0.01"),
        maximum_position_size=Decimal("0.12"),
        maximum_portfolio_exposure=Decimal("0.50"),
        maximum_open_positions=5,
    )

    policies = TradePolicySet.preview_parity(config)

    assert tuple(type(policy).__name__ for policy in policies.policies) == (
        "MinimumPricePolicy",
        "RewardRiskPolicy",
        "OpenPositionLimitPolicy",
        "DuplicatePositionPolicy",
        "DuplicateOrderPolicy",
        "DailyLossPolicy",
        "BuyingPowerPolicy",
        "MaximumPositionSizePolicy",
        "PortfolioExposurePolicy",
    )
    assert policies.collect_all_rejections is True
    assert policies.evaluate_when_zero_quantity is True

    with pytest.raises(FrozenInstanceError):
        config.minimum_price = Decimal("1")  # type: ignore[misc]


def test_trade_planner_uses_smallest_policy_quantity_cap() -> None:
    policies = TradePolicySet(
        policies=(
            BuyingPowerPolicy(mode=QuantityLimitMode.CAP),
            MaximumPositionSizePolicy(
                Decimal("0.12"),
                mode=QuantityLimitMode.CAP,
                include_existing_position=False,
            ),
            PortfolioExposurePolicy(
                Decimal("0.50"),
                mode=QuantityLimitMode.CAP,
            ),
        )
    )
    planner = TradePlanner(policies=policies)
    portfolio = PortfolioView(
        equity=Decimal("100000"),
        buying_power=Decimal("50000"),
        invested_value=Decimal("49000"),
    )

    plan = planner.plan(portfolio, intent())

    assert plan.approved is True
    assert plan.sizing_result.quantity == 10
    assert plan.sizing_result.dollar_risk == Decimal("50")
    assert plan.sizing_result.position_value == Decimal("1000")


@pytest.mark.parametrize(
    "factory",
    [
        lambda: MinimumPricePolicy(Decimal("-0.01")),
        lambda: RewardRiskPolicy(Decimal("-0.01")),
        lambda: DailyLossPolicy(Decimal("-0.01")),
        lambda: MaximumPositionSizePolicy(Decimal("1.01")),
        lambda: PortfolioExposurePolicy(Decimal("-0.01")),
        lambda: OpenPositionLimitPolicy(-1),
    ],
)
def test_invalid_policy_configuration_is_rejected(factory: object) -> None:
    with pytest.raises(ValueError):
        factory()  # type: ignore[operator]
