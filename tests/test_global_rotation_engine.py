from decimal import Decimal

import pandas as pd

from global_rotation import (
    GlobalInstrument,
    GlobalRotationEngine,
    PaperPortfolioContext,
    RegionConfig,
)


def _constructive_history(*, resistance_space: bool = True) -> pd.DataFrame:
    price = 80.0
    closes: list[float] = []
    for index in range(240):
        price += (0.8, 0.8, -0.8)[index % 3]
        closes.append(price)
    frame = pd.DataFrame(
        {
            "Open": closes,
            "High": [value + 0.5 for value in closes],
            "Low": [value - 0.5 for value in closes],
            "Close": closes,
            "Volume": [2_000_000.0] * len(closes),
        }
    )
    if resistance_space:
        frame.loc[len(frame) - 30, "High"] = closes[-1] * 1.12
    return frame


def _history_with_opening_gap() -> pd.DataFrame:
    frame = _constructive_history()
    frame.loc[len(frame) - 1, "Open"] = frame["Close"].iloc[-2] * 1.05
    return frame


def _portfolio() -> PaperPortfolioContext:
    return PaperPortfolioContext(
        equity_usd=Decimal("10000"),
        buying_power_usd=Decimal("10000"),
    )


def test_global_engine_requires_both_scanners_and_produces_paper_preview():
    region = RegionConfig(code="US", benchmark_symbol="SPY", currency="USD")
    engine = GlobalRotationEngine(regions=[region])
    result = engine.scan(
        instruments=[
            GlobalInstrument(
                symbol="TEST",
                region="US",
                currency="USD",
                etoro_eligible=True,
                fractional_enabled=True,
            )
        ],
        histories={"SPY": _constructive_history(), "TEST": _constructive_history()},
        portfolio=_portfolio(),
    )

    assert result.scanned == 1
    assert result.valid == 1
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.edu_score >= 80
    assert candidate.volcano_score >= 80
    assert candidate.guardian_approved is True
    assert "Guardian risk rules passed" in candidate.guardian_reason
    assert candidate.regime.tradeable is True
    assert "SPY" in candidate.regime.reasons[0]
    assert candidate.category == "preparar"
    assert candidate.target_pct == Decimal("6.00")
    assert candidate.position_value_usd == Decimal("200.00")
    assert candidate.planned_loss_usd <= Decimal("20.00")
    assert candidate.target_profit_usd > candidate.planned_loss_usd * Decimal("2")


def test_unverified_etoro_eligibility_blocks_prepare_without_inventing_execution():
    engine = GlobalRotationEngine(
        regions=[RegionConfig(code="US", benchmark_symbol="SPY", currency="USD")]
    )
    result = engine.scan(
        instruments=[GlobalInstrument(symbol="TEST", region="US", currency="USD")],
        histories={"SPY": _constructive_history(), "TEST": _constructive_history()},
        portfolio=_portfolio(),
    )

    candidate = result.candidates[0]
    assert candidate.category == "esperar"
    assert "eToro eligibility is unverified." in candidate.blockers
    assert candidate.quantity == Decimal("0")
    assert candidate.position_value_usd == Decimal("0.00")


def test_missing_resistance_space_prevents_prepare():
    engine = GlobalRotationEngine(
        regions=[RegionConfig(code="US", benchmark_symbol="SPY", currency="USD")]
    )
    result = engine.scan(
        instruments=[
            GlobalInstrument(
                symbol="TEST",
                region="US",
                currency="USD",
                etoro_eligible=True,
                fractional_enabled=True,
            )
        ],
        histories={
            "SPY": _constructive_history(),
            "TEST": _constructive_history(resistance_space=False),
        },
        portfolio=_portfolio(),
    )

    candidate = result.candidates[0]
    assert candidate.category == "esperar"
    assert (
        "Prior 60-session resistance does not provide 2R target space."
        in candidate.blockers
    )
    assert candidate.quantity == Decimal("0")


def test_region_specific_benchmark_is_named_in_regime_explanation():
    engine = GlobalRotationEngine(
        regions=[RegionConfig(code="JP", benchmark_symbol="1306.T", currency="JPY")]
    )
    result = engine.scan(
        instruments=[
            GlobalInstrument(
                symbol="TEST.T",
                region="JP",
                currency="JPY",
                fx_to_usd=Decimal("0.0068"),
                etoro_eligible=True,
                fractional_enabled=True,
            )
        ],
        histories={
            "1306.T": _constructive_history(),
            "TEST.T": _constructive_history(),
        },
        portfolio=_portfolio(),
    )

    assert "1306.T" in result.regimes["JP"].reasons[0]
    assert result.candidates[0].region == "JP"
    assert "USD-equivalent price is below the minimum." in result.candidates[0].blockers


def test_opening_gap_above_four_percent_is_not_pursued_or_sized():
    engine = GlobalRotationEngine(
        regions=[RegionConfig(code="US", benchmark_symbol="SPY", currency="USD")]
    )
    result = engine.scan(
        instruments=[
            GlobalInstrument(
                symbol="TEST",
                region="US",
                currency="USD",
                etoro_eligible=True,
                fractional_enabled=True,
            )
        ],
        histories={"SPY": _constructive_history(), "TEST": _history_with_opening_gap()},
        portfolio=_portfolio(),
    )

    candidate = result.candidates[0]
    assert candidate.gap_pct == Decimal("5.00")
    assert candidate.category == "no perseguir"
    assert candidate.quantity == Decimal("0")
    assert "Opening gap exceeds the 4% review limit." in candidate.blockers
