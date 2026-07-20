# ADR-0001: Layered Trading Architecture

- Status: Accepted
- Date: 2026-07-20

## Context

Trading applications often combine market data, strategy decisions, risk, execution, and accounting inside a single workflow.

That approach makes testing difficult and creates hidden dependencies.

## Decision

EduTraderAI will separate the following responsibilities:

- Domain
- Market
- Strategy
- Position Sizing
- Risk
- Execution
- Broker
- Portfolio
- Ledger
- Backtest
- Analytics
- Artificial Intelligence

Components communicate through explicit domain objects and narrow interfaces.

## Alternatives Considered

### Single Trading Engine

One central object could manage all trading responsibilities.

Rejected because it would become difficult to test, replace, and explain.

### Strategy-Owned Execution

Strategies could submit orders directly.

Rejected because strategies would become coupled to brokers, cash balances, and risk controls.

## Consequences

Positive:

- components are independently testable,
- brokers and feeds are replaceable,
- risk remains independent,
- strategy code remains small,
- AI can be introduced without changing execution.

Negative:

- more modules and classes,
- additional interfaces,
- some orchestration code is required.