"""Risk manager."""

from volcanoes.domain import TradeRequest
from volcanoes.portfolio import Portfolio
from volcanoes.risk.exceptions import RiskViolation
from volcanoes.risk.risk_config import RiskConfig


class RiskManager:
    """Central risk validation engine."""

    def __init__(self, config: RiskConfig | None = None):
        self.config = config or RiskConfig()

    def validate_trade(
        self,
        portfolio: Portfolio,
        trade: TradeRequest,
    ) -> bool:
        """
        Validate whether a trade can be executed.

        Returns:
            True if the trade is allowed.

        Raises:
            RiskViolation if any rule is violated.
        """

        if trade.cost > portfolio.buying_power:
            raise RiskViolation(
                code="INSUFFICIENT_BUYING_POWER",
                message="Trade exceeds available buying power.",
            )

        return True
