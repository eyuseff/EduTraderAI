# ADR-0008: Global Rotation Paper Research Core

- Status: Proposed
- Date: 2026-08-29

## Context

The Global Rotation concept searches liquid listed shares across regional
markets for short-horizon long candidates. It combines the existing EduTrader
trend score with Volcanes momentum confirmation and then applies liquidity,
regime, resistance, eligibility, and portfolio-risk gates.

The concept must remain research and Paper-only. A screen result is a candidate
for human review, not a recommendation or an executable order. The existing
execution architecture also requires scanner code to remain free of broker side
effects and reserves all execution authority for the supervisor boundary.

## Decision

Add a provider-neutral `global_rotation` research package with three explicit
boundaries:

1. `GlobalRotationEngine` receives already-loaded daily histories, normalized
   instrument metadata, regional benchmarks, and a Paper portfolio snapshot.
2. Existing EduTrader scoring remains the source of the Edu score. Volcanes
   momentum scoring is extracted into a pure function shared by the current
   Explorer and the new engine; the resulting candidate is then evaluated by
   the existing `Guardian` with its minimum score set to 80.
3. Paper sizing produces a preview only after every signal, market, resistance,
   and eToro eligibility gate passes. It never submits or constructs an order.

The first slice applies these rules:

- long-only listed stocks;
- EduTrader score at least 80 and Volcanes score at least 80 for `preparar`;
- regional benchmark regime must be tradeable;
- USD-equivalent price at least USD 10 and 20-session mean volume at least one
  million shares;
- price above SMA200, no opening gap or daily move beyond 4%, and enough prior
  60-session resistance space for the adaptive target;
- target is the greater of 6% or 2R, capped by the 15% stretch threshold;
- stop distance cannot exceed 7.5% for the 5–20 session mandate;
- eToro availability must be positively verified as BUY x1 on the underlying
  share, with neither CFD nor `.24-7` routing;
- Paper risk budget is `min(USD 20, 0.25% of equity)`;
- a 1% realized daily-loss lock blocks every new Paper quantity when the
  portfolio snapshot proves that threshold has been reached;
- qualification phase allows at most two open positions and USD 200 notional
  per new position; the mature ceiling is five positions;
- total exposure is capped at 50% and a single name at 12% of equity;
- duplicate symbols are rejected and whole-share rounding is used when
  fractional trading is unavailable.

Only blocker-free candidates receive a quantity. Missing eToro eligibility,
portfolio data, or any other admission gate returns a zero-quantity preview.

## Candidate states

| State | Meaning |
|---|---|
| `preparar` | Both scanners and every Paper-preview gate pass; manual confirmation is still required. |
| `esperar` | Both scanners pass but at least one market, eligibility, resistance, or risk gate blocks sizing. |
| `vigilar` | Only one scanner passes. |
| `no perseguir` | The opening gap or daily move exceeds 4%, or the minimum 2R target would exceed 15%. |

These states are research-priority labels, not investment recommendations.

## Safety and compatibility

- No network, broker, credential, persistence, clock, random, or filesystem
  dependency exists inside the engine.
- No existing scanner execution, supervisor, Paper broker, or Live path is
  modified.
- Regional market regimes reuse `classify_market`; its default remains SPY so
  existing callers are unchanged.
- The existing Volcanes Explorer retains its external behavior while delegating
  its score calculation to the extracted pure function.

## Deferred work

This slice does not claim to scan 8,000 securities in production. The following
remain separate reviewed milestones:

- licensed or public market-data adapters, exchange calendars, symbol/master
  normalization, corporate actions, FX snapshots, and survivorship-safe
  historical universes;
- deterministic 8,000-name batching, caching, rate-limit handling, stale-data
  detection, and data-quality quarantine;
- read-only eToro Demo capability discovery and per-account fractional/BUY x1
  eligibility verification;
- earnings calendar, fundamentals, valuation, sector concentration, and manual
  event-risk review;
- historical walk-forward validation including fees, FX, slippage, gaps,
  delistings, and false-discovery control;
- daily operator UI, durable run comparison, audit export, and notification;
- composition with the execution supervisor after Paper qualification. Live
  trading is not authorized by this ADR.

## Consequences

The repository gains a deterministic and testable strategy core without
widening the broker execution surface. A future data adapter can feed thousands
of instruments into the same engine, but no quantity is produced until both the
research thesis and account-specific eligibility are verified.

## First read-only operator slice

The initial operator composition adds:

- a versioned 64-stock starter spanning the United States, Canada, euro-area
  exchanges, Japan, Australia, and Hong Kong;
- a batched Yahoo Finance research adapter capped at 500 symbols, explicitly
  unsuitable for the final 8,000-name production universe;
- OHLCV completeness and consistency quarantine, regional benchmark-session
  alignment, and daily FX conversion;
- a deterministic run id and JSON/CSV audit representation;
- a `Global Rotation Paper` Streamlit button that has no order-submission path;
- a CLI that refuses to run without an explicit portfolio snapshot.

The starter universe deliberately records eToro eligibility and BUY x1 status
as unverified. Therefore it can rank candidates but cannot create a non-zero
Paper quantity until an authenticated read-only capability source updates those
fields.
