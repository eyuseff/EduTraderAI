"""Shared deterministic composition for the Paper Order use cases."""

from __future__ import annotations

from decimal import Decimal
from typing import cast

from trading.risk_manager import RiskLimits, TradeProposal
from volcanoes.application.services import PreviewTradeRequest
from volcanoes.domain import TradeSide
from volcanoes.events import new_correlation_id
from volcanoes.execution.trade_planner import TradePlanner
from volcanoes.risk import (
    PolicyParityConfig,
    RiskConfig,
    RiskManager,
    TradePolicySet,
)


def build_paper_order_planner(limits: RiskLimits) -> TradePlanner:
    """Build the one policy-parity planner used by preview and submission."""

    return TradePlanner(
        risk_manager=RiskManager(_to_risk_config(limits)),
        policies=_to_policy_set(limits),
    )


def to_preview_request(
    proposal: TradeProposal,
    *,
    correlation_id: str | None = None,
) -> PreviewTradeRequest:
    """Translate a legacy UI proposal into canonical application inputs."""

    try:
        side = TradeSide(proposal.side.strip().upper())
    except ValueError:
        side = cast(TradeSide, proposal.side)

    return PreviewTradeRequest(
        symbol=proposal.symbol,
        side=side,
        entry_price=Decimal(str(proposal.entry_price)),
        stop_price=Decimal(str(proposal.stop_price)),
        target_price=Decimal(str(proposal.target_price)),
        correlation_id=correlation_id or new_correlation_id(),
    )


def _to_risk_config(limits: RiskLimits) -> RiskConfig:
    percent = Decimal("100")
    return RiskConfig(
        max_risk_per_trade=(Decimal(str(limits.risk_per_trade_pct)) / percent),
        max_daily_loss=(Decimal(str(limits.max_daily_loss_pct)) / percent),
        max_portfolio_exposure=(Decimal(str(limits.max_total_exposure_pct)) / percent),
        max_position_size=(Decimal(str(limits.max_single_position_pct)) / percent),
        max_open_positions=limits.max_open_positions,
    )


def _to_policy_set(limits: RiskLimits) -> TradePolicySet:
    percent = Decimal("100")
    return TradePolicySet.preview_parity(
        PolicyParityConfig(
            minimum_price=Decimal(str(limits.minimum_price)),
            minimum_reward_risk=Decimal(str(limits.minimum_reward_risk)),
            maximum_daily_loss=(Decimal(str(limits.max_daily_loss_pct)) / percent),
            maximum_position_size=(
                Decimal(str(limits.max_single_position_pct)) / percent
            ),
            maximum_portfolio_exposure=(
                Decimal(str(limits.max_total_exposure_pct)) / percent
            ),
            maximum_open_positions=limits.max_open_positions,
        )
    )
