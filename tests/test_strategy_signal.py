from strategies.trend_momentum import score_candidate


def test_high_quality_candidate_scores_well():
    signal = score_candidate(
        symbol="TEST", close=120, sma20=115, sma50=100, rsi14=60,
        atr14=3, average_volume=2_000_000, daily_change_pct=1.2,
    )
    assert signal.score >= 80
    assert signal.stop_price < signal.entry_price < signal.target_price
