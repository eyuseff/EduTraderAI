"""Immutable domain models for the Global Rotation Paper scanner."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from market.regime import MarketRegime


@dataclass(frozen=True)
class RegionConfig:
    """A market region and the benchmark used to gate long signals."""

    code: str
    benchmark_symbol: str
    currency: str

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("Region code is required.")
        if not self.benchmark_symbol.strip():
            raise ValueError("Region benchmark symbol is required.")
        if len(self.currency.strip()) != 3:
            raise ValueError("Currency must be a three-letter code.")


@dataclass(frozen=True)
class GlobalInstrument:
    """Provider-neutral metadata for one listed stock."""

    symbol: str
    region: str
    currency: str
    fx_to_usd: Decimal = Decimal("1")
    etoro_eligible: bool | None = None
    fractional_enabled: bool = False
    underlying_buy_x1: bool = True
    is_cfd: bool = False
    is_247: bool = False

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("Instrument symbol is required.")
        if not self.region.strip():
            raise ValueError("Instrument region is required.")
        if len(self.currency.strip()) != 3:
            raise ValueError("Currency must be a three-letter code.")
        if self.fx_to_usd <= Decimal("0"):
            raise ValueError("FX conversion rate must be greater than zero.")


@dataclass(frozen=True)
class RotationPolicy:
    """Signal and target rules for the first Global Rotation milestone."""

    edu_min_score: int = 80
    volcano_min_score: int = 80
    minimum_price_usd: Decimal = Decimal("10")
    minimum_average_volume: Decimal = Decimal("1000000")
    maximum_daily_move_pct: Decimal = Decimal("4")
    maximum_gap_pct: Decimal = Decimal("4")
    minimum_target_pct: Decimal = Decimal("0.06")
    stretch_target_pct: Decimal = Decimal("0.15")
    maximum_stop_pct: Decimal = Decimal("0.075")
    resistance_lookback: int = 60
    max_candidates: int = 10

    def __post_init__(self) -> None:
        if not 0 <= self.edu_min_score <= 100:
            raise ValueError("EduTrader score must be between 0 and 100.")
        if not 0 <= self.volcano_min_score <= 100:
            raise ValueError("Volcanes score must be between 0 and 100.")
        if self.minimum_price_usd <= Decimal("0"):
            raise ValueError("Minimum price must be greater than zero.")
        if self.minimum_average_volume <= Decimal("0"):
            raise ValueError("Minimum average volume must be greater than zero.")
        if self.maximum_daily_move_pct <= Decimal("0"):
            raise ValueError("Maximum daily move percentage must be positive.")
        if self.maximum_gap_pct <= Decimal("0"):
            raise ValueError("Maximum gap percentage must be positive.")
        if self.minimum_target_pct <= Decimal("0"):
            raise ValueError("Minimum target percentage must be positive.")
        if self.stretch_target_pct < self.minimum_target_pct:
            raise ValueError("Stretch target cannot be below the minimum target.")
        if self.maximum_stop_pct <= Decimal("0"):
            raise ValueError("Maximum stop percentage must be positive.")
        if self.resistance_lookback < 2:
            raise ValueError("Resistance lookback must be at least two sessions.")
        if self.max_candidates < 1:
            raise ValueError("At least one candidate must be permitted.")


@dataclass(frozen=True)
class ScanRejection:
    symbol: str
    region: str
    reason: str


@dataclass(frozen=True)
class GlobalRotationCandidate:
    """Explainable output from both scanners plus the Paper sizing preview."""

    symbol: str
    region: str
    currency: str
    regime: MarketRegime
    edu_score: int
    volcano_score: int
    guardian_approved: bool
    guardian_reason: str
    entry_local: Decimal
    entry_usd: Decimal
    rsi14: Decimal
    atr14_local: Decimal
    gap_pct: Decimal
    daily_change_pct: Decimal
    relative_volume: Decimal
    stop_local: Decimal
    stop_pct: Decimal
    target_local: Decimal
    target_pct: Decimal
    stretch_target_local: Decimal
    resistance_local: Decimal
    reward_risk_to_resistance: Decimal
    quantity: Decimal
    position_value_usd: Decimal
    planned_loss_usd: Decimal
    target_profit_usd: Decimal
    category: str
    blockers: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class GlobalRotationResult:
    candidates: tuple[GlobalRotationCandidate, ...]
    rejected: tuple[ScanRejection, ...]
    regimes: dict[str, MarketRegime]
    scanned: int
    valid: int
