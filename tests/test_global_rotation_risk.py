from decimal import Decimal

from global_rotation.risk import (
    PaperPortfolioContext,
    PaperRiskPolicy,
    blocked_paper_preview,
    size_paper_position,
)


def test_qualification_phase_caps_notional_below_twenty_dollar_risk_budget():
    result = size_paper_position(
        symbol="TEST",
        entry_usd=Decimal("100"),
        stop_usd=Decimal("95"),
        target_usd=Decimal("110"),
        fractional_enabled=True,
        portfolio=PaperPortfolioContext(
            equity_usd=Decimal("10000"),
            buying_power_usd=Decimal("10000"),
        ),
    )

    assert result.risk_budget_usd == Decimal("20.00")
    assert result.quantity == Decimal("2.000000")
    assert result.position_value_usd == Decimal("200.00")
    assert result.planned_loss_usd == Decimal("10.00")
    assert result.target_profit_usd == Decimal("20.00")
    assert result.blockers == ()


def test_mature_phase_uses_twenty_dollar_loss_cap_when_it_is_binding():
    result = size_paper_position(
        symbol="TEST",
        entry_usd=Decimal("100"),
        stop_usd=Decimal("95"),
        target_usd=Decimal("110"),
        fractional_enabled=False,
        portfolio=PaperPortfolioContext(
            equity_usd=Decimal("10000"),
            buying_power_usd=Decimal("10000"),
            qualification_phase=False,
        ),
    )

    assert result.quantity == Decimal("4")
    assert result.position_value_usd == Decimal("400.00")
    assert result.planned_loss_usd == Decimal("20.00")
    assert result.target_profit_usd == Decimal("40.00")


def test_quarter_percent_equity_limit_can_bind_below_twenty_dollars():
    result = size_paper_position(
        symbol="TEST",
        entry_usd=Decimal("50"),
        stop_usd=Decimal("45"),
        target_usd=Decimal("60"),
        fractional_enabled=True,
        portfolio=PaperPortfolioContext(
            equity_usd=Decimal("4000"),
            buying_power_usd=Decimal("4000"),
            qualification_phase=False,
        ),
    )

    assert result.risk_budget_usd == Decimal("10.00")
    assert result.quantity == Decimal("2.000000")
    assert result.planned_loss_usd == Decimal("10.00")


def test_duplicate_symbol_returns_zero_size_and_explicit_blocker():
    result = size_paper_position(
        symbol="test",
        entry_usd=Decimal("100"),
        stop_usd=Decimal("95"),
        target_usd=Decimal("110"),
        fractional_enabled=True,
        portfolio=PaperPortfolioContext(
            equity_usd=Decimal("10000"),
            buying_power_usd=Decimal("10000"),
            open_symbols=("TEST",),
        ),
        policy=PaperRiskPolicy(),
    )

    assert result.quantity == Decimal("0")
    assert result.position_value_usd == Decimal("0.00")
    assert result.blockers == ("Duplicate symbol is not permitted.",)


def test_blocked_preview_never_invents_a_quantity():
    result = blocked_paper_preview(
        portfolio=PaperPortfolioContext(
            equity_usd=Decimal("10000"),
            buying_power_usd=Decimal("10000"),
        )
    )

    assert result.risk_budget_usd == Decimal("20.00")
    assert result.quantity == Decimal("0")
    assert result.position_value_usd == Decimal("0.00")
    assert result.planned_loss_usd == Decimal("0.00")


def test_daily_one_percent_loss_lock_blocks_new_preview():
    result = size_paper_position(
        symbol="TEST",
        entry_usd=Decimal("100"),
        stop_usd=Decimal("95"),
        target_usd=Decimal("110"),
        fractional_enabled=True,
        portfolio=PaperPortfolioContext(
            equity_usd=Decimal("10000"),
            buying_power_usd=Decimal("10000"),
            realized_loss_today_usd=Decimal("100"),
        ),
    )

    assert result.quantity == Decimal("0")
    assert result.blockers == ("Daily 1% portfolio loss lock is active.",)


def test_exhausted_exposure_returns_explicit_zero_size_blocker():
    result = size_paper_position(
        symbol="TEST",
        entry_usd=Decimal("100"),
        stop_usd=Decimal("95"),
        target_usd=Decimal("110"),
        fractional_enabled=True,
        portfolio=PaperPortfolioContext(
            equity_usd=Decimal("10000"),
            buying_power_usd=Decimal("10000"),
            current_exposure_usd=Decimal("5000"),
        ),
    )

    assert result.quantity == Decimal("0")
    assert result.blockers == ("No Paper buying or exposure capacity remains.",)
