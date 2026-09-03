"""Paper-only position sizing for the Global Rotation strategy."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

ZERO = Decimal("0")


@dataclass(frozen=True)
class PaperRiskPolicy:
    """Canonical limits agreed for the Global Rotation qualification phase."""

    maximum_loss_usd: Decimal = Decimal("20")
    maximum_risk_fraction: Decimal = Decimal("0.0025")
    maximum_daily_loss_fraction: Decimal = Decimal("0.01")
    maximum_position_fraction: Decimal = Decimal("0.12")
    maximum_exposure_fraction: Decimal = Decimal("0.50")
    qualification_position_cap_usd: Decimal = Decimal("200")
    qualification_max_open_positions: int = 2
    mature_max_open_positions: int = 5

    def __post_init__(self) -> None:
        decimal_fields = (
            ("Maximum loss", self.maximum_loss_usd),
            ("Maximum risk fraction", self.maximum_risk_fraction),
            ("Maximum daily loss fraction", self.maximum_daily_loss_fraction),
            ("Maximum position fraction", self.maximum_position_fraction),
            ("Maximum exposure fraction", self.maximum_exposure_fraction),
            ("Qualification position cap", self.qualification_position_cap_usd),
        )
        for name, value in decimal_fields:
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{name} must be a finite Decimal.")
        for name, limit in (
            ("Qualification position limit", self.qualification_max_open_positions),
            ("Mature position limit", self.mature_max_open_positions),
        ):
            if type(limit) is not int:
                raise ValueError(f"{name} must be an integer.")
        if self.maximum_loss_usd <= ZERO:
            raise ValueError("Maximum loss must be greater than zero.")
        for name, value in (
            ("Maximum risk fraction", self.maximum_risk_fraction),
            ("Maximum daily loss fraction", self.maximum_daily_loss_fraction),
            ("Maximum position fraction", self.maximum_position_fraction),
            ("Maximum exposure fraction", self.maximum_exposure_fraction),
        ):
            if not ZERO < value <= Decimal("1"):
                raise ValueError(f"{name} must be greater than zero and at most one.")
        if self.qualification_position_cap_usd <= ZERO:
            raise ValueError("Qualification position cap must be greater than zero.")
        if self.qualification_max_open_positions < 1:
            raise ValueError("Qualification phase must permit at least one position.")
        if self.mature_max_open_positions < self.qualification_max_open_positions:
            raise ValueError(
                "Mature position limit cannot be below the qualification limit."
            )


@dataclass(frozen=True)
class PaperPortfolioContext:
    equity_usd: Decimal
    buying_power_usd: Decimal
    current_exposure_usd: Decimal | None = None
    realized_loss_today_usd: Decimal | None = None
    open_symbols: tuple[str, ...] | None = None
    qualification_phase: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.equity_usd, Decimal):
            raise ValueError("Portfolio equity must be a Decimal.")
        if not isinstance(self.buying_power_usd, Decimal):
            raise ValueError("Buying power must be a Decimal.")
        if not self.equity_usd.is_finite():
            raise ValueError("Portfolio equity must be finite.")
        if not self.buying_power_usd.is_finite():
            raise ValueError("Buying power must be finite.")
        if self.equity_usd <= ZERO:
            raise ValueError("Portfolio equity must be greater than zero.")
        if self.buying_power_usd < ZERO:
            raise ValueError("Buying power cannot be negative.")
        if self.current_exposure_usd is not None:
            if not isinstance(self.current_exposure_usd, Decimal):
                raise ValueError("Current exposure must be a Decimal or null.")
            if not self.current_exposure_usd.is_finite():
                raise ValueError("Current exposure must be finite.")
        if self.current_exposure_usd is not None and self.current_exposure_usd < ZERO:
            raise ValueError("Current exposure cannot be negative.")
        if self.realized_loss_today_usd is not None:
            if not isinstance(self.realized_loss_today_usd, Decimal):
                raise ValueError("Today's realized loss must be a Decimal or null.")
            if not self.realized_loss_today_usd.is_finite():
                raise ValueError("Today's realized loss must be finite.")
        if (
            self.realized_loss_today_usd is not None
            and self.realized_loss_today_usd < ZERO
        ):
            raise ValueError("Today's realized loss cannot be negative.")
        if self.open_symbols is not None:
            if not isinstance(self.open_symbols, tuple) or any(
                not isinstance(symbol, str) or not symbol.strip()
                for symbol in self.open_symbols
            ):
                raise ValueError("Open symbols must be a tuple of non-empty strings.")
            normalized = [symbol.strip().upper() for symbol in self.open_symbols]
            if len(normalized) != len(set(normalized)):
                raise ValueError("Open symbols must not contain duplicates.")
        if (
            self.qualification_phase is not None
            and type(self.qualification_phase) is not bool
        ):
            raise ValueError("Qualification phase must be true, false, or null.")


@dataclass(frozen=True)
class PaperSizeResult:
    risk_budget_usd: Decimal
    quantity: Decimal
    reserved_position_value_usd: Decimal
    position_value_usd: Decimal
    planned_loss_usd: Decimal
    target_profit_usd: Decimal
    blockers: tuple[str, ...]


def _portfolio_truth_blockers(
    portfolio: PaperPortfolioContext,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if portfolio.current_exposure_usd is None:
        blockers.append("Current Paper exposure is unverified.")
    if portfolio.realized_loss_today_usd is None:
        blockers.append("Today's realized Paper loss is unverified.")
    if portfolio.open_symbols is None:
        blockers.append("Open Paper positions are unverified.")
    if portfolio.qualification_phase is None:
        blockers.append("Paper qualification phase is unverified.")
    return tuple(blockers)


def blocked_paper_preview(
    *,
    portfolio: PaperPortfolioContext,
    policy: PaperRiskPolicy | None = None,
) -> PaperSizeResult:
    """Return an explicitly empty preview when upstream gates are not satisfied."""

    selected = policy or PaperRiskPolicy()
    risk_budget = min(
        selected.maximum_loss_usd,
        portfolio.equity_usd * selected.maximum_risk_fraction,
    )
    return PaperSizeResult(
        risk_budget_usd=risk_budget.quantize(Decimal("0.01")),
        quantity=ZERO,
        reserved_position_value_usd=ZERO,
        position_value_usd=ZERO.quantize(Decimal("0.01")),
        planned_loss_usd=ZERO.quantize(Decimal("0.01")),
        target_profit_usd=ZERO.quantize(Decimal("0.01")),
        blockers=_portfolio_truth_blockers(portfolio),
    )


def size_paper_position(
    *,
    symbol: str,
    entry_usd: Decimal,
    stop_usd: Decimal,
    target_usd: Decimal,
    fractional_enabled: bool,
    portfolio: PaperPortfolioContext,
    policy: PaperRiskPolicy | None = None,
) -> PaperSizeResult:
    """Return a deterministic preview size; this function never submits an order."""

    selected = policy or PaperRiskPolicy()
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("Symbol is required.")
    for name, value in (
        ("Entry price", entry_usd),
        ("Stop price", stop_usd),
        ("Target price", target_usd),
    ):
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ValueError(f"{name} must be a finite Decimal.")
    if type(fractional_enabled) is not bool:
        raise ValueError("Fractional capability must be true or false.")
    if entry_usd <= ZERO:
        raise ValueError("Entry price must be greater than zero.")
    if not ZERO <= stop_usd < entry_usd:
        raise ValueError("Stop must be non-negative and below entry.")
    if target_usd <= entry_usd:
        raise ValueError("Target must be above entry.")

    risk_budget = min(
        selected.maximum_loss_usd,
        portfolio.equity_usd * selected.maximum_risk_fraction,
    )
    blockers = list(_portfolio_truth_blockers(portfolio))
    normalized_open = {item.strip().upper() for item in (portfolio.open_symbols or ())}
    normalized_symbol = symbol.strip().upper()
    max_positions = (
        selected.qualification_max_open_positions
        if portfolio.qualification_phase is not False
        else selected.mature_max_open_positions
    )
    if normalized_symbol in normalized_open:
        blockers.append("Duplicate symbol is not permitted.")
    elif len(normalized_open) >= max_positions:
        blockers.append("Maximum open positions reached.")
    if portfolio.realized_loss_today_usd is not None and (
        portfolio.realized_loss_today_usd
        >= portfolio.equity_usd * selected.maximum_daily_loss_fraction
    ):
        blockers.append("Daily 1% portfolio loss lock is active.")

    exposure_capacity = ZERO
    if portfolio.current_exposure_usd is not None:
        exposure_capacity = max(
            ZERO,
            portfolio.equity_usd * selected.maximum_exposure_fraction
            - portfolio.current_exposure_usd,
        )
    position_cap = min(
        portfolio.equity_usd * selected.maximum_position_fraction,
        portfolio.buying_power_usd,
        exposure_capacity,
    )
    if portfolio.qualification_phase is not False:
        position_cap = min(position_cap, selected.qualification_position_cap_usd)
    if position_cap <= ZERO:
        blockers.append("No Paper buying or exposure capacity remains.")

    risk_per_unit = entry_usd - stop_usd
    quantity_by_risk = risk_budget / risk_per_unit
    quantity_by_notional = position_cap / entry_usd
    quantity = min(quantity_by_risk, quantity_by_notional)
    if fractional_enabled:
        quantity = quantity.quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
    else:
        quantity = quantity.to_integral_value(rounding=ROUND_DOWN)

    if quantity <= ZERO and not blockers:
        blockers.append("Position cap cannot fund the minimum tradable quantity.")

    if blockers or quantity <= ZERO:
        quantity = ZERO
    position_value = quantity * entry_usd
    planned_loss = quantity * risk_per_unit
    target_profit = quantity * (target_usd - entry_usd)
    return PaperSizeResult(
        risk_budget_usd=risk_budget.quantize(Decimal("0.01")),
        quantity=quantity,
        reserved_position_value_usd=position_value,
        position_value_usd=position_value.quantize(Decimal("0.01")),
        planned_loss_usd=planned_loss.quantize(Decimal("0.01")),
        target_profit_usd=target_profit.quantize(Decimal("0.01")),
        blockers=tuple(blockers),
    )
