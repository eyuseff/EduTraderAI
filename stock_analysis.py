"""
EduTrader AI
Stock Analysis Model

Provides a strongly typed replacement for the loose stock dictionaries
used throughout the application.
"""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class StockAnalysis:
    """Complete technical and trading analysis for one stock."""

    # Market data
    symbol: str
    price: float
    rsi: float
    ema20: float
    ema50: float
    sma200: float
    macd: float
    signal: float
    atr: float

    # Strategy results
    score: int = 0
    recommendation: str = "HOLD"
    confidence: int = 0
    stars: str = "☆☆☆☆☆"
    reasons: list[str] = field(default_factory=list)

    # Risk plan
    entry: float = 0.0
    stop_loss: float = 0.0
    target: float = 0.0
    risk_amount: float = 0.0
    reward_amount: float = 0.0
    risk_percent: float = 0.0
    reward_percent: float = 0.0
    risk_reward: float = 0.0

    # Position sizing
    account_balance: float = 0.0
    portfolio_risk_percent: float = 0.0
    maximum_loss: float = 0.0
    risk_per_share: float = 0.0
    shares: int = 0
    capital_required: float = 0.0
    estimated_profit: float = 0.0
    actual_loss: float = 0.0
    actual_risk_percent: float = 0.0

    # Trade eligibility
    trade_eligible: bool = False
    trade_status: str = "NO TRADE"

    @classmethod
    def from_scanner_dict(
        cls,
        stock: dict[str, Any],
    ) -> "StockAnalysis":
        """
        Create a typed stock model from the dictionary
        currently returned by MarketScanner.
        """

        required_fields = (
            "Symbol",
            "Price",
            "RSI",
            "EMA20",
            "EMA50",
            "SMA200",
            "MACD",
            "Signal",
            "ATR",
        )

        missing_fields = [
            field_name
            for field_name in required_fields
            if field_name not in stock
        ]

        if missing_fields:
            missing = ", ".join(missing_fields)
            raise ValueError(
                f"Scanner result is missing required fields: {missing}"
            )

        return cls(
            symbol=str(stock["Symbol"]),
            price=float(stock["Price"]),
            rsi=float(stock["RSI"]),
            ema20=float(stock["EMA20"]),
            ema50=float(stock["EMA50"]),
            sma200=float(stock["SMA200"]),
            macd=float(stock["MACD"]),
            signal=float(stock["Signal"]),
            atr=float(stock["ATR"]),
        )

    def to_engine_dict(self) -> dict[str, Any]:
        """
        Convert the model to the dictionary format expected by
        the existing strategy, risk, analysis, and report modules.

        This compatibility method lets us refactor gradually.
        """

        return {
            "Symbol": self.symbol,
            "Price": self.price,
            "RSI": self.rsi,
            "EMA20": self.ema20,
            "EMA50": self.ema50,
            "SMA200": self.sma200,
            "MACD": self.macd,
            "Signal": self.signal,
            "ATR": self.atr,
            "Score": self.score,
            "Recommendation": self.recommendation,
            "Confidence": self.confidence,
            "Stars": self.stars,
            "Reasons": self.reasons,
            "Entry": self.entry,
            "StopLoss": self.stop_loss,
            "Target": self.target,
            "RiskAmount": self.risk_amount,
            "RewardAmount": self.reward_amount,
            "RiskPercent": self.risk_percent,
            "RewardPercent": self.reward_percent,
            "RiskReward": self.risk_reward,
            "AccountBalance": self.account_balance,
            "PortfolioRiskPercent": self.portfolio_risk_percent,
            "MaximumLoss": self.maximum_loss,
            "RiskPerShare": self.risk_per_share,
            "Shares": self.shares,
            "CapitalRequired": self.capital_required,
            "EstimatedProfit": self.estimated_profit,
            "ActualLoss": self.actual_loss,
            "ActualRiskPercent": self.actual_risk_percent,
            "TradeEligible": self.trade_eligible,
            "TradeStatus": self.trade_status,
        }

    def to_python_dict(self) -> dict[str, Any]:
        """Return the model using its native Python field names."""

        return asdict(self)