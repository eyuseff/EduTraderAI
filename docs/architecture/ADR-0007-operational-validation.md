# ADR-0007: Operational Validation Is Observational and Process-Local

- Status: Accepted for v4.0.0-rc1
- Date: 2026-07-20

## Context

The deterministic manual and scanner paths are unified and covered by release
acceptance tests, but a stable release also needs sustained paper-operation
evidence. That evidence must not become another input to planning or execution,
and the RC must not acquire durable infrastructure or distributed coordination.

## Decision

Operational metrics are an application-layer observation port. Services,
supervisor orchestration, scanner orchestration, and an event-publisher adapter
receive the port explicitly. Metrics never approve, reject, size, construct, or
submit a trade.

The RC recorder is thread-safe and process-local. Snapshots are immutable.
Durations use a monotonic clock. The recorder stores aggregates only, so memory
does not grow with observations.

Metric names are a closed vocabulary. Labels containing symbols, order IDs,
correlation IDs, account identifiers, or other high-cardinality values are not
supported. Detailed lifecycle identity remains in immutable domain events, not
metrics.

Instrumentation is fail-open: a counter or timing failure cannot change or block
the trading outcome. Such failures increment a separate
`instrumentation_failures` counter through an isolated recorder. An unresolved
failure blocks stable-release validation because evidence may be incomplete, not
because execution behavior changed.

The development dashboard consumes only `PlatformHealthReport`,
`OperationalMetricsSnapshot`, and optional verification metadata. It does not
inspect services, brokers, planners, or mutable supervisor internals. Production
navigation does not expose the page.

Validation export is manual and local. Its typed payload includes version, UTC
timestamp, health, feature flags, metrics, verification metadata, and known
limitations. It cannot accept raw brokers, credentials, mutable infrastructure,
or complete account identifiers. Export files live in the ignored `build/`
boundary and are not durable event storage.

Stable acceptance uses zero-tolerance outcome criteria for incorrect quantities,
silent drift, duplicates, correlation loss, lock leaks, deadlocks, and unexplained
crashes. The observation window records elapsed time and meaningful workflow
counts without requiring unsafe or arbitrary trade volume.

## Consequences

- Metrics and supervisor state reset on restart and are not comparable across
  processes unless an operator exports and reconciles each session.
- `NullEventPublisher` remains the RC event destination; event attempts are
  observable but events are not retained.
- The stable decision must explicitly disposition process-local coordination and
  the null publisher.
- Durable metrics/events, broker reconciliation, restart-safe state, and
  distributed locks remain deferred.
