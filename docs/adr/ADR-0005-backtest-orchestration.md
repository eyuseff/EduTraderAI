# ADR-0005: Backtest Engine Performs Orchestration Only

- Status: Accepted
- Date: 2026-07-20

## Context

A backtest engine could calculate indicators, generate signals, size trades, apply risk rules, execute orders, maintain accounting, and calculate analytics.

Combining those responsibilities would duplicate existing components and make historical results harder to trust.

## Decision

BacktestEngine will only:

1. consume bars from MarketFeed,
2. pass each bar to Strategy,
3. receive TradeIntent or None,
4. call ExecutionPipeline,
5. count executed and rejected trades,
6. return BacktestResult.

BacktestEngine will not implement:

- strategy rules,
- position sizing,
- portfolio risk,
- order creation,
- broker execution,
- accounting,
- or performance analytics.

## Consequences

Positive:

- historical and future live workflows can share execution logic,
- each layer remains independently testable,
- BacktestEngine remains small and understandable.

Negative:

- advanced backtesting may require additional orchestration objects,
- portfolio valuation snapshots will need a separate design.