# Global Rotation Paper Roadmap

## Objective

Build a daily, international, long-only research workflow that can reduce a
large liquid-stock universe to a small set of explainable Paper candidates. The
mandate is 5–20 sessions, with a normal 6–10% target, strong 10–15% target, at
least 2:1 reward/risk, and no more than USD 20 planned loss per position.

Screen outputs are research candidates. They are not guaranteed profits, and a
high number of small positions does not remove correlation, gap, liquidity,
currency, or multiple-testing risk.

## Delivery slices

| Slice | Deliverable | Status | Exit gate |
|---|---|---|---|
| 1. Deterministic core | Regional regimes, EduTrader + Volcanes scoring, resistance checks, adaptive targets, Paper sizing | Implemented in isolated module | Unit tests and architecture review |
| 2. Universe and data | Stable ~8,000-name security master, exchange calendars, daily OHLCV, FX, corporate actions, delisting history | In progress: versioned 64-stock starter and research reader implemented; authoritative master pending | Completeness, freshness, and survivorship QA |
| 3. eToro Read adapter | Demo + Read authentication, public availability, account eligibility, fractional support, BUY x1 underlying verification | Blocked by authenticated read access | Zero writes; capability evidence per symbol |
| 4. Event/fundamental overlay | Earnings windows, recent results, valuation, balance-sheet and sector checks | Pending | Source-backed blocker and freshness rules |
| 5. Backtest and calibration | Walk-forward tests by region/regime with costs, FX, slippage and gaps | Pending | Pre-declared acceptance thresholds; no look-ahead |
| 6. Daily operator surface | Run button, ranked funnel, changes since prior run, audit export and manual confirmation | In progress: read-only button and JSON/CSV audit output implemented | Reproducible run and zero broker writes |
| 7. Paper qualification | Supervisor-composed previews and tightly controlled Paper submissions | Pending | Existing Paper qualification and rollback gates |

## Daily funnel target

1. Start from the versioned security master, not from an unbounded claim of
   “millions of stocks.”
2. Quarantine stale, incomplete, suspended, duplicated, OTC, leveraged, CFD, and
   `.24-7` instruments.
3. Gate each region with its benchmark and exchange session.
4. Run EduTrader and Volcanes independently.
5. Review gaps, SMA200, earnings, fundamentals, valuation, resistance space,
   currency, and concentration.
6. Surface only blocker-free candidates for a Paper quantity.
7. Require explicit human confirmation before any future Paper submission.

## Canonical risk limits

- Risk per position: `min(USD 20, 0.25% of equity)`.
- Daily lock: 1% of equity.
- Qualification: maximum two positions and USD 200 initial notional per name.
- Mature operation: maximum five positions.
- Maximum total exposure: 50% of equity.
- Maximum single-name exposure: 12% of equity.
- Minimum reward/risk: 2:1.
- Long-only, no leverage, no CFD, no short, no duplicate symbol.

The engine enforces the daily lock only when the injected portfolio snapshot
contains broker-truth realized loss. The execution supervisor remains the
authoritative gate and must independently recheck it before any future Paper
submission.
