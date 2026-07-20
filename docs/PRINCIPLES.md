# EduTraderAI Engineering Principles

These principles govern the design and development of EduTraderAI.

## 1. Capital Preservation Before Profit

The system must prioritize survival, controlled exposure, and downside protection before return maximization.

## 2. Deterministic Execution

Given the same portfolio state, configuration, and trade intent, the execution system should produce the same result.

Randomness must never influence order approval or execution unless it is explicitly introduced for a controlled research experiment.

## 3. AI Recommends; AI Never Executes

Artificial intelligence may:

- analyze,
- rank,
- explain,
- propose,
- and challenge ideas.

Artificial intelligence may not:

- submit orders directly,
- alter broker balances,
- bypass Guardian decisions,
- bypass position sizing,
- or bypass risk management.

## 4. Every Decision Must Be Explainable

The system should preserve enough information to explain:

- what market information was evaluated,
- which strategy generated the signal,
- which trade intent was proposed,
- how position size was calculated,
- which risk rules were applied,
- why execution was accepted or rejected,
- and how the portfolio changed.

## 5. Single Responsibility

Each component should perform one clearly defined role.

Examples:

- Market feeds deliver market data.
- Strategies produce trade intents.
- Position sizing calculates quantity.
- Risk management approves or rejects requests.
- Brokers execute orders.
- Portfolios maintain financial state.
- Ledgers record transactions.
- Backtests orchestrate historical simulations.
- Analytics measure results.

## 6. Immutable Domain Models

Domain values should be immutable whenever practical.

Examples include:

- Bar
- Quote
- TradeIntent
- TradeRequest
- Order
- PositionSizingRequest
- PositionSizingResult
- ExecutionPipelineResult
- BacktestResult

Immutability reduces hidden state, accidental mutation, and debugging complexity.

## 7. No Hidden State

Important state must be visible through explicit objects such as:

- Portfolio
- Ledger
- Feed cursor
- Strategy state
- Broker order history
- Backtest results

Components must not depend on undocumented global state.

## 8. Every Feature Includes Tests

A feature is incomplete until it has:

1. Production code.
2. Focused automated tests.
3. A successful regression run.
4. Clear observable behavior.

## 9. Green Before Merge

No production change should be committed or merged while the regression suite is failing.

## 10. Simple Architecture Beats Clever Architecture

Prefer explicit, understandable components over compressed abstractions or overly generic frameworks.

## 11. Components Must Be Replaceable

Market feeds, strategies, brokers, storage systems, and analytics should be replaceable behind stable interfaces.

## 12. Unexpected Errors Must Remain Visible

Expected domain outcomes may be represented as results or controlled exceptions.

Programming errors must not be silently swallowed.

## 13. Backtests Must Be Reproducible

A backtest must identify:

- market data,
- strategy configuration,
- risk configuration,
- starting portfolio state,
- software version,
- and relevant execution assumptions.

## 14. Historical Data Must Not Leak the Future

Strategies must only receive information available at the simulated point in time.

Future bars, future prices, and future outcomes must never influence a historical decision.

## 15. Live Trading Requires Stronger Controls

Live trading must not begin until the platform has:

- reliable backtests,
- reliable paper trading,
- validated broker integration,
- reconciliation,
- explicit operational limits,
- emergency shutdown controls,
- and comprehensive logging.