"""Risk configuration."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RiskConfig:
    """Immutable risk configuration."""

    max_risk_per_trade: Decimal = Decimal("0.01")
    max_daily_loss: Decimal = Decimal("0.03")
    max_portfolio_exposure: Decimal = Decimal("0.80")
    max_position_size: Decimal = Decimal("0.20")
    max_open_positions: int = 10
