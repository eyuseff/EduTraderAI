# ADR-0005: Execution Supervisor

- Status: Accepted
- Date: 2026-07-20

## Context

Deterministic preview, submission, and operational events are available for the
manual Paper Order path. Autonomous producers require an additional boundary
before they may request execution. Trading rules alone do not prevent repeated
commands, concurrent workflows for one symbol, rapid re-entry, or reuse of an
idempotency key with different parameters.

These are orchestration concerns. They must not be added to `TradePlanner`, risk
policies, sizing, brokers, or `ExecutionPipeline`.

## Decision

`ExecutionSupervisor` is an application-level coordinator around the existing
`PreviewTradeService` and `SubmitTradeService`. It accepts immutable canonical
`ExecutionRequest` objects from either `HUMAN` or `AUTOMATION` sources. It never
calculates risk, sizes a position, builds an order, or calls a broker.

The dependency flow is:

```text
Human or automation
        |
        v
ExecutionSupervisor
        |
        +--> PreviewTradeService --> TradePlanner
        |
        +--> SubmitTradeService --> ExecutionPipeline --> Broker port
```

The preview and submission services supplied to a supervisor must share the
exact same `TradePlanner` instance. The supervisor converts the preview result
into the immutable expected-plan contract used by submission, preserving the
existing preview/submission drift invariant.

## Immutable contracts

- `ExecutionRequest` contains canonical trade inputs, source, correlation ID,
  idempotency key, and optional caller-provided market state.
- `ExecutionDecision` explains an admission, skip, or abort with a code, policy,
  configuration, and correlation ID.
- `ExecutionResult` contains the decision and, when invoked, immutable preview
  and submission results.

The deterministic request fingerprint consists only of normalized symbol,
side, entry, stop, target, and execution mode. It excludes source, idempotency
key, and correlation ID. Including execution mode prevents a successful
preview-only request from blocking a later submission of the same trade.

## Orchestration policies

- `DuplicateExecutionPolicy` rejects a fingerprint that is currently active or
  has already submitted successfully in this supervisor instance.
- `ConcurrentSymbolPolicy` permits at most one active workflow for a symbol.
  Contending requests are rejected rather than queued, guaranteeing that
  workflows for one symbol never overlap.
- `CooldownPolicy` blocks a distinct request for the configured period after a
  successful submission for that symbol. Rejections and failures do not start a
  cooldown.
- `MarketStatePolicy` is a stub. Enforcement is disabled by default. When
  configured to require an open market, it evaluates only the immutable state
  supplied by the caller; no market-data adapter is introduced here.

These policies make admission decisions only. They do not approve trades under
risk rules and do not alter quantity or prices.

## Idempotency

An idempotency key is admitted once at a time. After a workflow completes, an
identical request with the same key replays the original immutable result and
does not invoke either service again. Reusing the key for a different trade
fingerprint is rejected as `IDEMPOTENCY_CONFLICT`.

Pre-admission skips such as cooldown or market-state rejection are not stored as
completed idempotent executions. The same request may therefore be retried when
the orchestration condition changes.

## Supervisor events

Supervisor events extend the operational `DomainEvent` model:

- `ExecutionStarted`
- `ExecutionSkipped`
- `ExecutionCompleted`
- `ExecutionAborted`

They carry the execution source, symbol, idempotency key, timestamp, and
correlation ID. Skips and aborts also carry policy, explanation, and immutable
configuration.

An accepted lifecycle publishes `ExecutionStarted`, allows the underlying
services to publish their operational events, then publishes either
`ExecutionCompleted` or `ExecutionAborted`. Admission-policy rejection and
idempotent replay publish one `ExecutionSkipped`. A replay never republishes
`TradeSubmitted` or `ExecutionCompleted`.

## Correlation

The supervisor-provided correlation ID is copied into the preview request,
expected submission plan, submission request, application-service results, and
all supervisor events. The resulting stream can reconstruct one supervised
lifecycle without carrying broker or UI objects.

## State and concurrency

Supervisor state is protected by an in-process lock and includes active
symbols, in-flight keys and fingerprints, successful fingerprints, completed
idempotency results, and last successful execution timestamps. This is
process-local and intentionally has no persistence dependency.

## Consequences and deferred work

- Human and future automated execution producers can use one supervisory API.
- Duplicate, concurrent, cooldown, and idempotency behavior is deterministic and
  explainable.
- Restart-safe idempotency and distributed symbol locking require a future
  persistence or coordination adapter.
- Authoritative market-state integration remains deferred.
- Scanner integration is defined separately by ADR-0006.
- Broker implementations, persistence, trading policies, planning, sizing,
  execution pipeline, scanner, and analytics remain unchanged.
