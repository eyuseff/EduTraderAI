# ADR-0002: Deterministic Trading Core

- Status: Accepted
- Date: 2026-07-20

## Context

Market data providers and artificial intelligence systems may produce variable or nondeterministic outputs.

Trading execution and portfolio accounting require predictable behavior.

## Decision

All components from TradeIntent through portfolio and ledger updates will remain deterministic.

This includes:

- validation,
- position sizing,
- risk checks,
- order construction,
- broker simulation,
- portfolio updates,
- ledger recording,
- and backtest orchestration.

External or nondeterministic outputs must be converted into explicit captured inputs before entering the deterministic core.

## Consequences

Positive:

- identical inputs reproduce identical outcomes,
- failures are easier to diagnose,
- historical simulations are auditable,
- AI recommendations can be evaluated independently.

Negative:

- nondeterministic optimization must be isolated,
- random simulations require explicit seeds and metadata.