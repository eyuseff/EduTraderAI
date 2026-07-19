from market.regime import classify_market


def test_bullish_regime_is_tradeable():
    regime = classify_market(500, 480, 450, 18)
    assert regime.tradeable is True
    assert regime.label == "Bullish"


def test_risk_off_regime_blocks_trading():
    regime = classify_market(400, 430, 450, 35)
    assert regime.tradeable is False
