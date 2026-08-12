# ADR-0004: Operational Safety Events and Correlation

- Status: Accepted
- Date: 2026-07-20

## Context

Deterministic preview and manual submission now share planning rules, but their
operational outcomes were observable only through UI messages and broker
responses. Scanner automation must not be migrated until trade decisions can be
reconstructed, rejection causes can be explained, and side effects can be
correlated without importing UI or broker objects into the application core.

## Decision

Volcanoes defines immutable operational events in `volcanoes.events`. Each
event is a frozen, slotted dataclass with an aware UTC timestamp, a non-empty
correlation ID, and a schema containing only immutable deterministic values.
The event model rejects mutable or infrastructure-specific payload objects at
runtime.

The initial vocabulary is:

- `TradePreviewed`
- `TradeRejected`
- `TradeSubmitted`
- `TradeFilled`
- `TradeCancelled`
- `TradeFailed`
- `PlanDriftDetected`
- `PolicyViolation`

Canonical serialization converts timestamps to UTC ISO-8601, decimals to exact
base-10 strings, tuples to arrays, and emits compact JSON with sorted keys. The
same event therefore always produces the same serialized representation.

## Correlation lifecycle

The presentation boundary creates one correlation ID for a Paper Order
lifecycle and passes it into deterministic preview and confirmed submission.
The immutable preview request and result carry that ID. The expected submitted
plan carries the same ID, and the immutable submission request exposes it as
its own correlation ID. `TradeSubmitted` records both the correlation ID and
the broker order ID, which provides the future join from preview to submission,
broker order, and fill without putting a broker object in an event.

```text
TradePreviewed(correlation_id)
        |
        v
TradeSubmitted(correlation_id, broker_order_id)
        |
        v
TradeFilled(correlation_id, broker_order_id)
```

## Publisher boundary

`EventPublisher` is an application-facing interface with one operation:
`publish(DomainEvent)`. `NullEventPublisher` is the default implementation. It
performs no persistence and preserves existing behavior when no operational
adapter is configured.

Application services publish domain events, never audit strings. No event
persistence adapter, message bus, logger adapter, or database schema is added by
this milestone.

## Publication order

- Approved preview: `TradePreviewed`.
- Rejected planned preview: `TradePreviewed`, one configured
  `PolicyViolation` per unique violation, then one `TradeRejected`.
- Invalid request or portfolio: configured `PolicyViolation`, then
  `TradeRejected`.
- Plan drift: `PlanDriftDetected`, configured `PolicyViolation`, then
  `TradeRejected`.
- Successful accepted submission: `TradeSubmitted`.
- Immediately filled submission: `TradeSubmitted`, then `TradeFilled`.
- Broker cancellation response: `TradeCancelled`, configured
  `PolicyViolation`, then `TradeRejected`.
- Broker exception: one `TradeFailed`.

A successful immutable submission command publishes `TradeSubmitted` only
once. A repeated command is represented as its own duplicate-submission policy
violation and rejection and cannot reach the broker.

## Explainability

Every rejection result and rejection event contains:

- the correlation ID;
- the responsible policy or operational guard;
- a human-readable explanation; and
- immutable effective configuration as sorted name/value pairs.

Policy configuration is read from the immutable policy object that produced the
decision. Request validation, portfolio validation, plan consistency, duplicate
submission, execution, and broker acceptance use explicit operational policy
names and configurations.

## Dependency and side-effect boundaries

Events and the publisher port import no Streamlit, root broker, concrete broker,
adapter, scanner, persistence, or analytics modules. Preview and submission
remain broker- and Streamlit-independent. UI and adapters may import the event
port inward.

This milestone does not change broker behavior, execution rules, policies,
sizing formulas, scanner behavior, persistence schemas, or analytics.

## Consequences and deferred work

- Manual preview and submission can be reconstructed by correlation ID.
- Rejections are machine-readable and remain human-explainable.
- The null publisher provides no durability. A durable publisher, delivery
  guarantees, retention policy, and sensitive-data policy require a later ADR.
- Scanner event production and automated-order correlation are intentionally
  deferred until scanner migration.
