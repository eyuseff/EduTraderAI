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
    current_exposure_usd: Decimal = ZERO
    realized_loss_today_usd: Decimal = ZERO
    open_symbols: tuple[str, ...] = ()
    qualification_phase: bool = True

    def __post_init__(self) -> None:
        if self.equity_usd <= ZERO:
            raise ValueError("Portfolio equity must be greater than zero.")
        if self.buying_power_usd < ZERO:
            raise ValueError("Buying power cannot be negative.")
        if self.current_exposure_usd < ZERO:
            raise ValueError("Current exposure cannot be negative.")
        if self.realized_loss_today_usd < ZERO:
            raise ValueError("Today's realized loss cannot be negative.")


@dataclass(frozen=True)
class PaperSizeResult:
    risk_budget_usd: Decimal
    quantity: Decimal
    position_value_usd: Decimal
    planned_loss_usd: Decimal
    target_profit_usd: Decimal
    blockers: tuple[str, ...]


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
        position_value_usd=ZERO.quantize(Decimal("0.01")),
        planned_loss_usd=ZERO.quantize(Decimal("0.01")),
        target_profit_usd=ZERO.quantize(Decimal("0.01")),
        blockers=(),
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
    blockers: list[str] = []
    normalized_open = {item.strip().upper() for item in portfolio.open_symbols}
    normalized_symbol = symbol.strip().upper()
    max_positions = (
        selected.qualification_max_open_positions
        if portfolio.qualification_phase
        else selected.mature_max_open_positions
    )
    if normalized_symbol in normalized_open:
        blockers.append("Duplicate symbol is not permitted.")
    elif len(normalized_open) >= max_positions:
        blockers.append("Maximum open positions reached.")
    if (
        portfolio.realized_loss_today_usd
        >= portfolio.equity_usd * selected.maximum_daily_loss_fraction
    ):
        blockers.append("Daily 1% portfolio loss lock is active.")

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
    if portfolio.qualification_phase:
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
        position_value_usd=position_value.quantize(Decimal("0.01")),
        planned_loss_usd=planned_loss.quantize(Decimal("0.01")),
        target_profit_usd=target_profit.quantize(Decimal("0.01")),
        blockers=tuple(blockers),
    )
