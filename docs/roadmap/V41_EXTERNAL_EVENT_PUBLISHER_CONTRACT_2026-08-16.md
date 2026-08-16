# EduTraderAI v4.1 External Event Publisher Contract

Date: 2026-08-16

Backlog item: V41-EP-002 — Define external publisher contract.

Status: Contract requirements defined for technical review; no vendor or adapter selected.

Dependency: V41-EP-001 NullEventPublisher inventory.

## Purpose

Define a vendor-neutral contract for externally observable operational domain events without making event delivery an execution authority or creating a path that can replay a broker effect.

This document changes no runtime wiring and authorizes no network, broker, credential, `state/`, Live, or order action.

## Core principle

**Publishing is observational/integration behavior; durable execution persistence remains the authority for idempotency, ownership, dispatch permission, recovery and reconciliation.**

An event-delivery failure must never cause the corresponding trade/broker operation to be re-executed.

## Contract requirements

### EP-REQ-001 — Stable event identity

Every externally publishable event must carry a deterministic or immutable unique event identity plus correlation identity. Duplicate delivery of the same event identity must be safe.

### EP-REQ-002 — Safe canonical serialization

External payloads must use a versioned canonical schema. Serialization must reject unsupported types and must not include credentials, authorization headers, raw broker payloads, account secrets, private keys, connection strings or unrestricted exception dumps.

### EP-REQ-003 — Explicit capability declaration

A configured publisher must expose whether it is `NULL`, `LOCAL_RECORDING`, or `EXTERNAL_DELIVERY` (or equivalent typed capability). Production/release readiness must not infer external delivery from successful service construction.

### EP-REQ-004 — Typed delivery result

The publisher boundary should distinguish at least:
- accepted locally / no external delivery;
- externally accepted/acknowledged when the adapter can prove it;
- retryable delivery failure;
- permanent delivery failure;
- outcome unknown when the adapter cannot safely determine whether the event left the process.

A `NullEventPublisher` result must never be represented as externally delivered.

### EP-REQ-005 — Event retry only

Retry logic may retry publication of the immutable event identity. It must never invoke or replay the originating preview, submission, dispatch or broker effect.

### EP-REQ-006 — Idempotent external adapters

Where the destination supports an idempotency/deduplication key, use the event identity. Otherwise duplicate delivery must be treated as an expected at-least-once possibility and consumers must be documented accordingly.

### EP-REQ-007 — Bounded backpressure

The adapter must define queue/buffer limits, blocking policy and overload behavior. Event backpressure must not silently hold a broker transaction or durable execution DB transaction open across network publication.

### EP-REQ-008 — Failure isolation

The system must explicitly define which event categories are best-effort and which are required for production readiness. For best-effort operational events, delivery failure must not corrupt execution state. If a release mode requires durable event evidence, readiness must fail explicitly before consequential operation rather than discovering missing observability after the fact.

### EP-REQ-009 — No authority transfer

Possession, receipt or acknowledgement of an operational event cannot grant execution authority, dispatch ownership or recovery permission. Consumers must query/use the appropriate durable execution authority when consequential action is required.

### EP-REQ-010 — Ordering semantics are declared, not assumed

If ordering matters, define the key (for example correlation ID or aggregate ID) and the adapter guarantee. Global ordering must not be assumed unless explicitly provided and tested.

### EP-REQ-011 — Version compatibility

Payload schema version is mandatory. Producers and consumers must define compatible-version behavior and fail safely on unsupported schemas.

### EP-REQ-012 — Redaction before transport

Redaction/safe-field validation occurs before data crosses the external publisher boundary. Adapter logging must use the same safe representation and must not log connection secrets.

### EP-REQ-013 — Observability of the publisher itself

The implementation should expose safe counters/metrics for publish attempts, acknowledged deliveries, retries, permanent failures, unknown outcomes, queue depth/backpressure and Null/default usage. Metrics are operational signals, not durable event evidence.

### EP-REQ-014 — Startup/readiness validation

A deployment that requires external event delivery must fail readiness/configuration when only Null/no-delivery capability is configured. Development/test modes may explicitly allow Null behavior.

### EP-REQ-015 — Shutdown semantics

The adapter must define whether it flushes queued events, the maximum bounded shutdown behavior, and how undelivered events are reported. Shutdown must not claim delivery merely because an event was enqueued locally.

### EP-REQ-016 — Durable outbox is optional but authoritative about delivery handoff only

If reliable post-commit publication is required, a transactional outbox may be added in the same durable transaction as the authoritative application state. The outbox row grants permission to publish an event, not permission to execute a trade. Outbox delivery remains independently idempotent by event identity.

### EP-REQ-017 — Correlation continuity

Event identity, correlation ID and relevant safe aggregate/command identity must remain unchanged across retries and adapter boundaries so operations can reconstruct a timeline without account secrets.

### EP-REQ-018 — Consumer contract

Consumers must be told whether delivery is best-effort, at-most-once, at-least-once or deduplicated-at-least-once. A consumer must not infer missing business state from a missing event unless the declared delivery contract supports that inference.

## Recommended interface shape

The existing `EventPublisher.publish(event) -> None` is sufficient for a Null/simple in-process port but cannot express external delivery outcomes. A future implementation slice should introduce a storage/vendor-neutral result contract rather than overloading exceptions with delivery semantics.

Conceptually:

- input: one immutable safe `DomainEvent`;
- output: typed publish result containing event ID, capability, status, retry classification and safe reason code;
- no broker object, credentials or raw transport response in the application contract.

Exact source-code types are intentionally deferred to an implementation slice.

## Failure matrix

| Failure | Required behavior |
|---|---|
| Null publisher configured | Explicit no-external-delivery capability |
| Serialization/redaction fails | Do not transmit; return permanent/safe validation failure |
| Destination unavailable before send | Retry event only according to policy |
| Timeout after possible send | Mark event delivery outcome unknown; retry only if destination/idempotency contract makes it safe |
| Duplicate publish call | Same immutable event identity; no business operation replay |
| Queue full | Apply declared bounded backpressure/drop/fail policy and surface metrics/result |
| Adapter crashes | Execution authority remains durable and unaffected |
| Process restarts | Event recovery depends on declared adapter/outbox contract, not volatile assumptions |
| Consumer receives duplicate | Consumer handles same event ID idempotently where required |
| Unsupported schema version | Consumer/adapter rejects safely and observably |

## Production readiness

A production/release mode that claims external observability should prove:

1. non-Null external capability is configured;
2. safe serialization/redaction tests pass;
3. event identity survives retries;
4. adapter failure cannot replay execution;
5. backpressure/failure metrics are visible;
6. any required outbox/recovery path is tested across restart;
7. destination credentials are obtained only through the approved secret mechanism and never enter event payload/evidence.

## V41-EP-002 acceptance mapping

- External publisher boundary defined: yes, vendor-neutral.
- Delivery semantics defined: yes.
- Retry/idempotency defined: event-only, identity-bound.
- Failure/backpressure behavior required: yes.
- Redaction/versioning/correlation defined: yes.
- Production Null-vs-external capability distinction defined: yes.
- Execution-authority boundary protected: yes.
- Vendor/transport implementation: intentionally not selected in this requirement slice.

## Next implementation boundary

A later authorized slice may add typed publisher capability/result contracts and deterministic adapters/tests. Any concrete external transport, credentials or network validation is a separate external-integration step and must not be bundled with broker execution changes.