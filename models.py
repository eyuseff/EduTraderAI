"""
EduTrader AI
Shared Data Models
"""

from dataclasses import dataclass, field


@dataclass
class Stock:

    symbol: str

    price: float

    rsi: float

    ema20: float
    ema50: float

    sma200: float

    macd: float
    signal: float

    atr: float

    recommendation: str = ""

    confidence: int = 0

    score: int = 0

    reasons: list[str] = field(default_factory=list)


@dataclass
class RiskResult:

    entry: float

    stop: float

    target: float

    risk: float

    reward: float

    risk_reward: float