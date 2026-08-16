# ADR-012: Durable Execution Coordination Authority

Status: Proposed for V41-CC-003 review

Date: 2026-08-16

Depends on:
- V41-CC-001 coordination inventory
- V41-CC-002 distributed coordination requirements
- ADR-007 execution persistence and idempotency
- ADR-008 SQLite execution durable adapter
- ADR-009 durable Paper dispatch claim
- ADR-010/011 F6B reconciliation foundation/history

## Context

EduTraderAI has two coordination classes that must not be confused:

1. legacy `ExecutionSupervisor` process-local guards implemented with a Python lock and in-memory active-symbol/idempotency/fingerprint/cooldown registries; and
2. the durable execution authority built around command registration, idempotency reservation, revision-checked aggregates, append-only transitions, dispatch-control generation, durable claim, append-only authorization, durable resolution, restart discovery and reconciliation.

ADR-009 already makes SQLite the sole authoritative election mechanism for controlled Paper dispatch and deliberately gives only a newly committed winning claim an in-process effect grant. Claims do not expire or transfer automatically. This provides a strong at-most-once automatic-dispatch posture for the currently supported local durable topology.

V41-CC-003 asks whether broader coordination should be implemented with database authority, Redis, a distributed lock service, an outbox/command ledger, or another mechanism.

## Proposed decision

**Extend the existing durable execution database authority as the single source of consequential coordination truth. Do not add Redis or a separate distributed lock service for the current topology.**

The durable execution persistence contracts remain storage-neutral. SQLite remains the concrete authoritative adapter for the currently supported single-host/local-durable deployment. If a future supported deployment requires independent processes on multiple hosts, migrate the same transactional authority model to a transactional server database or another storage adapter proven to satisfy the same contracts and fencing semantics before declaring that topology supported.

Process-local supervisor state remains an advisory/early-rejection layer only. It must never grant consequential authority and must never be used as proof that durable execution is safe.

An outbox/command-ledger may be added later for reliable asynchronous work notification/handoff, but it is not a replacement for execution ownership, idempotency, fencing, authorization, resolution or reconciliation. The outbox must carry references to already-authoritative durable records and must not create a second authority.

This ADR is a proposal. No runtime implementation or deployment-topology expansion is authorized until review accepts the decision and implementation slices are separately approved.

## Authority model

The proposed authority sequence is:

1. **Intake authority** — atomically register immutable command identity, reserve logical idempotency, create/revise the execution aggregate and persist dispatch intent.
2. **Discovery authority** — workers discover eligible durable work; discovery itself grants no effect authority.
3. **Control generation** — a durable monotonic dispatch-control generation fences policy/emergency-stop authority.
4. **Claim election** — one durable atomic claim is the exclusive winner for the execution identity.
5. **Authorization** — a second short transaction rereads current durable authority and appends one authorization bound to the winning claim/generation.
6. **External effect** — only the process that owns the newly committed winner grant may invoke the one-shot boundary. No database transaction is held open across the external effect.
7. **Resolution** — acknowledgement, rejection, possible-post-effect uncertainty, broker-reference ownership and lifecycle evidence are durably recorded.
8. **Recovery/reconciliation** — restart/recovery consumes the same durable authority; it never creates a weaker parallel ownership path.

## Why this is the preferred option

### Existing semantic fit

The repository already has the required semantic primitives: durable idempotency, CAS revision checking, control generation, durable claim, authorization, resolution and reconciliation. Reusing them avoids two sources of truth.

### Stronger failure semantics than a generic lock

The current claim model records execution identity and durable evidence. A generic distributed mutex says only that a holder owns a key temporarily; it does not inherently bind command fingerprint, aggregate revision, authorization, broker-reference ownership or reconciliation history.

### At-most-once bias

ADR-009's non-expiring claim design deliberately sacrifices automatic availability after crash windows in favor of preventing automatic redispatch. This is consistent with the repository's fail-closed Paper execution posture.

### Lower operational complexity

Adding Redis solely for coordination introduces another availability domain, credentials, deployment dependency and consistency boundary while the authoritative execution state must still be stored in the database. Without a demonstrated topology need, that duplication increases split-brain risk rather than reducing it.

### Storage-neutral migration path

Application ports already describe authority independent of SQLite. A future server-database adapter can preserve the same logical contracts while providing database concurrency semantics appropriate for multi-host deployments.

## Options considered

### Option A — Extend existing durable database authority

Decision: **Preferred.**

Advantages:
- preserves one source of truth;
- reuses tested command/idempotency/CAS/claim/authorization/resolution contracts;
- best alignment with ADR-007 through ADR-011;
- deterministic restart/reconciliation evidence;
- no new runtime dependency for the current topology;
- storage-neutral port contracts preserve a later migration path.

Costs/limits:
- SQLite topology must remain explicitly constrained;
- true multi-host deployment cannot be claimed without validation of a suitable shared transactional storage topology;
- high-concurrency scaling may eventually require a server database.

### Option B — Redis lease/lock plus existing durable database

Decision: **Rejected for current topology; reconsider only with demonstrated operational need.**

Potential advantages:
- common primitives for leases and short-lived distributed locks;
- useful for high-throughput multi-worker scheduling.

Reasons not selected now:
- creates dual authority unless carefully subordinated to durable execution state;
- lease expiry/clock/network-partition behavior is more availability-oriented than the current non-expiring at-most-once claim posture;
- still requires durable DB state for idempotency, lifecycle, resolution and reconciliation;
- adds infrastructure/credentials/monitoring/failure modes without solving a currently authorized multi-host requirement.

### Option C — External distributed lock service

Decision: **Rejected as primary authority.**

A generic lock cannot replace command registration, idempotency reservation, revision checking, claim evidence, authorization and resolution. It could only be an optimization around the durable authority and therefore does not justify an additional source of ownership truth.

### Option D — Transactional server database as authority now

Decision: **Deferred, not rejected.**

This is the preferred evolution if/when the supported topology requires independent multi-host workers or SQLite becomes an operational bottleneck. The implementation should adapt the existing storage-neutral ports and prove equivalent-or-stronger CAS/transaction/claim behavior rather than redesigning execution semantics.

### Option E — Outbox / command ledger

Decision: **Complementary, not an authority replacement.**

A transactional outbox can improve reliable asynchronous notification after durable intake. It cannot atomically include the external broker effect and must not grant effect permission. Consumers still require durable claim/authorization semantics before consequential action.

## Required topology declaration

Until a future adapter and validation package are accepted, the architecture must distinguish:

| Topology | Proposed support posture |
|---|---|
| One process + durable SQLite | Supported by existing model, subject to current release gates |
| Multiple processes on one host using the exact same supported SQLite database | Not automatically claimed by this ADR; requires explicit adversarial validation of connection/transaction/claim behavior and operational configuration |
| Multiple hosts using SQLite over network/shared filesystem | Unsupported unless separately proven; do not infer safety from SQLite durability alone |
| Multiple hosts using a transactional server database adapter implementing the same authority contracts | Target future architecture; unsupported until adapter, migrations, fault tests and operational validation are accepted |
| In-memory persistence for consequential dispatch | Unsupported as authority; test-only/local deterministic use |

## Fencing and stale-worker policy

The authoritative fencing identity is the durable dispatch-control generation plus immutable claim/authorization identity. A stale worker must not infer authority from holding a Python object or from having previously passed a local guard.

Any future takeover/abandonment mechanism must:
- create an explicit monotonic authority change;
- preserve the old claim/authorization history;
- prove that the old authority cannot cross the effect boundary after supersession;
- require reconciliation when prior effect status is uncertain;
- never implement timeout-based automatic redispatch merely because a process-local lease expired.

The current non-expiring claim model remains valid until such a mechanism is separately designed and accepted.

## Symbol serialization and cooldown

The existing supervisor's `_active_symbols` and `_last_success_by_symbol` are not elevated to distributed authority by this decision.

If symbol serialization becomes a cross-process safety requirement, it should be represented through durable active execution state or a durable coordination identity within the same execution authority model.

If cooldown must survive restart as a safety requirement, its authoritative timestamp should be derived from durable execution history or persisted policy state. Process-local cooldown may remain only as an optimization when it is explicitly documented as such.

## Outbox boundary

If asynchronous worker delivery is later introduced, the preferred pattern is:

- intake transaction persists authoritative execution state and an inert work-notification record/outbox row together;
- delivery can be at-least-once;
- consumers treat delivery as a wake-up hint, not permission;
- consumer rechecks durable state and acquires the authoritative claim/authorization before effect;
- duplicate delivery therefore becomes harmless replay rather than duplicate execution authority.

## Consequences

Positive:
- one durable authority model;
- preserves existing fail-closed semantics and tested recovery paths;
- minimizes infrastructure complexity;
- provides a clean migration path to a server database without rewriting domain execution semantics;
- keeps process-local supervisor policy clearly subordinate.

Negative/tradeoffs:
- current SQLite topology remains deliberately constrained;
- non-expiring claims can require operator/reconciliation intervention after crash windows;
- scaling to many hosts will require a new durable adapter and operational work;
- some local supervisor policies such as authoritative cooldown may need durable integration later.

## Validation required before acceptance

Technical acceptance of this ADR should require evidence that the existing/future implementation satisfies the V41-CC-002 requirement set, especially:

- one winner under competing claim attempts;
- stale-generation/stale-worker rejection;
- restart recovery with empty process memory;
- exact/logical replay and conflict behavior;
- pre-effect and possible-post-effect fault injection;
- outcome-unknown never auto-redispatches;
- competing normal/recovery workers share one authority;
- broker-reference ownership conflicts remain fail closed;
- database busy/unavailable/corruption paths do not fall back to local permission;
- deployment topology is explicitly documented and tested.

## Migration strategy if multi-host becomes required

1. Freeze storage-neutral execution authority contracts and behavioral tests.
2. Implement a server-database adapter behind the same ports.
3. Port schema/migrations and preserve canonical fingerprints/identities.
4. Run the full persistence, intake, competing-worker, crash-window, stale-worker, reconciliation and restart suites against both adapters where applicable.
5. Add true multi-process/multi-host adversarial tests for the target database topology.
6. Prove fail-closed configuration and migration/rollback behavior.
7. Only then update the supported deployment matrix.

Redis may still be used later for non-authoritative scheduling/caching if justified, but no Redis-held lease or queue receipt should independently permit a broker effect.

## Decision status and governance boundary

This document completes the **architecture proposal** portion of V41-CC-003. It deliberately does not mark itself `Accepted` and does not claim the backlog acceptance criterion “ADR accepted.” Human/owner technical review remains the governance boundary.

No source code, runtime wiring, persistence migration, broker integration, credential access, `state/` access, or consequential action is part of this ADR proposal.