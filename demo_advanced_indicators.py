#!/usr/bin/env python3
"""
Demo: advanced technical indicators for AI EMERS research layer.

Run from the repo root:
    PYTHONPATH=. python3 demo_advanced_indicators.py

This script is read-only research. It never connects to brokers or
submits orders.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from volcanoes.market.advanced_indicators import (
    add_advanced_indicators,
    interpret_advanced,
    last_advanced_snapshot,
)


def make_demo_series(n: int = 260, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-01-01", periods=n)
    close = 150 + np.cumsum(rng.normal(0.08, 1.4, n))
    high = close + rng.uniform(0.3, 2.0, n)
    low = close - rng.uniform(0.3, 2.0, n)
    open_ = close + rng.normal(0, 0.4, n)
    volume = rng.integers(200_000, 800_000, n).astype(float)
    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=dates,
    )


def main() -> None:
    print("=" * 60)
    print("AI EMERS — Advanced Technical Indicators Demo")
    print("(Research / advisory layer only — no execution)")
    print("=" * 60)

    raw = make_demo_series()
    enriched = add_advanced_indicators(raw)
    snap = last_advanced_snapshot(enriched)
    labels = interpret_advanced(snap)

    last = enriched.iloc[-1]
    print(f"\nLast bar date : {enriched.index[-1].date()}")
    print(f"Close         : {last['Close']:.2f}")
    print()

    print("--- Classic (already in project) style values ---")
    print(f"  BB Mid / Upper / Lower : {snap.bb_mid:.2f} / {snap.bb_upper:.2f} / {snap.bb_lower:.2f}")
    print(f"  %B / Bandwidth         : {snap.bb_percent_b:.3f} / {snap.bb_bandwidth:.3f}")
    print(f"  ADX / +DI / -DI        : {snap.adx:.1f} / {snap.plus_di:.1f} / {snap.minus_di:.1f}")
    print(f"  Stochastic %K / %D     : {snap.stoch_k:.1f} / {snap.stoch_d:.1f}")
    print(f"  MFI                    : {snap.mfi:.1f}")
    print(f"  OBV                    : {snap.obv:,.0f}")
    print(f"  Supertrend / Dir       : {snap.supertrend:.2f} / {snap.supertrend_direction:+d}")

    print("\n--- Human-readable interpretation (for advisory UI) ---")
    for key, value in labels.items():
        print(f"  {key:18s}: {value}")

    print("\n--- Sample of last 5 rows (key columns) ---")
    cols = ["Close", "BB_PERCENT_B", "ADX", "STOCH_K", "MFI", "SUPERTREND_DIR"]
    print(enriched[cols].tail().round(2).to_string())
    print()


if __name__ == "__main__":
    main()
