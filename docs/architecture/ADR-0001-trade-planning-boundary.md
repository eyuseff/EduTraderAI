# ADR-0001: Trade Planning Boundary

- Status: Accepted
- Date: 2026-07-20

## Context

EduTraderAI is migrating toward a ports-and-adapters architecture with the
following dependency direction:

```text
Streamlit UI / CLI
        |
        v
Application services
        |
        v
Volcanoes deterministic core
        ^
        |
External adapters
```

Before this decision, sizing, risk validation, and broker submission were
coordinated inside `ExecutionPipeline`. A user interface that needed a trade
preview could either duplicate the sizing and risk sequence or construct an
execution object with a broker even though previewing must not execute
anything. Both choices would weaken the deterministic boundary.

The active Streamlit application also belongs to an older architectural
generation. It currently depends on root-level `broker`, `trading`, `engine`,
and `scanner_engine` packages rather than on the new application-services
boundary.

## Decision

### TradePlanner owns pure trade planning

`TradePlanner` owns the deterministic sequence shared by preview and
execution:

1. create a `PositionSizingRequest`;
2. calculate a `PositionSizingResult`;
3. reject a zero-quantity result;
4. build a `TradeRequest`;
5. evaluate portfolio risk; and
6. return an immutable `TradePlan`.

Trade planning must not submit an order, mutate a portfolio, open a database,
write an audit record, or otherwise cause an external side effect.

`ExecutionPipeline` delegates all sizing and risk planning to `TradePlanner`.
It remains responsible for converting an approved plan into an order and
submitting that order to its broker. This keeps one implementation of sizing
and risk planning while preserving execution's existing broker-facing
behavior.

### Preview and execution are separate operations

Preview is a query. It calculates and explains a possible trade without
changing system state. Execution is a command. It may submit an order and
change broker, portfolio, ledger, audit, and persistence state.

The operations therefore have separate entry points:

- `PreviewTradeService.preview(...)` returns an immutable,
  presentation-neutral result and has no broker or persistence dependency.
- `ExecutionPipeline.execute(...)` plans first and may submit only an approved
  plan through a broker.

This separation makes repeated previews deterministic and safe during
Streamlit reruns. It also prevents a future CLI, API, or UI from acquiring
execution authority merely because it can request a preview.

### RiskManager depends on RiskPortfolioView

Risk validation needs a small read-only view of account state: equity, buying
power, invested value, realized profit and loss, position count, and position
lookup. It does not need ownership of the mutable `Portfolio` implementation.

`RiskManager` therefore depends on the structural `RiskPortfolioView` port
rather than on concrete `Portfolio`.

The native `Portfolio` satisfies the port without modification. Future broker
snapshot adapters may also satisfy it without constructing a false or partial
domain portfolio. The port exposes read-only properties so immutable account
snapshots remain valid implementations.

### Application services remain infrastructure-independent

Application services coordinate use cases and translate between immutable
application contracts and deterministic core types. They must not import or
instantiate:

- Streamlit;
- root-level broker or trading implementations;
- Alpaca or the JSON simulator;
- adapter modules;
- SQLite or database repositories; or
- other persistence implementations.

The Preview Trade service is subject to an additional narrow rule: it may not
import any database, persistence, or broker module. Its complete input is a
`RiskPortfolioView` plus a `PreviewTradeRequest`.

The in-memory `volcanoes.execution.paper_broker` remains part of the existing
deterministic execution/lifecycle implementation. It is not categorized as an
external adapter by this ADR. External broker adapters are the root-level
`broker.*` implementations and future modules beneath an `adapters` boundary.

### Dependency direction is inward only

UI and adapters may import application services and Volcanoes core modules.
Application and core modules must never import the UI or adapters.

The enforced direction is:

```text
UI / adapters -> application services -> deterministic core
```

Imports in the reverse direction are architecture violations. Relative imports
inside Volcanoes remain valid; for example, `from .broker import Broker` inside
`volcanoes.execution` resolves to `volcanoes.execution.broker`, not to the
root-level `broker` adapter package.

## Automated Enforcement

`tests/test_architecture_dependencies.py` parses Python imports with the
standard-library `ast` module and enforces the following rules:

1. `volcanoes/domain`, `risk`, `sizing`, `execution`, `portfolio`, and
   `analytics` cannot import Streamlit, root `broker`, root `trading`, root
   `scanner_engine`, root `engine`, or any `adapters` package.
2. `volcanoes/application` cannot import Streamlit, root `broker`, root
   `trading`, or any `adapters` package.
3. `volcanoes/application/services/preview_trade.py` cannot import database,
   persistence, broker, Streamlit, or adapter modules.
4. UI and adapter modules are intentionally allowed to import inward from
   `volcanoes`.

The checker resolves relative imports before matching prohibited module
prefixes and tests the resolver itself to prevent false positives from
similarly named modules.

## Current Migration Status

Completed:

- `RiskPortfolioView` is the risk engine's account-state boundary.
- `TradePlanner` and immutable `TradePlan` isolate pure planning.
- `ExecutionPipeline` delegates sizing and risk planning.
- `PreviewTradeService` exposes immutable request and result contracts.
- Preview planning has no broker or persistence dependency.

Intentionally deferred:

- wiring `app.py` to `PreviewTradeService`;
- adding the active-broker snapshot adapter;
- adapting Alpaca Paper to Volcanoes ports;
- migrating the automated scanner and `EduTraderBrain`;
- reconciling root and Volcanoes risk-policy differences;
- moving Streamlit submission to the deterministic execution boundary; and
- integrating Preview Trade with SQLite or other persistence.

These integrations must be introduced through outer adapters or composition
roots. They must not add outward dependencies to application services or the
deterministic core.

## Consequences

Positive:

- preview is repeatable and side-effect free;
- preview and execution share one planning implementation;
- risk logic can consume native or adapted read-only portfolio state;
- UI and infrastructure can evolve without entering the deterministic core;
- dependency direction is executable policy rather than documentation alone.

Trade-offs:

- application contracts add mapping code at system boundaries;
- external broker state will require a dedicated adapter;
- current legacy integrations remain temporarily parallel to the new path;
- future boundary changes must update both this decision and its enforcement
  tests.
