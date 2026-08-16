# EduTraderAI v4.1 NullEventPublisher Inventory

Date: 2026-08-16

Backlog item: V41-EP-001 — Inventory `NullEventPublisher` usage.

Status: Production execution call sites directly verified; GitHub code-search indexing reported incomplete during this audit, so future revalidation should repeat a repository-wide indexed search when available.

## Purpose

Document where operational domain events can currently be intentionally discarded, how that affects diagnostics/release evidence, and which guarantees must not depend on event delivery.

This is a read-only architecture inventory. No event adapter, runtime wiring, broker access, credentials, `state/`, Live behavior, or order action is changed.

## Publisher contract

`volcanoes/events/publisher.py` defines:

- `EventPublisher.publish(event)` as the operational domain-event publishing port; and
- `NullEventPublisher`, whose `publish` method validates that the value is a `DomainEvent` and then produces no side effect.

The class docstring describes `NullEventPublisher` as the default publisher until a persistence adapter is introduced.

## Directly verified production call sites

| Component | Code path | Default behavior | Events/diagnostics affected | Risk / implication |
|---|---|---|---|---|
| Preview trade | `volcanoes/application/services/preview_trade.py` — `PreviewTradeService.__init__` | `event_publisher or NullEventPublisher()` | Preview/rejection operational events emitted by the service are discarded if no publisher is injected | Preview correctness is unaffected, but external audit/telemetry cannot assume event delivery |
| Submit trade | `volcanoes/application/services/submit_trade.py` — `SubmitTradeService.__init__` | `event_publisher or NullEventPublisher()` | Submission, failure, cancellation/fill, plan-drift and rejection events can be discarded when defaulted | Consequential execution safety must remain in synchronous/durable execution state, not event receipt |
| Execution supervisor | `volcanoes/application/supervisor/supervisor.py` — `ExecutionSupervisor.__init__` | `event_publisher or NullEventPublisher()` | Execution started/completed/skipped/aborted and policy-violation style supervisory events can be discarded | Idempotency, symbol exclusion and admission decisions must not depend on event consumers |

## Verified characteristics

### EP-INV-001 — Null publishing is explicit no-delivery behavior

`NullEventPublisher` is not a buffer, durable log, retry queue, outbox or in-memory recording sink. A valid event is accepted and discarded.

### EP-INV-002 — Services remain synchronous and deterministic without an external publisher

The reviewed service constructors make the publisher optional and substitute `NullEventPublisher`. Therefore core application behavior is intentionally capable of operating without an external event destination.

### EP-INV-003 — Event delivery is not execution authority

The durable Paper execution stack separately persists commands, idempotency, aggregate transitions, dispatch control/claims/authorization/resolution and reconciliation. These records — not operational event delivery — are the appropriate authority for replay, recovery and consequential ownership.

### EP-INV-004 — Operational visibility can be materially reduced

When a default Null publisher is active, event consumers cannot observe lifecycle events through the event port. An operator or release process must rely on synchronous results, durable execution evidence, metrics, logs or another configured publisher rather than assuming those events were delivered.

### EP-INV-005 — Metrics and events are separate paths

`PreviewTradeService`, `SubmitTradeService`, and `ExecutionSupervisor` also accept operational metrics independently of the event publisher. Null event delivery does not itself prove metrics are unavailable, and metrics must not be represented as durable event history.

## Event categories visible in the verified surfaces

The reviewed production services import/use operational event models covering categories such as:

- trade preview and policy explanation/rejection;
- trade submitted;
- trade cancelled;
- trade failed;
- trade filled;
- plan drift detected;
- execution started;
- execution completed;
- execution skipped;
- execution aborted;
- policy violation.

This inventory does not claim that the event model is limited to those categories; it identifies the operational categories exposed by the verified Null-default execution surfaces.

## Release-evidence implications

### What NullEventPublisher cannot prove

A release artifact must not treat successful return from `NullEventPublisher.publish` as proof that:

- an event was persisted;
- an event left the process;
- an event reached a queue/topic/collector;
- an operator received an alert;
- a consumer processed the event;
- replay after restart is possible.

### What remains independently evidentiary

Where available, release evidence should use authoritative artifacts such as:

- durable execution command/idempotency/transition records;
- dispatch claim, authorization and resolution records;
- reconciliation evidence/history;
- deterministic result fingerprints;
- CI verification artifacts;
- explicitly configured external publisher delivery evidence once such a contract is implemented.

## Risk map

### EP-R1 — Silent observability gap

A composition root can omit a publisher and still run successfully. If operations assume events are externally visible, the system can appear healthy while lifecycle notifications are being discarded.

Mitigation requirement for EP-002: production/release modes that require external observability must expose publisher capability/configuration explicitly instead of inferring it from service success.

### EP-R2 — False audit assumption

An emitted domain-event object is not equivalent to a durable audit record when the configured publisher is Null.

Mitigation requirement for EP-002: distinguish `accepted_by_application`, `persisted/delivered`, and `consumed/acknowledged` semantics.

### EP-R3 — Coupling safety to delivery

Making execution permission or recovery depend on an event consumer would be unsafe because current defaults allow no delivery.

Mitigation requirement for EP-002: external publishing remains observational/integration behavior; execution authority stays durable and local to the execution persistence model.

### EP-R4 — Retry ambiguity

A future publisher that fails after an uncertain external send cannot simply cause the trade/execution operation to be replayed.

Mitigation requirement for EP-002: publisher retry/idempotency must use event identity and never replay the broker effect.

### EP-R5 — Secret leakage

Operational events may cross process/system boundaries in a future adapter.

Mitigation requirement for EP-002: external publisher contracts must use safe serialized event schemas and reject credentials/raw broker payloads/account secrets.

## Search/inventory limitation

During this audit, GitHub's code-search endpoint returned `incomplete_results=true` and no indexed matches even though direct file reads prove `NullEventPublisher` imports/usages in the reviewed services. For that reason this document distinguishes **directly verified production call sites** from a claim of search-index completeness.

The production execution surfaces most relevant to the backlog were directly read and verified. When repository code indexing is healthy, EP-001 should be rechecked with a repository-wide search for `NullEventPublisher`, `EventPublisher`, and `event_publisher or` to detect any additional direct defaults introduced later.

## V41-EP-001 acceptance mapping

- Publisher behavior inventoried: verified.
- Direct production execution usage inventoried: PreviewTradeService, SubmitTradeService, ExecutionSupervisor.
- Metrics/diagnostics distinction documented: verified.
- Release-evidence dependencies and invalid assumptions documented: verified.
- Risks documented: EP-R1 through EP-R5.
- Repository-wide indexed-search completeness: **not claimed**, because the provider explicitly reported incomplete search results during this audit.

## Handoff to V41-EP-002

Define a storage/vendor-neutral external event publisher contract with explicit semantics for event identity, safe serialization, delivery outcome, retry/idempotency, backpressure/failure behavior, production capability declaration, and the boundary between observational delivery and durable execution authority.

No external publisher implementation is selected by this inventory.