from decimal import Decimal

import pytest

from global_rotation.risk import (
    PaperPortfolioContext,
    PaperRiskPolicy,
    blocked_paper_preview,
    size_paper_position,
)


def _portfolio(**overrides) -> PaperPortfolioContext:
    values = {
        "equity_usd": Decimal("10000"),
        "buying_power_usd": Decimal("10000"),
        "current_exposure_usd": Decimal("0"),
        "realized_loss_today_usd": Decimal("0"),
        "open_symbols": (),
        "qualification_phase": True,
    }
    values.update(overrides)
    return PaperPortfolioContext(**values)


def test_qualification_phase_caps_notional_below_twenty_dollar_risk_budget():
    result = size_paper_position(
        symbol="TEST",
        entry_usd=Decimal("100"),
        stop_usd=Decimal("95"),
        target_usd=Decimal("110"),
        fractional_enabled=True,
        portfolio=_portfolio(),
    )

    assert result.risk_budget_usd == Decimal("20.00")
    assert result.quantity == Decimal("2.000000")
    assert result.reserved_position_value_usd == Decimal("200.000000")
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
        portfolio=_portfolio(qualification_phase=False),
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
        portfolio=_portfolio(
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
        portfolio=_portfolio(open_symbols=("TEST",)),
        policy=PaperRiskPolicy(),
    )

    assert result.quantity == Decimal("0")
    assert result.position_value_usd == Decimal("0.00")
    assert result.blockers == ("Duplicate symbol is not permitted.",)


def test_blocked_preview_never_invents_a_quantity():
    result = blocked_paper_preview(portfolio=_portfolio())

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
        portfolio=_portfolio(realized_loss_today_usd=Decimal("100")),
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
        portfolio=_portfolio(current_exposure_usd=Decimal("5000")),
    )

    assert result.quantity == Decimal("0")
    assert result.blockers == ("No Paper buying or exposure capacity remains.",)


def test_missing_portfolio_truth_returns_zero_with_explicit_blockers():
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

    assert result.quantity == Decimal("0")
    assert set(result.blockers) == {
        "Current Paper exposure is unverified.",
        "Today's realized Paper loss is unverified.",
        "Open Paper positions are unverified.",
        "Paper qualification phase is unverified.",
        "No Paper buying or exposure capacity remains.",
    }


def test_portfolio_context_rejects_false_like_string_boolean():
    try:
        _portfolio(qualification_phase="false")
    except ValueError as exc:
        assert "Qualification phase must be true, false, or null" in str(exc)
    else:
        raise AssertionError("String booleans must not cross the risk boundary.")


@pytest.mark.parametrize(
    "overrides",
    [
        {"equity_usd": Decimal("Infinity")},
        {"buying_power_usd": Decimal("NaN")},
        {"current_exposure_usd": Decimal("Infinity")},
        {"realized_loss_today_usd": Decimal("NaN")},
    ],
)
def test_portfolio_context_rejects_non_finite_values(overrides):
    with pytest.raises(ValueError, match="finite"):
        _portfolio(**overrides)


def test_risk_policy_rejects_non_finite_values():
    with pytest.raises(ValueError, match="finite Decimal"):
        PaperRiskPolicy(maximum_loss_usd=Decimal("Infinity"))


@pytest.mark.parametrize("value", [2.5, True, "2"])
def test_risk_policy_rejects_non_integer_position_limits(value):
    with pytest.raises(ValueError, match="must be an integer"):
        PaperRiskPolicy(qualification_max_open_positions=value)
