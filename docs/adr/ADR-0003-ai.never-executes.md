# ADR-0003: Artificial Intelligence Never Executes Orders

- Status: Accepted
- Date: 2026-07-20

## Context

AI can assist with market interpretation and recommendation generation, but its output may be uncertain, inconsistent, or difficult to validate.

Direct AI access to a broker would create unacceptable operational and financial risk.

## Decision

Artificial intelligence may produce:

- candidate opportunities,
- rankings,
- explanations,
- confidence estimates,
- and proposed TradeIntent data.

AI may not:

- submit an order,
- call a broker,
- change portfolio state,
- change account balances,
- override Guardian,
- bypass position sizing,
- or bypass risk validation.

## Required Flow

```text
AI
 |
 v
Structured Recommendation
 |
 v
Guardian
 |
 v
TradeIntent
 |
 v
Deterministic ExecutionPipeline